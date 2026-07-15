from datetime import datetime, timedelta
from operator import eq, ge, lt

from app.models import Service, Ticket, Window
from app.routers.tickets import (
    build_operator_ticket_detail_payload,
    get_served_operator_tickets,
)
from app.services import tickets as ticket_services


class ServedTicketQuery:
    def __init__(self, tickets):
        self._tickets = list(tickets)

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
        self._tickets = sorted(
            self._tickets,
            key=lambda ticket: ticket.finished_at,
            reverse=True,
        )
        return self

    def all(self):
        return self._tickets


class ServedTicketDb:
    def __init__(self, tickets):
        self._tickets = tickets

    def query(self, model):
        assert model is Ticket
        return ServedTicketQuery(self._tickets)


def make_finished_ticket(number, *, reason, finished_at, window_id=3):
    service = Service(id=1, name="Consultation")
    ticket = Ticket(
        number=number,
        service_id=service.id,
        status="finished",
        completion_reason=reason,
        window_id=window_id,
        created_at=finished_at - timedelta(minutes=30),
        called_at=finished_at - timedelta(minutes=20),
        finished_at=finished_at,
    )
    ticket.service = service
    return ticket


def test_redirected_finished_ticket_is_in_served_operator_tickets():
    now = datetime(2026, 7, 8, 12, 0)
    redirected = make_finished_ticket(
        101,
        reason="redirected",
        finished_at=now - timedelta(minutes=5),
    )
    completed = make_finished_ticket(
        102,
        reason="completed",
        finished_at=now - timedelta(minutes=10),
    )
    cancelled = make_finished_ticket(
        103,
        reason="cancelled",
        finished_at=now - timedelta(minutes=1),
    )

    tickets = get_served_operator_tickets(
        ServedTicketDb([cancelled, completed, redirected]),
        window_id=3,
        today_start=now.replace(hour=0, minute=0, second=0, microsecond=0),
        tomorrow_start=now.replace(hour=0, minute=0, second=0, microsecond=0)
        + timedelta(days=1),
    )

    assert tickets == [redirected, completed]
    payload = build_operator_ticket_detail_payload(redirected)
    assert payload["status"] == "finished"
    assert payload["completion_reason"] == "redirected"
    assert payload["reason"] == "redirected"


class BoardTicketQuery:
    def __init__(self, rows):
        self._rows = list(rows)

    def join(self, *args, **kwargs):
        return self

    def outerjoin(self, *args, **kwargs):
        return self

    def filter(self, *conditions):
        rows = self._rows
        for condition in conditions:
            field = condition.left.name
            value = condition.right.value
            op = condition.operator

            if op.__name__ == "in_op":
                rows = [
                    (ticket, service, window)
                    for ticket, service, window in rows
                    if getattr(ticket, field) in value
                ]
            else:
                raise AssertionError(f"Unexpected operator in test query: {op}")

        self._rows = rows
        return self

    def order_by(self, *order):
        self._rows = sorted(
            self._rows,
            key=lambda row: (
                0 if row[0].status == "waiting" else 1,
                row[0].queue_entered_at or row[0].created_at,
            ),
        )
        return self

    def all(self):
        return self._rows


class BoardTicketDb:
    def __init__(self, rows):
        self._rows = rows
        self.closed = False

    def query(self, *models):
        assert models == (Ticket, Service, Window)
        return BoardTicketQuery(self._rows)

    def close(self):
        self.closed = True


def make_board_ticket(number, *, status, created_at):
    return Ticket(
        id=number,
        number=number,
        service_id=1,
        status=status,
        created_at=created_at,
        queue_entered_at=created_at,
    )


def test_deferred_tickets_are_in_board_waiting_payload_after_waiting(monkeypatch):
    service = Service(id=1, name="Consultation")
    now = datetime(2026, 7, 8, 12, 0)
    deferred = make_board_ticket(
        201,
        status="deferred",
        created_at=now - timedelta(minutes=30),
    )
    deferred.window_id = 7
    waiting = make_board_ticket(
        202,
        status="waiting",
        created_at=now - timedelta(minutes=5),
    )
    called = make_board_ticket(
        203,
        status="called",
        created_at=now - timedelta(minutes=40),
    )
    window = Window(id=7, name="Window 7")
    db = BoardTicketDb([
        (deferred, service, window),
        (waiting, service, None),
        (called, service, None),
    ])

    monkeypatch.setattr(ticket_services, "SessionLocal", lambda: db)

    payload = ticket_services.get_waiting_tickets_for_board()

    assert [ticket["number"] for ticket in payload] == [202, 201]
    assert [ticket["status"] for ticket in payload] == ["waiting", "deferred"]
    assert payload[0]["window_name"] is None
    assert payload[1]["window_name"] == "Window 7"
    assert db.closed is True
