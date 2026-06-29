from datetime import datetime
from operator import eq, ge, lt

from app.models import Ticket
from app.routers.tickets import (
    COMPLETED_TODAY_TICKET_DETAIL,
    find_completed_today_ticket_by_number,
)


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
    def __init__(self, tickets):
        self._tickets = tickets

    def query(self, model):
        assert model is Ticket
        return FakeTicketQuery(self._tickets)


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
