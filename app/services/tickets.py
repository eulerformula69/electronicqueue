import asyncio
from datetime import datetime, timedelta

from sqlalchemy import and_, asc, case, func, literal
from sqlalchemy.orm import Session

from app.connections import manager, operatorManager
from app.database import SessionLocal
from app.models import Operator, Service, Ticket, Window, WindowService
from app.services.settings import get_system_settings_dict

RETURN_TO_QUEUE_DELAY_MINUTES = 15
AUTO_CANCEL_RETURNED_TICKET_AFTER_MINUTES = 30
AUTO_CANCEL_RETURNED_TICKETS_INTERVAL_SECONDS = 60


def queue_order_expr():
    return func.coalesce(Ticket.queue_entered_at, Ticket.created_at)


def return_ticket_to_queue(ticket: Ticket, *, now: datetime | None = None):
    returned_at = now or datetime.now()
    was_returned_before = (ticket.returned_to_queue_count or 0) > 0

    ticket.status = "waiting"
    ticket.completion_reason = None
    ticket.operator_id = None
    ticket.window_id = None
    ticket.target_window_id = None
    ticket.called_at = None
    ticket.finished_at = None
    ticket.defer_reason = None
    ticket.deferred_at = None
    ticket.cancel_reason = None
    ticket.queue_entered_at = returned_at + timedelta(minutes=RETURN_TO_QUEUE_DELAY_MINUTES)
    ticket.returned_to_queue_count = (ticket.returned_to_queue_count or 0) + 1

    return was_returned_before


def defer_ticket(
    ticket: Ticket,
    *,
    operator_id: int,
    window_id: int,
    reason: str,
    now: datetime | None = None,
) -> None:
    deferred_at = now or datetime.now()

    ticket.status = "deferred"
    ticket.completion_reason = None
    ticket.operator_id = operator_id
    ticket.window_id = window_id
    ticket.target_window_id = None
    ticket.defer_reason = reason
    ticket.deferred_at = deferred_at
    ticket.cancel_reason = None
    ticket.finished_at = None


def resume_deferred_ticket(
    ticket: Ticket,
    *,
    operator_id: int,
    window_id: int,
    now: datetime | None = None,
) -> None:
    called_at = now or datetime.now()

    ticket.status = "called"
    ticket.completion_reason = None
    ticket.operator_id = operator_id
    ticket.window_id = window_id
    ticket.target_window_id = None
    ticket.called_at = called_at
    ticket.finished_at = None
    ticket.defer_reason = None
    ticket.deferred_at = None
    ticket.cancel_reason = None


def cancel_expired_returned_tickets(db: Session, *, now: datetime | None = None) -> int:
    cancelled_at = now or datetime.now()
    cutoff = cancelled_at - timedelta(minutes=AUTO_CANCEL_RETURNED_TICKET_AFTER_MINUTES)

    tickets = db.query(Ticket).filter(
        Ticket.status == "waiting",
        Ticket.returned_to_queue_count == 1,
        Ticket.queue_entered_at <= cutoff,
    ).all()

    for ticket in tickets:
        ticket.status = "finished"
        ticket.completion_reason = "cancelled"
        ticket.cancel_reason = "returned_timeout"
        ticket.finished_at = cancelled_at

    return len(tickets)


async def cancel_expired_returned_tickets_once(
    *, now: datetime | None = None
) -> int:
    db = SessionLocal()
    try:
        cancelled_count = cancel_expired_returned_tickets(db, now=now)
        if cancelled_count:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if cancelled_count:
        await manager.broadcast({"type": "queue_updated"})
        await broadcast_board()

    return cancelled_count


async def auto_cancel_returned_tickets_worker(
    interval_seconds: int = AUTO_CANCEL_RETURNED_TICKETS_INTERVAL_SECONDS,
):
    while True:
        try:
            await cancel_expired_returned_tickets_once()
        except Exception:
            pass
        await asyncio.sleep(interval_seconds)


def create_window_redirect_ticket(
    ticket: Ticket,
    *,
    target_window_id: int,
    operator_id: int,
    service_id: int | None = None,
    now: datetime | None = None,
) -> Ticket:
    redirected_at = now or datetime.now()
    root_ticket_id = ticket.root_ticket_id or ticket.id

    ticket.root_ticket_id = root_ticket_id
    ticket.status = "finished"
    ticket.completion_reason = "redirected"
    if ticket.operator_id is None:
        ticket.operator_id = operator_id
    ticket.target_window_id = target_window_id
    ticket.finished_at = redirected_at

    return Ticket(
        number=ticket.number,
        service_id=service_id or ticket.service_id,
        status="waiting",
        completion_reason="redirected",
        root_ticket_id=root_ticket_id,
        operator_id=None,
        window_id=None,
        target_window_id=target_window_id,
        created_at=redirected_at,
        queue_entered_at=redirected_at,
        called_at=None,
        finished_at=None,
    )


def assign_ticket_to_least_loaded_window(db: Session, ticket: Ticket):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    candidates = (
        db.query(
            Window.id.label("window_id"),
            func.count(Ticket.id).label("served_count")
        )
        .join(Operator, Operator.window_id == Window.id)
        .join(WindowService, WindowService.window_id == Window.id)
        .outerjoin(
            Ticket,
            and_(
                Ticket.window_id == Window.id,
                Ticket.status == "finished",
                Ticket.finished_at >= today_start
            )
        )
        .filter(
            Window.status == "online",
            WindowService.service_id == ticket.service_id
        )
        .group_by(Window.id)
        .order_by(func.count(Ticket.id).asc(), Window.id.asc())
        .first()
    )

    ticket.window_id = candidates.window_id if candidates else None


