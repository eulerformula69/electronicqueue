import asyncio
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path as FilePath
from typing import List

import bcrypt
from fastapi import (
    APIRouter, Body, Depends, File, Header, HTTPException, Query, UploadFile,
    WebSocket, WebSocketDisconnect, status,
)
from fastapi.params import Path
from fastapi.responses import FileResponse
from sqlalchemy import and_, asc, func, literal
from sqlalchemy.orm import Session

from app.config import (
    ALLOWED_MEDIA_EXTENSIONS, BASE_DIR, DEFAULT_PAGE_LIMIT, MAX_FILE_SIZE,
    MAX_PAGE_LIMIT, PIPER_MODEL, PIPER_PATH, SESSION_TIMEOUT_SECONDS,
    TTS_CACHE_DIR, TTS_LENGTH_SCALE,
    TTS_NOISE_SCALE, TTS_NOISE_W_SCALE,
)
from app.connections import manager, operatorManager
from app.database import SessionLocal
from app.dependencies import (
    get_current_terminal, get_operator_by_session, verify_admin_session,
    verify_session,
)
from app.models import Operator, Service, Ticket, Window, WindowService
from app.schemas import (
    CallSpecificRequest, RedirectRequest, RedirectToWindowRequest, TicketCreate,
    TicketReprintResponse,
)
from app.security import get_password_hash, verify_password
from app.services.settings import get_system_settings_dict
from app.services.tickets import (
    assign_ticket_to_least_loaded_window, broadcast_board,
    broadcast_ticket_called, queue_available_condition, queue_order_expr,
    render_ticket_template, return_ticket_to_queue,
)

router = APIRouter()

COMPLETED_TODAY_TICKET_DETAIL = (
    "Обслуживание этого клиента уже завершено. Вызвать талон не получится."
)


def is_ticket_redirected_to_operator_window(ticket, operator_window_id: int | None) -> bool:
    return (
        ticket.target_window_id == operator_window_id
        and ticket.completion_reason == "redirected"
    )


def build_operator_queue_ticket_payload(ticket, operator_window_id: int | None) -> dict:
    return {
        "id": ticket.id,
        "number": ticket.number,
        "service_id": ticket.service_id,
        "service_name": ticket.service_name or "Неизвестно",
        "created_at": ticket.created_at.strftime("%H:%M") if ticket.created_at else "—",
        "priority": getattr(ticket, "priority", None),
        "target_window_id": ticket.target_window_id,
        "is_redirected_to_window": is_ticket_redirected_to_operator_window(
            ticket,
            operator_window_id,
        ),
    }


def _today_bounds(now: datetime | None = None):
    current = now or datetime.now()
    today_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    return today_start, tomorrow_start


def build_reprint_ticket_payload(
    db: Session,
    number: int,
    now: datetime | None = None,
) -> dict:
    today_start, tomorrow_start = _today_bounds(now)

    ticket = (
        db.query(Ticket)
        .filter(
            Ticket.number == number,
            Ticket.created_at >= today_start,
            Ticket.created_at < tomorrow_start,
        )
        .order_by(Ticket.created_at.desc())
        .first()
    )

    if not ticket:
        raise HTTPException(status_code=404, detail="Талон за сегодня не найден")

    waiting_before = (
        db.query(Ticket)
        .filter(
            Ticket.status == "waiting",
            Ticket.id < ticket.id,
        )
        .count()
    )

    return {
        "id": ticket.id,
        "number": ticket.number,
        "service_name": ticket.service.name if ticket.service else "Услуга не найдена",
        "waiting_before": waiting_before,
        "date": ticket.created_at.strftime("%d.%m.%Y %H:%M") if ticket.created_at else "",
    }


