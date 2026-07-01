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
from sqlalchemy import and_, asc, func, literal, text
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
from app.models import (
    AdminSession, Operator, Ticket, UserSession, Window,
    record_operator_status,
)
from app.security import get_password_hash, verify_password
from app.services.operators import get_operator_state, update_services_status_for_window
from app.services.settings import get_system_settings_dict
from app.services.tickets import (
    broadcast_board, get_board_state, reassign_waiting_tickets_from_window,
    return_ticket_to_queue,
)

router = APIRouter()


@router.websocket("/ws/terminal")
async def websocket_endpoint(websocket: WebSocket):
    """
    Общий WebSocket‑канал для терминалов, операторов и админки.
    Cюда же приходят небольшие heartbeat‑сообщения:
    {"type": "ping", "session_id": "..."} — мы обновляем last_seen в БД.
    """
    db: Session = SessionLocal()
    await manager.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except Exception:
                # Игнорируем некорректный JSON, чтобы не ронять соединение
                continue

            msg_type = message.get("type")

            # WebSocket heartbeat: обновляем last_seen по session_id
            if msg_type == "ping":
                session_id = message.get("session_id")
                if not session_id:
                    continue

                try:
                    # Пытаемся найти сначала операторскую, затем админскую сессию
                    session = db.query(UserSession).filter(
                        UserSession.session_id == session_id
                    ).first()
                    if not session:
                        session = db.query(AdminSession).filter(
                            AdminSession.session_id == session_id
                        ).first()

                    if session:
                        session.last_seen = datetime.now()
                        db.commit()
                        # Сохраняем mapping сокет -> session_id
                        ws_id = id(websocket)
                        manager.ws_id_to_session_id[ws_id] = session_id
                        manager.session_id_to_ws[session_id] = websocket
                    else:
                        # Если сессии нет в БД — уведомляем клиента и закрываем WS
                        await websocket.send_json({
                            "type": "session_expired",
                            "message": "Ваша сессия истекла. Войдите в систему снова.",
                        })
                        await websocket.close()
                        break
                except Exception:
                    db.rollback()
                continue

            # Обрабатываем старые типы служебных сообщений
            if msg_type == "queue_updated":
                await manager.broadcast({"type": "queue_updated"})
            elif msg_type == "services_updated":
                await manager.broadcast({"type": "services_updated"})
            elif msg_type == "close_day_updated":
                await manager.broadcast({"type": "services_updated"})
                await manager.broadcast({"type": "queue_updated"})
                deleted_session_ids = message.get("deleted_session_ids")
                if isinstance(deleted_session_ids, list):
                    await manager.send_to_sessions(
                        [
                            session_id
                            for session_id in deleted_session_ids
                            if isinstance(session_id, str)
                        ],
                        {
                            "type": "session_expired",
                            "silent": True,
                            "message": "\u0420\u0430\u0431\u043e\u0447\u0438\u0439 \u0434\u0435\u043d\u044c \u0437\u0430\u043a\u0440\u044b\u0442. \u0412\u043e\u0439\u0434\u0438\u0442\u0435 \u0432 \u0441\u0438\u0441\u0442\u0435\u043c\u0443 \u0441\u043d\u043e\u0432\u0430.",
                        },
                    )
                await broadcast_board()

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    finally:
        db.close()


@router.websocket("/ws/board")
async def websocket_board(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # при подключении сразу отправляем текущее состояние табло
        await websocket.send_json(get_board_state())

        while True:
            await websocket.receive_text()  # держим соединение живым

    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.websocket("/ws/operator/{operator_id}")
async def websocket_operator(websocket: WebSocket, operator_id: int):
    db = SessionLocal()
    await websocket.accept()
    try:
        # подключаем оператора к менеджеру
        await operatorManager.connect(operator_id, websocket)

        # при подключении сразу отправляем текущие данные
        operator_data = get_operator_state(operator_id)
        await websocket.send_json(operator_data)

        # держим соединение живым
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                print(f"Оператор {operator_id} отключился")
                break  # выходим из цикла

    except Exception as e:
        print(f"Ошибка в websocket_operator: {e}")

    finally:
        # всегда выполняем отсоединение и очистку базы
        operatorManager.disconnect(operator_id)

        try:
            settings = get_system_settings_dict(db)
            # удаляем все сессии этого оператора
            sessions = db.query(UserSession).filter(UserSession.operator_id == operator_id).all()
            for s in sessions:
                db.delete(s)

            # делаем окно offline
            operator = db.query(Operator).filter(Operator.id == operator_id).first()
            if operator and operator.window_id:
                window = db.query(Window).filter(Window.id == operator.window_id).first()
                if window:
                    window.status = "offline"
                    record_operator_status(db, operator.id, window.id, window.status)
                    db.flush()
                    await reassign_waiting_tickets_from_window(db, window.id)
                    update_services_status_for_window(db, window.id)

                    if settings["active_ticket_on_operator_logout"] == "return_to_queue":
                        active_ticket = db.query(Ticket).filter(
                            Ticket.window_id == operator.window_id,
                            Ticket.status == "called"
                        ).first()
                        if active_ticket:
                            return_ticket_to_queue(active_ticket)

            db.commit()
        except Exception as e:
            print(f"Ошибка при очистке базы для оператора {operator_id}: {e}")
        finally:
            db.close()

        # уведомляем всех терминалы
        await manager.broadcast({"type": "services_updated", "target": "operator"})
