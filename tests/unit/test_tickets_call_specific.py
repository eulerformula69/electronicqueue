import asyncio
from datetime import datetime, timedelta
from operator import eq, ge, lt

from app.models import Operator, Service, Ticket, Window, WindowService
from app.routers import tickets as tickets_router
from app.routers.tickets import (
    COMPLETED_TODAY_TICKET_DETAIL,
    call_specific_ticket,
    find_completed_today_ticket_by_number,
)
from app.schemas import CallSpecificRequest


class FakeTicketQuery:
    def __init__(self, tickets):
        self._tickets = list(tickets)
        self._order_desc = False

    def filter(self, *conditions):
        tickets = self._tickets
        for condition in conditions:
            field = condition.left.name
            value = condition.right.value
            op = condition.operator

            if op is eq:
                tickets = [ticket for ticket in tickets if getattr(ticket, field) == value]
            elif op.__name__ == "in_op":
                tickets = [ticket for ticket in tickets if getattr(ticket, field) in value]
            elif op is ge:
                tickets = [ticket for ticket in tickets if getattr(ticket, field) >= value]
            elif op is lt:
                tickets = [ticket for ticket in tickets if getattr(ticket, field) < value]
            else:
                raise AssertionError(f"Unexpected operator in test query: {op}")

        self._tickets = tickets
        return self

    def order_by(self, *order):
        self._order_desc = True
        return self

    def first(self):
        tickets = self._tickets
        if self._order_desc:
            tickets = sorted(tickets, key=lambda ticket: ticket.finished_at, reverse=True)
        return tickets[0] if tickets else None


class FakeDb:
    def __init__(self, tickets, windows=None, window_services=None):
        self._tickets = tickets
        self._windows = windows or []
        self._window_services = window_services or []
        self.committed = False
        self.closed = False

    def query(self, model):
        if model is Ticket:
            return FakeTicketQuery(self._tickets)
        if model is Window:
            return FakeTicketQuery(self._windows)
        if model is WindowService:
            return FakeTicketQuery(self._window_services)
        raise AssertionError(f"Unexpected model in test query: {model}")

    def commit(self):
        self.committed = True

    def refresh(self, item):
        return item

    def close(self):
        self.closed = True


def make_ticket(number, finished_at, completion_reason="completed"):
    return Ticket(
        number=number,
        status="finished",
        completion_reason=completion_reason,
        finished_at=finished_at,
    )


def test_find_completed_today_ticket_by_number_finds_finished_completed_ticket():
    now = datetime(2026, 6, 29, 12, 0)
    completed_ticket = make_ticket(42, datetime(2026, 6, 29, 10, 0))
    cancelled_ticket = make_ticket(
        42,
        datetime(2026, 6, 29, 10, 10),
        completion_reason="cancelled",
    )

    result = find_completed_today_ticket_by_number(
        FakeDb([cancelled_ticket, completed_ticket]),
        42,
        now=now,
    )

    assert result is completed_ticket
    assert COMPLETED_TODAY_TICKET_DETAIL == (
        "Обслуживание этого клиента уже завершено. Вызвать талон не получится."
    )


def test_find_completed_today_ticket_by_number_ignores_yesterday_finished_ticket():
    now = datetime(2026, 6, 29, 12, 0)
    yesterday_ticket = make_ticket(42, datetime(2026, 6, 28, 10, 0))

    result = find_completed_today_ticket_by_number(
        FakeDb([yesterday_ticket]),
        42,
        now=now,
    )

    assert result is None


def test_call_specific_reopens_today_finished_completed_ticket(monkeypatch):
    now = datetime.now()
    service = Service(id=5, name="Consultation")
    ticket = Ticket(
        id=10,
        number=42,
        service_id=service.id,
        status="finished",
        completion_reason="completed",
        operator_id=1,
        window_id=11,
        target_window_id=99,
        created_at=now - timedelta(hours=2),
        called_at=now - timedelta(hours=1),
        finished_at=now - timedelta(minutes=5),
    )
    ticket.service = service
    window = Window(id=3, name="3")
    operator = Operator(id=7, window_id=window.id)
    db = FakeDb([ticket], windows=[window])
    broadcasts = []

    async def fake_broadcast_board():
        broadcasts.append(("board", None))

    async def fake_broadcast_ticket_called(called_ticket, called_window):
        broadcasts.append(("called", called_ticket, called_window))

    monkeypatch.setattr(tickets_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(tickets_router, "broadcast_board", fake_broadcast_board)
    monkeypatch.setattr(
        tickets_router,
        "broadcast_ticket_called",
        fake_broadcast_ticket_called,
    )

    response = asyncio.run(
        call_specific_ticket(CallSpecificRequest(number=42), operator=operator)
    )

    assert response == {
        "id": 10,
        "number": 42,
        "status": "called",
        "service_name": "Consultation",
    }
    assert ticket.status == "called"
    assert ticket.completion_reason is None
    assert ticket.operator_id == operator.id
    assert ticket.window_id == operator.window_id
    assert ticket.target_window_id is None
    assert ticket.called_at is not None
    assert ticket.finished_at is None
    assert db.committed is True
    assert db.closed is True
    assert broadcasts == [("board", None), ("called", ticket, window)]