def find_completed_today_ticket_by_number(
    db: Session,
    number: int,
    now: datetime | None = None,
):
    today_start, tomorrow_start = _today_bounds(now)

    return (
        db.query(Ticket)
        .filter(
            Ticket.number == number,
            Ticket.status == "finished",
            Ticket.completion_reason == "completed",
            Ticket.finished_at >= today_start,
            Ticket.finished_at < tomorrow_start,
        )
        .order_by(Ticket.finished_at.desc())
        .first()
    )


@router.post("/tickets/", tags=["Tickets"])
async def create_ticket(
    ticket: TicketCreate,
    _auth = Depends(get_current_terminal) 
    ):
    db = SessionLocal()
    try:
        settings = get_system_settings_dict(db)
        
        # 1. Проверяем существование услуги
        service = (
            db.query(Service)
            .filter(Service.id == ticket.service_id, Service.is_archived == 0)
            .first()
        )
        if not service:
            raise HTTPException(status_code=404, detail="Услуга не найдена")

        if not service.visible_on_terminal or service.status != "active":
            raise HTTPException(
                status_code=400,
                detail="Услуга сейчас недоступна на терминале"
            )

        # 2. Валидация доступности окон
        if settings.get("hide_services_without_online_operators"):
            active_windows = (
                db.query(Window)
                .join(WindowService, Window.id == WindowService.window_id)
                .filter(
                    WindowService.service_id == service.id,
                    Window.status == "online"
                ).first()
            )
            if not active_windows:
                raise HTTPException(
                    status_code=400, 
                    detail="В данный момент услуга не оказывается (нет активных окон)"
                )

        target_window_id = None

        if service.operator_choice_enabled:
            if not ticket.window_id:
                raise HTTPException(status_code=400, detail="Выберите оператора")

            selected_window = (
                db.query(Window)
                .join(WindowService, Window.id == WindowService.window_id)
                .filter(
                    Window.id == ticket.window_id,
                    WindowService.service_id == service.id,
                    Window.status == "online"
                )
                .first()
            )

            if not selected_window:
                raise HTTPException(status_code=400, detail="Выбранный оператор сейчас недоступен")

            target_window_id = ticket.window_id

        # 3. Создаем тикет
        created_at = datetime.now()
        db_ticket = Ticket(
            service_id=service.id,
            status="waiting",
            target_window_id=target_window_id,
            created_at=created_at,
            queue_entered_at=created_at,
        )

        db.add(db_ticket)
        db.flush()
        db_ticket.root_ticket_id = db_ticket.id

        if not target_window_id and settings.get("queue_mode") == "dynamic_operator_distribution":
            assign_ticket_to_least_loaded_window(db, db_ticket)

        db.commit()
        db.refresh(db_ticket)

        # 4. Считаем людей перед талоном
        waiting_before = db.query(Ticket).filter(
            Ticket.status == "waiting",
            Ticket.id < db_ticket.id
        ).count()

        # 5. Рассылка уведомлений
        await manager.broadcast({
            "type": "queue_updated",
            "service_id": service.id
        })

        await broadcast_board()

        return {
            "id": db_ticket.id,
            "number": db_ticket.number,
            "service_name": service.name,
            "waiting_before": waiting_before,
            "date": datetime.now().strftime("%d.%m.%Y %H:%M")
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/tickets/reprint/{number}", response_model=TicketReprintResponse, tags=["Tickets"])
def reprint_ticket(
    number: int = Path(..., gt=0),
    _auth = Depends(get_current_terminal),
):
    db = SessionLocal()
    try:
        return build_reprint_ticket_payload(db, number)
    finally:
        db.close()


@router.post("/tickets/finish", tags=["Tickets"])
async def finish_ticket(operator: Operator = Depends(verify_session)):
    db = SessionLocal()

    if not operator.window_id:
        db.close()
        raise HTTPException(status_code=404, detail="Operator or window not found")
    
    ticket = db.query(Ticket).filter(
        Ticket.window_id == operator.window_id,
        Ticket.status == "called"  
    ).first()

    if not ticket:
        db.close()
        return {"detail": "Нет текущего клиента"}

    # Завершаем тикет
    ticket.status = "finished"
    ticket.completion_reason = "completed"
    if ticket.operator_id is None:
        ticket.operator_id = operator.id
    ticket.finished_at = datetime.now() #text("CURRENT_TIMESTAMP")

    db.commit()
    db.refresh(ticket)

    await broadcast_board()

    db.close()
    return ticket


@router.post("/tickets/next", tags=["Tickets"])
async def call_next_ticket(operator: Operator = Depends(verify_session)):
    db = SessionLocal()
    try:
        if not operator.window_id:
            return {"detail": "Оператору не назначено окно"}

        current = db.query(Ticket).filter(
            Ticket.window_id == operator.window_id,
            Ticket.status == "called"
        ).first()

        if current:
            return {"detail": f"Сначала завершите клиента: {current.number}"}

        settings = get_system_settings_dict(db)

        # Сначала всегда вызываем билеты, явно перенаправленные на это окно.
        ticket = (
            db.query(Ticket)
            .filter(
                Ticket.status == "waiting",
                Ticket.target_window_id == operator.window_id,
            )
            .order_by(queue_order_expr().asc())
            .first()
        )

        if not ticket:
            if settings.get("queue_mode") == "dynamic_operator_distribution":
                ticket = (
                    db.query(Ticket)
                    .filter(
                        Ticket.status == "waiting",
                        Ticket.window_id == operator.window_id,
                        Ticket.target_window_id.is_(None),
                        queue_available_condition(),
                    )
                    .order_by(queue_order_expr().asc())
                    .first()
                )
            else:
                ticket = (
                    db.query(Ticket)
                    .join(WindowService, Ticket.service_id == WindowService.service_id)
                    .filter(
                        WindowService.window_id == operator.window_id,
                        Ticket.status == "waiting",
                        Ticket.target_window_id.is_(None),
                        queue_available_condition(),
                    )
                    .order_by(
                        WindowService.priority.asc(),
                        queue_order_expr().asc()
                    )
                    .first()
                )

        if not ticket:
            return {"detail": "Нет ожидающих билетов"}

        ticket.status = "called"
        ticket.completion_reason = None
        ticket.operator_id = operator.id
        ticket.window_id = operator.window_id
        ticket.target_window_id = None
        ticket.called_at = datetime.now()
        ticket.finished_at = None

        db.commit()
        db.refresh(ticket)

        window = db.query(Window).filter(Window.id == ticket.window_id).first()

        await manager.broadcast({"type": "queue_updated"})
        await broadcast_board()

        if window:
            await broadcast_ticket_called(ticket, window)

        return {
            "id": ticket.id,
            "number": ticket.number,
            "status": ticket.status,
            "service_name": ticket.service.name if ticket.service else "Услуга не найдена"
        }
    finally:
        db.close()


@router.post("/tickets/call-specific", tags=["Tickets"])
async def call_specific_ticket(data: CallSpecificRequest, operator: Operator = Depends(verify_session)):
    db = SessionLocal()
    try:
        if not operator.window_id:
            return {"detail": "Оператору не назначено окно"}

        # Проверяем, не обслуживается ли уже клиент
        current = db.query(Ticket).filter(
            Ticket.window_id == operator.window_id,
            Ticket.status == "called"
        ).first()

        if current:
            return {"detail": f"Сначала завершите клиента: {current.number}"}

        # Ищем билет по номеру только за сегодняшний день
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)

        ticket = db.query(Ticket).filter(
            Ticket.number == data.number,
            Ticket.status.in_(["waiting", "cancelled"]),
            Ticket.created_at >= today_start,
            Ticket.created_at < tomorrow_start
        ).order_by(Ticket.created_at.desc()).first()

        if not ticket:
            completed_ticket = find_completed_today_ticket_by_number(
                db,
                data.number,
                now=today_start,
            )
            if completed_ticket:
                return {"detail": COMPLETED_TODAY_TICKET_DETAIL}

            return {"detail": "Билет с таким номером за сегодня не найден или недоступен для вызова"}

        # Если билет был перенаправлен на конкретное окно, вызвать его может только это окно.
        if ticket.target_window_id is not None and ticket.target_window_id != operator.window_id:
            return {"detail": "Этот талон перенаправлен на другое рабочее место"}

        # Обычные билеты по-прежнему можно вызвать только на окне, которое обслуживает их услугу.
        if ticket.target_window_id is None:
            window_service = db.query(WindowService).filter(
                WindowService.window_id == operator.window_id,
                WindowService.service_id == ticket.service_id
            ).first()

            if not window_service:
                return {"detail": "Ваше окно не обслуживает услугу этого талона"}

        # Обновляем статус билета и привязываем к текущему окну
        ticket.status = "called"
        ticket.completion_reason = None
        ticket.operator_id = operator.id
        ticket.window_id = operator.window_id
        ticket.target_window_id = None
        ticket.called_at = datetime.now()
        ticket.finished_at = None

        db.commit()
        db.refresh(ticket)

        window = db.query(Window).filter(Window.id == ticket.window_id).first()

        # Обновляем табло только после сохранения в БД
        await broadcast_board()

        if window:
            await broadcast_ticket_called(ticket, window)

        return {
            "id": ticket.id,
            "number": ticket.number,
            "status": ticket.status,
            "service_name": ticket.service.name if ticket.service else "Услуга не найдена"
        }
    finally:
        db.close()


