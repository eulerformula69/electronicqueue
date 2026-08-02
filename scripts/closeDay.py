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
    collect_interactive_schedule,
    parse_run_at,
    run_schedule,
)


@dataclass(frozen=True)
class CloseDayResult:
    windows_status_changed: int
    tickets_finished: int
    tickets_cancelled: int
    tickets_deferred: int
    sessions_deleted: int
    deleted_session_ids: tuple[str, ...]


def close_day(
    db,
    *,
    ticket_action: str,
    operator_action: str,
) -> CloseDayResult:
    """Apply all end-of-day changes atomically and return affected row counts."""
    if operator_action not in {"offline", "online", "break"}:
        raise ValueError(f"Неизвестное действие с операторами: {operator_action}")

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
    tickets_finished = 0
    tickets_cancelled = 0
    tickets_deferred = 0
    if ticket_action == "finish":
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
    elif ticket_action != "cancel":
        raise ValueError(f"Неизвестное действие с билетами: {ticket_action}")

    tickets_cancelled = (
        db.query(Ticket)
        .filter(
            Ticket.status.in_(
                ("waiting", "called")
                if ticket_action == "cancel"
                else ("waiting",)
            )
        )
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

    windows_status_changed = 0
    deleted_session_ids: tuple[str, ...] = ()
    sessions_deleted = 0
    if operator_action in {"offline", "break"}:
        operators = db.query(Operator).order_by(Operator.id).all()
        for operator in operators:
            record_operator_status(
                db, operator.id, operator.window_id, operator_action
            )

        windows_status_changed = (
            db.query(Window)
            .filter(or_(Window.status != operator_action, Window.status.is_(None)))
            .update({Window.status: operator_action}, synchronize_session=False)
        )

        if settings["hide_services_without_online_operators"]:
            db.query(Service).update(
                {Service.status: "inactive"}, synchronize_session=False
            )

    if operator_action == "offline":
        deleted_session_ids = tuple(
            session_id
            for (session_id,) in db.query(UserSession.session_id)
            .order_by(UserSession.session_id)
            .all()
        )
        sessions_deleted = db.query(UserSession).delete(synchronize_session=False)

    db.commit()
    return CloseDayResult(
        windows_status_changed=windows_status_changed,
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
        description=(
            "Закрыть рабочий день сейчас или по расписанию. "
            "Для запуска явно выберите действие с билетами и операторами."
        ),
        epilog=(
            "Пример: python scripts/closeDay.py "
            "--finish-tickets --operator-offline"
        ),
    )
    ticket_group = parser.add_mutually_exclusive_group(required=True)
    ticket_group.add_argument(
        "--finish-tickets",
        action="store_const",
        const="finish",
        dest="ticket_action",
        help="завершить обслуживаемые билеты, отменить ожидающие и отложенные",
    )
    ticket_group.add_argument(
        "--cancel-tickets",
        action="store_const",
        const="cancel",
        dest="ticket_action",
        help="отменить обслуживаемые, ожидающие и отложенные билеты",
    )
    operator_group = parser.add_mutually_exclusive_group(required=True)
    operator_group.add_argument(
        "--operator-offline",
        action="store_const",
        const="offline",
        dest="operator_action",
        help="перевести окна операторов в офлайн и закрыть их сессии",
    )
    operator_group.add_argument(
        "--operator-online",
        action="store_const",
        const="online",
        dest="operator_action",
        help="не менять статусы и сессии операторов",
    )
    operator_group.add_argument(
        "--operator-break",
        action="store_const",
        const="break",
        dest="operator_action",
        help="перевести окна операторов в перерыв, сохранив их сессии",
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
    return parser


def run_close_day_once(*, ticket_action: str, operator_action: str) -> int:
    """Close the current day immediately and notify connected clients."""
    db = SessionLocal()
    try:
        result = close_day(
            db,
            ticket_action=ticket_action,
            operator_action=operator_action,
        )
    except (SQLAlchemyError, ValueError) as error:
        db.rollback()
        print(f"Ошибка закрытия рабочего дня: {error}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print("Рабочий день закрыт.")
    print(
        f"Статус окон изменён на {operator_action}: "
        f"{result.windows_status_changed}"
    )
    print(f"Текущих билетов завершено: {result.tickets_finished}")
    print(f"Открытых билетов отменено: {result.tickets_cancelled}")
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


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    effective_argv = sys.argv[1:] if argv is None else argv
    if not effective_argv:
        parser.print_help()
        return 0
    args = parser.parse_args(effective_argv)
    close_day_once = lambda: run_close_day_once(
        ticket_action=args.ticket_action,
        operator_action=args.operator_action,
    )
    if args.schedule is not None:
        try:
            values = args.schedule
            if values == [""]:
                values = collect_interactive_schedule()
            elif "" in values:
                raise ValueError(
                    "пустой --schedule нельзя смешивать с датами; выберите один способ ввода"
                )
            run_times = [parse_run_at(value) for value in values]
        except ValueError as error:
            print(f"Ошибка планирования закрытия дня: {error}", file=sys.stderr)
            return 1

        print("Таймер запущен. Не закрывайте это окно до последнего закрытия.")
        try:
            return run_schedule(run_times, close_day_once)
        except KeyboardInterrupt:
            print("\nТаймер Close Day остановлен.")
            return 130

    return close_day_once()


if __name__ == "__main__":
    raise SystemExit(main())
