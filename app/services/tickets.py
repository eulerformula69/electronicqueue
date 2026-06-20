import asyncio
from datetime import datetime

from sqlalchemy import and_, asc, func, literal
from sqlalchemy.orm import Session

from app.connections import manager, operatorManager
from app.database import SessionLocal
from app.models import Operator, Service, Ticket, Window, WindowService
from app.services.settings import get_system_settings_dict


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
        Ticket.target_window_id.is_(None)
    ).order_by(Ticket.created_at.asc()).all()

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
        tickets = (
            db.query(Ticket, Service)
            .join(Service, Ticket.service_id == Service.id)
            .filter(Ticket.status == "waiting")
            .order_by(Ticket.created_at.asc())
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


async def broadcast_ticket_called(ticket: Ticket, window: Window):
    db = SessionLocal()
    try:
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
    finally:
        db.close()

    called_at_value = ticket.called_at
    if called_at_value:
        call_id = f"{ticket.id}:{called_at_value}"
    else:
        call_id = f"{ticket.id}:{datetime.now().timestamp()}"

    await manager.broadcast({
        "type": "ticket_called",
        "call_id": call_id,
        "ticket": {
            "id": ticket.id,
            "number": ticket.number,
            "window_name": window.name,
            "display_text": display_text,
            "tts_text": tts_text
        },
        "tts_text": tts_text
    })