@router.post("/tickets/cancel", tags=["Tickets"])
async def cancel_current_ticket(operator: Operator = Depends(verify_session)):
    db = SessionLocal()

    if not operator.window_id:
        db.close()
        return {"detail": "Оператору не назначено окно"}

    # Ищем текущий вызванный билет в этом окне
    ticket = db.query(Ticket).filter(
        Ticket.window_id == operator.window_id,
        Ticket.status == "called"
    ).first()

    if not ticket:
        db.close()
        return {"detail": "Нет активного билета для отмены (клиент не вызван)"}

    # Устанавливаем статус отмены и время завершения
    ticket.status = "cancelled"
    ticket.completion_reason = "cancelled"
    if ticket.operator_id is None:
        ticket.operator_id = operator.id
    ticket.finished_at = datetime.now()

    db.commit()
    db.refresh(ticket)

    # Уведомляем систему об изменениях только после сохранения в БД
    await manager.broadcast({
        "type": "queue_updated"
    })

    # Обновляем табло, чтобы номер исчез из списка вызванных
    await broadcast_board()

    db.close()

    return {"status": "cancelled", "ticket_number": ticket.number}


@router.post("/tickets/return-to-queue", tags=["Tickets"])
async def return_current_ticket_to_queue(operator: Operator = Depends(verify_session)):
    db = SessionLocal()
    try:
        if not operator.window_id:
            raise HTTPException(status_code=400, detail="Оператору не назначено окно")

        ticket = db.query(Ticket).filter(
            Ticket.window_id == operator.window_id,
            Ticket.status == "called"
        ).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Нет активного билета для возврата в очередь")

        settings = get_system_settings_dict(db)

        return_ticket_to_queue(ticket)

        if settings.get("queue_mode") == "dynamic_operator_distribution":
            assign_ticket_to_least_loaded_window(db, ticket)

        db.commit()
        db.refresh(ticket)

        await manager.broadcast({"type": "queue_updated"})
        await broadcast_board()

        return {"status": "waiting", "ticket_number": ticket.number}
    finally:
        db.close()


