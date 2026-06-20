import asyncio
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import SESSION_TIMEOUT_SECONDS
from app.connections import manager, operatorManager
from app.database import SessionLocal
from app.models import (
    AdminSession, Operator, OperatorStatusPeriod, Service, Ticket, UserSession,
    Window, WindowService, record_operator_status,
)
from app.services.settings import get_system_settings_dict
from app.services.tickets import (
    assign_ticket_to_least_loaded_window, broadcast_board,
    reassign_waiting_tickets_from_window,
)


def update_services_status_for_window(db: Session, window_id: int):
    settings = get_system_settings_dict(db)

    # Если скрытие услуг отключено, услуги остаются доступными на терминале.
    if not settings["hide_services_without_online_operators"]:
        service_ids = [
            row[0]
            for row in db.query(WindowService.service_id)
            .filter(WindowService.window_id == window_id)
            .all()
        ]
        if service_ids:
            db.query(Service).filter(Service.id.in_(service_ids)).update(
                {Service.status: "active"},
                synchronize_session=False
            )
        db.commit()
        return

    # Получаем все услуги окна одним запросом.
    service_ids = [
        row[0]
        for row in db.query(WindowService.service_id)
        .filter(WindowService.window_id == window_id)
        .all()
    ]
    if not service_ids:
        db.commit()
        return

    # Находим услуги, у которых есть хотя бы одно online-окно, одним запросом.
    online_service_ids = {
        row[0]
        for row in db.query(WindowService.service_id)
        .join(Window, WindowService.window_id == Window.id)
        .filter(
            WindowService.service_id.in_(service_ids),
            Window.status == "online"
        )
        .distinct()
        .all()
    }

    services = db.query(Service).filter(Service.id.in_(service_ids)).all()
    for service in services:
        new_status = "active" if service.id in online_service_ids else "inactive"
        if service.status != new_status:
            service.status = new_status

    db.commit()


def get_operator_state(operator_id: int):
    db = SessionLocal()
    try:
        operator = db.query(Operator).filter(Operator.id == operator_id).first()
        if not operator or not operator.window_id:
            return {"error": "Оператор не найден или нет окна"}

        window = db.query(Window).filter(Window.id == operator.window_id).first()

        # Очередь (уже с учетом приоритета, как мы делали ранее)
        tickets = (
            db.query(Ticket)
            .join(WindowService, Ticket.service_id == WindowService.service_id)
            .filter(WindowService.window_id == operator.window_id, Ticket.status == "waiting")
            .order_by(WindowService.priority.desc(), Ticket.created_at.asc())
            .all()
        )

        current_ticket = db.query(Ticket)\
            .filter(Ticket.window_id == operator.window_id, Ticket.status == "called")\
            .first()

        # Услуги с приоритетами
        services_data = (
            db.query(Service.name, WindowService.priority)
            .join(WindowService, Service.id == WindowService.service_id)
            .filter(WindowService.window_id == operator.window_id)
            .order_by(WindowService.priority.desc())
            .all()
        )

        return {
            "operator": {"id": operator.id, "name": operator.name},
            "window": {"id": window.id, "name": window.name, "status": window.status if window else "offline"},
            "services": [{"name": s[0], "priority": s[1]} for s in services_data],
            "queue": [{"id": t.id, "number": t.number} for t in tickets],
            "current_ticket": {"id": current_ticket.id, "number": current_ticket.number} if current_ticket else None
        }
    finally:
        db.close()


async def cleanup_sessions():
    print("[System] Фоновая задача очистки сессий запущена")
    while True:
        await asyncio.sleep(SESSION_TIMEOUT_SECONDS)
        db: Session = SessionLocal()
        try:
            settings = get_system_settings_dict(db)
            timeout_datetime = datetime.now() - timedelta(seconds=SESSION_TIMEOUT_SECONDS)
            mapped_session_ids = list(manager.session_id_to_ws.keys())
            ws_alive_operator_ids = set()
            ws_alive_admin_ids = set()
            
            if mapped_session_ids:
                ws_user_rows = (
                    db.query(UserSession.operator_id)
                    .filter(UserSession.session_id.in_(mapped_session_ids))
                    .all()
                )
                ws_admin_rows = (
                    db.query(AdminSession.admin_id)
                    .filter(AdminSession.session_id.in_(mapped_session_ids))
                    .all()
                )
                ws_alive_operator_ids = {row[0] for row in ws_user_rows if row and row[0] is not None}
                ws_alive_admin_ids = {row[0] for row in ws_admin_rows if row and row[0] is not None}

            # --- ЧАСТЬ 1: ОПЕРАТОРЫ ---
            # Добавляем фильтр .filter(UserSession.is_expirable == 1)
            # Сессии с is_expirable=0 (терминалы) база просто не вернет в этом списке
            dead_sessions = db.query(UserSession).filter(
                UserSession.last_seen < timeout_datetime,
                UserSession.is_expirable == 1  # <--- Игнорируем вечные сессии
            ).all()
            
            if dead_sessions:
                print(f"\n[Cleanup] Найдено мертвых сессий операторов: {len(dead_sessions)}")
                need_board_update = False

                for session in dead_sessions:
                    if session.operator_id in ws_alive_operator_ids:
                        session.last_seen = datetime.now()
                        continue

                    other_alive = db.query(UserSession).filter(
                        UserSession.operator_id == session.operator_id,
                        UserSession.last_seen >= timeout_datetime,
                        UserSession.session_id != session.session_id
                    ).first()

                    if other_alive:
                        db.delete(session)
                        continue

                    operator = db.query(Operator).filter(Operator.id == session.operator_id).first()

                    if operator and operator.window_id:
                        window = db.query(Window).filter(Window.id == operator.window_id).first()

                        if window:
                            window.status = "offline"
                            record_operator_status(
                                db, operator.id, window.id, window.status
                            )
                            db.flush()

                            if settings["active_ticket_on_operator_logout"] == "return_to_queue":
                                active_ticket = db.query(Ticket).filter(
                                    Ticket.window_id == operator.window_id,
                                    Ticket.status == "called"
                                ).first()

                                if active_ticket:
                                    active_ticket.status = "waiting"
                                    active_ticket.window_id = None

                                    if (
                                        settings.get("queue_mode") == "dynamic_operator_distribution"
                                        and active_ticket.target_window_id is None
                                    ):
                                        assign_ticket_to_least_loaded_window(db, active_ticket)

                                    need_board_update = True

                            await reassign_waiting_tickets_from_window(db, window.id)

                            update_services_status_for_window(db, window.id)

                    db.delete(session)

            # --- ЧАСТЬ 2: АДМИНИСТРАТОРЫ / ТЕРМИНАЛЫ ---
            # Аналогично добавляем фильтр AdminSession.is_expirable == 1
            dead_admin_sessions = db.query(AdminSession).filter(
                AdminSession.last_seen < timeout_datetime,
                AdminSession.is_expirable == 1  # <--- Игнорируем терминалы
            ).all()
            
            if dead_admin_sessions:
                print(f"[Cleanup] Найдено мертвых сессий админов: {len(dead_admin_sessions)}")
                for a_session in dead_admin_sessions:
                    if a_session.admin_id in ws_alive_admin_ids:
                        a_session.last_seen = datetime.now()
                        continue

                    db.delete(a_session)

            db.commit()

            if dead_sessions:
                await manager.broadcast({"type": "services_updated"})
                if need_board_update:
                    await broadcast_board()
                    await manager.broadcast({"type": "queue_updated"})

        except Exception as e:
            print(f"[Cleanup] ОШИБКА: {e}")
            db.rollback()
        finally:
            db.close()