async def reassign_waiting_tickets_from_window(db: Session, window_id: int):
    settings = get_system_settings_dict(db)

    if settings.get("queue_mode") != "dynamic_operator_distribution":
        return

    db.flush()

    tickets = db.query(Ticket).filter(
        Ticket.status == "waiting",
        Ticket.window_id == window_id,
        Ticket.target_window_id.is_(None)
    ).all()

    for ticket in tickets:
        ticket.window_id = None
        db.flush()
        assign_ticket_to_least_loaded_window(db, ticket)

    await manager.broadcast({
        "type": "queue_updated"
    })

    db.commit()


async def assign_unassigned_waiting_tickets(db: Session):
    settings = get_system_settings_dict(db)

    if settings.get("queue_mode") != "dynamic_operator_distribution":
        return

    tickets = db.query(Ticket).filter(
        Ticket.status == "waiting",
        Ticket.window_id.is_(None),
        Ticket.target_window_id.is_(None),
    ).order_by(queue_order_expr().asc()).all()

    for ticket in tickets:
        assign_ticket_to_least_loaded_window(db, ticket)


def get_called_tickets():
    db = SessionLocal()
    try:
        settings = get_system_settings_dict(db)

        tickets = (
            db.query(Ticket, Window)
            .join(Window, Ticket.window_id == Window.id)
            .filter(Ticket.status == "called")
            .order_by(Ticket.called_at.asc())
            .all()
        )

        result = []
        for ticket, window in tickets:
            result.append({
                "id": ticket.id,
                "number": ticket.number,
                "window_name": window.name,
                "display_text": render_ticket_template(
                    settings["board_ticket_template"],
                    ticket.number,
                    window.name
                ),
                "called_at": ticket.called_at.isoformat() if ticket.called_at else None
            })

        return result
    finally:
        db.close()


def get_waiting_tickets_for_board():
    db = SessionLocal()
    try:
        status_order = case(
            (Ticket.status == "waiting", 0),
            (Ticket.status == "deferred", 1),
            else_=2,
        )
        tickets = (
            db.query(Ticket, Service)
            .join(Service, Ticket.service_id == Service.id)
            .filter(Ticket.status.in_(("waiting", "deferred")))
            .order_by(status_order.asc(), queue_order_expr().asc())
            .all()
        )

        result = []
        for ticket, service in tickets:
            result.append({
                "id": ticket.id,
                "number": ticket.number,
                "service_id": ticket.service_id,
                "service_name": service.name,
                "window_id": ticket.window_id,
                "target_window_id": ticket.target_window_id,
                "status": ticket.status,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None
            })

        return result
    finally:
        db.close()


def get_board_state():
    return {
        "type": "board_state",
        "called": get_called_tickets(),
        "waiting": get_waiting_tickets_for_board()
    }


async def broadcast_board():
    board_state = get_board_state()
    for conn in manager.active_connections:
        try:
            await conn.send_json(board_state)
        except:
            pass


def render_ticket_template(template: str, ticket_number: int, window_name: str) -> str:
    template = template or ""
    return (
        template
        .replace("<number>", str(ticket_number))
        .replace("<window>", str(window_name))
    )


def build_ticket_tts_text(ticket_number: int, window_name: str) -> str:
    db = SessionLocal()
    try:
        settings = get_system_settings_dict(db)
        return render_ticket_template(
            settings["call_message_template"],
            ticket_number,
            window_name
        )
    finally:
        db.close()


def build_ticket_called_event(
    ticket: Ticket,
    window: Window,
    *,
    service: Service | None,
    settings: dict,
    call_id: str,
) -> dict:
    service_name = service.name if service else None
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

    ticket_payload = {
        "id": ticket.id,
        "number": ticket.number,
        "service_id": ticket.service_id,
        "service_name": service_name,
        "window_id": window.id,
        "window_name": window.name,
        "operator_id": ticket.operator_id,
        "display_text": display_text,
        "tts_text": tts_text
    }

    return {
        "type": "ticket_called",
        "call_id": call_id,
        "ticket_id": ticket.id,
        "number": ticket.number,
        "service_id": ticket.service_id,
        "service_name": service_name,
        "window_id": window.id,
        "window_name": window.name,
        "operator_id": ticket.operator_id,
        "ticket": ticket_payload,
        "tts_text": tts_text,
        "display_text": display_text,
    }


async def broadcast_ticket_called(ticket: Ticket, window: Window):
    db = SessionLocal()
    try:
        settings = get_system_settings_dict(db)
        service = db.query(Service).filter(Service.id == ticket.service_id).first()
    finally:
        db.close()

    called_at_value = ticket.called_at
    if called_at_value:
        call_id = f"{ticket.id}:{called_at_value}"
    else:
        call_id = f"{ticket.id}:{datetime.now().timestamp()}"

    await manager.broadcast(build_ticket_called_event(
        ticket,
        window,
        service=service,
        settings=settings,
        call_id=call_id,
    ))