@router.get("/tickets/my-queue", tags=["Tickets"])
def get_my_queue(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    operator: Operator = Depends(verify_session)
    ):
    db = SessionLocal()
    settings = get_system_settings_dict(db)
    try:
        if not operator.window_id:
            return []

        # 1) Перенаправленные именно на это окно билеты всегда сверху.
        redirected_query = (
            db.query(
                Ticket.id,
                Ticket.number,
                Ticket.service_id,
                Ticket.created_at,
                Ticket.completion_reason,
                Ticket.target_window_id,
                Service.name.label("service_name"),
                literal(0).label("priority")
            )
            .join(Service, Service.id == Ticket.service_id)
            .filter(
                Ticket.status == "waiting",
                Ticket.target_window_id == operator.window_id,
            )
            .order_by(queue_order_expr().asc())
        )

        # 2) Обычные билеты ниже — по текущему режиму очереди.
        if settings.get("queue_mode") == "dynamic_operator_distribution":
            ordinary_query = (
                db.query(
                    Ticket.id,
                    Ticket.number,
                    Ticket.service_id,
                    Ticket.created_at,
                    Ticket.completion_reason,
                    Ticket.target_window_id,
                    Service.name.label("service_name"),
                    literal(None).label("priority")
                )
                .join(Service, Service.id == Ticket.service_id)
                .filter(
                    Ticket.window_id == operator.window_id,
                    Ticket.status == "waiting",
                    Ticket.target_window_id.is_(None),
                )
                .order_by(queue_order_expr().asc())
            )
        else:
            ordinary_query = (
                db.query(
                    Ticket.id,
                    Ticket.number,
                    Ticket.service_id,
                    Ticket.created_at,
                    Ticket.completion_reason,
                    Ticket.target_window_id,
                    Service.name.label("service_name"),
                    WindowService.priority.label("priority")
                )
                .join(WindowService, Ticket.service_id == WindowService.service_id)
                .join(Service, Service.id == Ticket.service_id)
                .filter(
                    WindowService.window_id == operator.window_id,
                    Ticket.status == "waiting",
                    Ticket.target_window_id.is_(None),
                )
                .order_by(
                    WindowService.priority.asc(),
                    queue_order_expr().asc()
                )
            )

        tickets = (redirected_query.all() + ordinary_query.all())[skip:skip + limit]

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tickets_served_today = db.query(Ticket).filter(
            Ticket.window_id == operator.window_id,
            Ticket.status == "finished",
            Ticket.finished_at >= today_start
        ).count()

        result = []
        for t in tickets:
            result.append(build_operator_queue_ticket_payload(t, operator.window_id))

        return {
            "tickets": result,
            "tickets_served_today": tickets_served_today
        }
    finally:
        db.close()


