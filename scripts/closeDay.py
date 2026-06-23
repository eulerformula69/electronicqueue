#!/usr/bin/env python3
"""Close the queue at the end of the working day."""

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, or_, text
from sqlalchemy.exc import SQLAlchemyError
import websockets


PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.database import SessionLocal  # noqa: E402
from app.config import CLOSE_DAY_WS_URL  # noqa: E402
from app.models import (  # noqa: E402
    Operator,
    Service,
    Ticket,
    UserSession,
    Window,
    record_operator_status,
)
from app.services.settings import get_system_settings_dict  # noqa: E402


@dataclass(frozen=True)
class CloseDayResult:
    windows_offline: int
    tickets_finished: int
    tickets_cancelled: int
    sessions_deleted: int


def close_day(db) -> CloseDayResult:
    """Apply all end-of-day changes atomically and return affected row counts."""
    # This helper may create the singleton settings row and commit it.
    settings = get_system_settings_dict(db)

    # Prevent queue activity from being committed halfway through the operation.
    db.execute(
        text(
            "LOCK TABLE tickets, windows, sessions, operator_status_periods "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
    )

    now = func.timezone("Asia/Irkutsk", func.current_timestamp())
    db.execute(
        text(
            """
            UPDATE tickets t
            SET operator_id = o.id
            FROM operators o
            WHERE t.status = 'called'
              AND t.operator_id IS NULL
              AND t.window_id = o.window_id
            """
        )
    )
    tickets_finished = (
        db.query(Ticket)
        .filter(Ticket.status == "called")
        .update(
            {
                Ticket.status: "finished",
                Ticket.completion_reason: "completed",
                Ticket.finished_at: now,
            },
            synchronize_session=False,
        )
    )
    tickets_cancelled = (
        db.query(Ticket)
        .filter(Ticket.status == "waiting")
        .update(
            {
                Ticket.status: "cancelled",
                Ticket.completion_reason: "cancelled",
                Ticket.finished_at: now,
            },
            synchronize_session=False,
        )
    )

    operators = db.query(Operator).order_by(Operator.id).all()
    for operator in operators:
        record_operator_status(db, operator.id, operator.window_id, "offline")

    windows_offline = (
        db.query(Window)
        .filter(or_(Window.status != "offline", Window.status.is_(None)))
        .update({Window.status: "offline"}, synchronize_session=False)
    )
    sessions_deleted = db.query(UserSession).delete(synchronize_session=False)

    if settings["hide_services_without_online_operators"]:
        db.query(Service).update(
            {Service.status: "inactive"}, synchronize_session=False
        )

    db.commit()
    return CloseDayResult(
        windows_offline=windows_offline,
        tickets_finished=tickets_finished,
        tickets_cancelled=tickets_cancelled,
        sessions_deleted=sessions_deleted,
    )


async def notify_clients() -> None:
    """Ask the running application to refresh all connected clients."""
    async with websockets.connect(
        CLOSE_DAY_WS_URL, open_timeout=5, close_timeout=2
    ) as websocket:
        await websocket.send(json.dumps({"type": "close_day_updated"}))


def main() -> int:
    db = SessionLocal()
    try:
        result = close_day(db)
    except (SQLAlchemyError, ValueError) as error:
        db.rollback()
        print(f"Ошибка закрытия рабочего дня: {error}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print("Рабочий день закрыт.")
    print(f"Окон переведено в offline: {result.windows_offline}")
    print(f"Текущих билетов завершено: {result.tickets_finished}")
    print(f"Ожидающих билетов отменено: {result.tickets_cancelled}")
    print(f"Сессий операторов закрыто: {result.sessions_deleted}")

    try:
        asyncio.run(notify_clients())
    except Exception as error:
        print(
            "База обновлена, но WebSocket-уведомление не отправлено: "
            f"{error}",
            file=sys.stderr,
        )
        return 2

    print("Терминалы, операторы и табло обновлены через WebSocket.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
