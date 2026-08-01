from datetime import datetime

import pytest

from app.models import Ticket
from app.services.ticket_lifecycle import (
    InvalidTicketTransition,
    start_ticket_service,
)


def test_start_ticket_service_records_factual_start_time():
    started_at = datetime(2026, 8, 1, 12, 30)
    ticket = Ticket(
        id=1,
        status="called",
        operator_id=7,
        window_id=3,
        called_at=datetime(2026, 8, 1, 12, 29),
    )

    start_ticket_service(
        ticket,
        operator_id=7,
        window_id=3,
        now=started_at,
    )

    assert ticket.status == "serving"
    assert ticket.service_started_at == started_at


@pytest.mark.parametrize("status", ["waiting", "serving", "finished", "cancelled"])
def test_start_ticket_service_rejects_invalid_source_status(status):
    ticket = Ticket(id=1, status=status, operator_id=7, window_id=3)

    with pytest.raises(InvalidTicketTransition):
        start_ticket_service(ticket, operator_id=7, window_id=3)


def test_start_ticket_service_rejects_another_window():
    ticket = Ticket(id=1, status="called", operator_id=7, window_id=3)

    with pytest.raises(InvalidTicketTransition):
        start_ticket_service(ticket, operator_id=7, window_id=4)