@router.post("/tickets/redirect-to-window", tags=["Tickets"])
async def redirect_ticket_to_window(data: RedirectToWindowRequest, operator: Operator = Depends(verify_session)):
    db = SessionLocal()
    try:
        if not operator.window_id:
            raise HTTPException(status_code=400, detail="Оператору не назначено окно")

        ticket = db.query(Ticket).filter(
            Ticket.id == data.ticket_id,
            Ticket.status == "called"
        ).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Вызванный билет не найден")

        if ticket.window_id != operator.window_id:
            raise HTTPException(status_code=403, detail="Этот билет не является текущим билетом вашего окна")

        target_window = db.query(Window).filter(Window.id == data.window_id).first()
        if not target_window:
            raise HTTPException(status_code=404, detail="Рабочее место для перенаправления не найдено")

        ticket.status = "waiting"
        ticket.completion_reason = "redirected"
        ticket.operator_id = None
        ticket.window_id = None
        ticket.target_window_id = target_window.id
        ticket.created_at = datetime.now()
        ticket.called_at = None
        ticket.finished_at = None

        db.commit()
        db.refresh(ticket)

        await manager.broadcast({"type": "queue_updated"})
        await broadcast_board()

        message = f"Билет перенаправлен на рабочее место: {target_window.name}"
        response = {"message": message, "ticket": ticket}
        if target_window.status != "online":
            response["warning"] = f"Рабочее место {target_window.name} сейчас не online"
        return response
    finally:
        db.close()


