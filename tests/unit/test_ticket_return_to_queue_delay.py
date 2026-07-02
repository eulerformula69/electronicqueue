from datetime import datetime, timedelta

from app.models import Ticket
from app.routers import tickets as tickets_router
from app.services import tickets as ticket_service
from app.services.tickets import (
    RETURN_TO_QUEUE_DELAY_MINUTES,
    create_window_redirect_ticket,
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
        returned_to_queue_count=0,
    )

    was_returned_before = return_ticket_to_queue(ticket, now=now)

    assert RETURN_TO_QUEUE_DELAY_MINUTES == 15
    assert was_returned_before is False
    assert ticket.status == "waiting"
    assert ticket.completion_reason is None
    assert ticket.operator_id is None
    assert ticket.window_id is None
    assert ticket.target_window_id is None
    assert ticket.called_at is None
    assert ticket.finished_at is None
    assert ticket.queue_entered_at == now + timedelta(minutes=15)
    assert ticket.returned_to_queue_count == 1


def test_return_ticket_to_queue_reports_repeated_return_from_shared_ticket_state():
    now = datetime(2026, 7, 1, 10, 0)
    ticket = Ticket(status="called", returned_to_queue_count=1)

    was_returned_before = return_ticket_to_queue(ticket, now=now)

    assert was_returned_before is True
    assert ticket.returned_to_queue_count == 2


def test_create_window_redirect_ticket_preserves_finished_source_stage():
    called_at = datetime(2026, 7, 2, 12, 25)
    redirected_at = datetime(2026, 7, 2, 12, 30)
    ticket = Ticket(
        id=1771,
        number=119,
        service_id=2,
        status="called",
        completion_reason=None,
        root_ticket_id=None,
        operator_id=None,
        window_id=7,
        target_window_id=None,
        created_at=datetime(2026, 7, 2, 12, 14),
        queue_entered_at=datetime(2026, 7, 2, 12, 14),
        called_at=called_at,
        finished_at=None,
    )

    redirected_ticket = create_window_redirect_ticket(
        ticket,
        target_window_id=19,
        operator_id=5,
        now=redirected_at,
    )

    assert ticket.status == "finished"
    assert ticket.completion_reason == "redirected"
    assert ticket.root_ticket_id == 1771
    assert ticket.operator_id == 5
    assert ticket.window_id == 7
    assert ticket.target_window_id == 19
    assert ticket.called_at == called_at
    assert ticket.finished_at == redirected_at

    assert redirected_ticket.number == 119
    assert redirected_ticket.service_id == 2
    assert redirected_ticket.status == "waiting"
    assert redirected_ticket.completion_reason == "redirected"
    assert redirected_ticket.root_ticket_id == 1771
    assert redirected_ticket.operator_id is None
    assert redirected_ticket.window_id is None
    assert redirected_ticket.target_window_id == 19
    assert redirected_ticket.created_at == redirected_at
    assert redirected_ticket.queue_entered_at == redirected_at
    assert redirected_ticket.called_at is None
    assert redirected_ticket.finished_at is None


def test_next_ticket_query_does_not_hide_delayed_returned_tickets():
    assert not hasattr(ticket_service, "queue_available_condition")
    assert "queue_available_condition" not in tickets_router.call_next_ticket.__code__.co_names
