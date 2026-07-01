from datetime import datetime, timedelta

from app.models import Ticket
from app.routers import tickets as tickets_router
from app.services import tickets as ticket_service
from app.services.tickets import (
    RETURN_TO_QUEUE_DELAY_MINUTES,
    return_ticket_to_queue,
)


def test_return_ticket_to_queue_delays_ticket_by_15_minutes():
    now = datetime(2026, 7, 1, 10, 0)
    ticket = Ticket(
        status="called",
        completion_reason="completed",
        operator_id=7,
        window_id=3,
        target_window_id=4,
        called_at=now - timedelta(minutes=3),
        finished_at=now - timedelta(minutes=1),
        queue_entered_at=now - timedelta(minutes=10),
    )

    return_ticket_to_queue(ticket, now=now)

    assert RETURN_TO_QUEUE_DELAY_MINUTES == 15
    assert ticket.status == "waiting"
    assert ticket.completion_reason is None
    assert ticket.operator_id is None
    assert ticket.window_id is None
    assert ticket.target_window_id is None
    assert ticket.called_at is None
    assert ticket.finished_at is None
    assert ticket.queue_entered_at == now + timedelta(minutes=15)


def test_next_ticket_query_does_not_hide_delayed_returned_tickets():
    assert not hasattr(ticket_service, "queue_available_condition")
    assert "queue_available_condition" not in tickets_router.call_next_ticket.__code__.co_names