@router.post("/tickets/redirect", tags=["Tickets"])
async def redirect_ticket(data: RedirectRequest, operator: Operator = Depends(verify_session)):
    db = SessionLocal()
    try:
        settings = get_system_settings_dict(db)

        ticket = db.query(Ticket).filter(
            Ticket.id == data.ticket_id,
            Ticket.status == "called"
        ).first()
        if not ticket:
            return {"detail": "Сначала завершите текущего клиента или тикет не найден"}

        if ticket.window_id != operator.window_id:
            raise HTTPException(
                status_code=403,
                detail="Этот билет не является текущим билетом вашего рабочего места",
            )

        service = (
            db.query(Service)
            .filter(Service.id == data.new_service_id, Service.is_archived == 0)
            .first()
        )
        if not service:
            return {"detail": "Новая услуга не найдена"}

        windows = (
            db.query(Window)
            .join(WindowService, Window.id == WindowService.window_id)
            .filter(
                WindowService.service_id == service.id,
                Window.status == "online"
            )
            .distinct()
            .order_by(Window.id)
            .all()
        )

        if not windows:
            return {"detail": "Нет доступных окон для этой услуги, Пожалуйста сообщите клиенту"}

        redirected_at = datetime.now()
        root_ticket_id = ticket.root_ticket_id or ticket.id

        ticket.status = "finished"
        ticket.completion_reason = "redirected"
        if ticket.operator_id is None:
            ticket.operator_id = operator.id
        ticket.finished_at = redirected_at

        redirected_ticket = Ticket(
            number=ticket.number,
            service_id=service.id,
            status="waiting",
            completion_reason=None,
            root_ticket_id=root_ticket_id,
            operator_id=None,
            window_id=None,
            target_window_id=None,
            created_at=redirected_at,
            queue_entered_at=redirected_at,
            called_at=None,
            finished_at=None,
        )
        db.add(redirected_ticket)
        db.flush()

        if settings.get("queue_mode") == "dynamic_operator_distribution":
            assign_ticket_to_least_loaded_window(db, redirected_ticket)

        db.commit()
        db.refresh(redirected_ticket)

        await manager.broadcast({
            "type": "queue_updated",
            "service_id": service.id
        })

        asyncio.create_task(broadcast_board())

        return {"message": "Билет перенаправлен", "ticket": redirected_ticket}

    finally:
        db.close()


@router.post("/tickets/recall", tags=["Tickets"])
async def recall_ticket(operator: Operator = Depends(verify_session)):
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(
            Ticket.window_id == operator.window_id,
            Ticket.status == "called"
        ).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Нет активного клиента для повторного вызова")

        window = db.query(Window).filter(Window.id == operator.window_id).first()
        if not window:
            raise HTTPException(status_code=404, detail="Окно не найдено")

        settings = get_system_settings_dict(db)

        tts_text = render_ticket_template(
            settings["call_message_template"],
            ticket.number,
            window.name
        )

        display_text = render_ticket_template(
            settings["board_ticket_template"],
            ticket.number,
            window.name
        )

        await manager.broadcast({
            "type": "recall_ticket",
            "ticket_id": ticket.id,
            "ticket_number": ticket.number,
            "window_name": window.name,
            "display_text": display_text,
            "tts_text": tts_text
        })

        return {"status": "success", "message": f"Повторный вызов клиента {ticket.number}"}
    finally:
        db.close()


@router.get("/tickets/current", tags=["Tickets"])
def get_current_ticket(operator: Operator = Depends(verify_session)):
    db = SessionLocal()
    try:
        if not operator.window_id:
            return {"ticket": None}

        ticket = (
            db.query(Ticket)
            .filter(
                Ticket.status == "called",
                Ticket.window_id == operator.window_id
            )
            .order_by(Ticket.called_at.asc())
            .first()
        )

        if not ticket:
            return {"ticket": None}

        return {"ticket": ticket}
    finally:
        db.close()
