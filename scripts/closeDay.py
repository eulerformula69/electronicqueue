#!/usr/bin/env python3
"""Close the queue at the end of the working day."""

import asyncio
import argparse
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
from scripts.close_day_schedule import (  # noqa: E402
    build_close_day_command,
    collect_interactive_schedule,
    schedule_close_days,
)


@dataclass(frozen=True)
class CloseDayResult:
    windows_offline: int
    tickets_finished: int
    tickets_cancelled: int
    tickets_deferred: int
    sessions_deleted: int
    deleted_session_ids: tuple[str, ...]


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
    
    tickets_deferred = (
        db.query(Ticket)
        .filter(Ticket.status == "deferred")
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
    deleted_session_ids = tuple(
        session_id
        for (session_id,) in db.query(UserSession.session_id)
        .order_by(UserSession.session_id)
        .all()
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
        tickets_deferred=tickets_deferred,
        sessions_deleted=sessions_deleted,
        deleted_session_ids=deleted_session_ids,
    )


async def notify_clients(deleted_session_ids: tuple[str, ...]) -> None:
    """Ask the running application to refresh all connected clients."""
    async with websockets.connect(
        CLOSE_DAY_WS_URL, open_timeout=5, close_timeout=2
    ) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "close_day_updated",
                    "deleted_session_ids": list(deleted_session_ids),
                }
            )
        )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Закрыть рабочий день сейчас или запланировать одноразовые закрытия."
    )
    parser.add_argument(
        "--schedule",
        action="append",
        nargs="?",
        const="",
        metavar='"ДД.ММ.ГГГГ ЧЧ:ММ"',
        help=(
            "запланировать одноразовое закрытие; повторите опцию для нескольких дат "
            "или не указывайте значение для интерактивного ввода"
        ),
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    if args.schedule is not None and not args.run_now:
        try:
            values = args.schedule
            if values == [""]:
                values = collect_interactive_schedule()
            elif "" in values:
                raise ValueError(
                    "пустой --schedule нельзя смешивать с датами; выберите один способ ввода"
                )
            scheduled = schedule_close_days(
                values,
                command=build_close_day_command(sys.executable, __file__),
            )
        except (RuntimeError, ValueError) as error:
            print(f"Ошибка планирования закрытия дня: {error}", file=sys.stderr)
            return 1

        for item in scheduled:
            print(f"Закрытие запланировано: {item.run_at:%d.%m.%Y в %H:%M} (Иркутск)")
        print("Каждое задание сработает один раз.")
        return 0

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
    print(f"Отложенных билетов отменено: {result.tickets_deferred}")
    print(f"Сессий операторов закрыто: {result.sessions_deleted}")

    try:
        asyncio.run(notify_clients(result.deleted_session_ids))
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
