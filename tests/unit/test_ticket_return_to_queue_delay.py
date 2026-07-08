from datetime import datetime, timedelta

import pytest

from app.models import Ticket
from app.routers import tickets as tickets_router
from app.schemas import CancelTicketRequest, DeferTicketRequest
from app.services import tickets as ticket_service
from app.services.tickets import (
    AUTO_CANCEL_RETURNED_TICKET_AFTER_MINUTES,
    RETURN_TO_QUEUE_DELAY_MINUTES,
    cancel_expired_returned_tickets,
    cancel_expired_returned_tickets_once,
    create_window_redirect_ticket,
    defer_ticket,
    resume_deferred_ticket,
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


def test_defer_ticket_keeps_ticket_owned_by_current_operator_and_window():
    now = datetime(2026, 7, 8, 10, 0)
    ticket = Ticket(
        status="called",
        completion_reason=None,
        operator_id=1,
        window_id=2,
        target_window_id=9,
        called_at=now - timedelta(minutes=4),
        finished_at=None,
    )

    defer_ticket(
        ticket,
        operator_id=7,
        window_id=3,
        reason="missing_document",
        now=now,
    )

    assert ticket.status == "deferred"
    assert ticket.completion_reason is None
    assert ticket.operator_id == 7
    assert ticket.window_id == 3
    assert ticket.target_window_id is None
    assert ticket.defer_reason == "missing_document"
    assert ticket.deferred_at == now
    assert ticket.called_at == now - timedelta(minutes=4)
    assert ticket.finished_at is None


def test_resume_deferred_ticket_returns_ticket_to_service_without_general_queue():
    now = datetime(2026, 7, 8, 10, 30)
    deferred_at = now - timedelta(minutes=10)
    ticket = Ticket(
        status="deferred",
        completion_reason=None,
        operator_id=7,
        window_id=3,
        target_window_id=None,
        defer_reason="pays",
        deferred_at=deferred_at,
        called_at=now - timedelta(minutes=20),
        finished_at=None,
    )

    resume_deferred_ticket(
        ticket,
        operator_id=7,
        window_id=3,
        now=now,
    )

    assert ticket.status == "called"
    assert ticket.completion_reason is None
    assert ticket.operator_id == 7
    assert ticket.window_id == 3
    assert ticket.target_window_id is None
    assert ticket.called_at == now
    assert ticket.defer_reason is None
    assert ticket.deferred_at is None
    assert ticket.finished_at is None


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


class FakeQuery:
    def __init__(self, tickets):
        self.tickets = tickets
        self.conditions = []

    def filter(self, *conditions):
        self.conditions.extend(conditions)
        return self

    def all(self):
        return [
            ticket for ticket in self.tickets
            if ticket.status == "waiting"
            and ticket.returned_to_queue_count == 1
            and ticket.queue_entered_at <= self._cutoff
        ]

    @property
    def _cutoff(self):
        cutoff_condition = self.conditions[-1]
        return cutoff_condition.right.value


class FakeDb:
    def __init__(self, tickets):
        self.tickets = tickets
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def query(self, model):
        assert model is Ticket
        return FakeQuery(self.tickets)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class ActiveTicketQuery:
    def __init__(self, ticket):
        self.ticket = ticket

    def filter(self, *conditions):
        return self

    def first(self):
        return self.ticket


class ActiveTicketDb:
    def __init__(self, ticket):
        self.ticket = ticket
        self.committed = False
        self.refreshed = None
        self.closed = False

    def query(self, model):
        assert model is Ticket
        return ActiveTicketQuery(self.ticket)

    def commit(self):
        self.committed = True

    def refresh(self, ticket):
        self.refreshed = ticket

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_cancel_ticket_accepts_other_comment_reason(monkeypatch):
    now = datetime(2026, 7, 8, 10, 0)
    ticket = Ticket(
        number=55,
        status="called",
        operator_id=7,
        window_id=3,
        called_at=now,
    )
    db = ActiveTicketDb(ticket)
    broadcasts = []
    board_updates = []

    async def fake_broadcast(message):
        broadcasts.append(message)

    async def fake_broadcast_board():
        board_updates.append(True)

    monkeypatch.setattr(tickets_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(tickets_router.manager, "broadcast", fake_broadcast)
    monkeypatch.setattr(tickets_router, "broadcast_board", fake_broadcast_board)

    result = await tickets_router.cancel_current_ticket(
        CancelTicketRequest(reason="Другое: клиент ушёл"),
        operator=type("Operator", (), {"id": 7, "window_id": 3})(),
    )

    assert result["cancel_reason"] == "Другое: клиент ушёл"
    assert ticket.cancel_reason == "Другое: клиент ушёл"
    assert ticket.status == "cancelled"
    assert ticket.completion_reason == "cancelled"
    assert db.committed is True
    assert db.refreshed is ticket
    assert db.closed is True
    assert broadcasts == [{"type": "queue_updated"}]
    assert board_updates == [True]


@pytest.mark.asyncio
async def test_defer_ticket_accepts_other_comment_reason(monkeypatch):
    now = datetime(2026, 7, 8, 10, 0)
    ticket = Ticket(
        number=56,
        status="called",
        operator_id=7,
        window_id=3,
        called_at=now,
    )
    db = ActiveTicketDb(ticket)
    broadcasts = []
    board_updates = []

    async def fake_broadcast(message):
        broadcasts.append(message)

    async def fake_broadcast_board():
        board_updates.append(True)

    monkeypatch.setattr(tickets_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(tickets_router.manager, "broadcast", fake_broadcast)
    monkeypatch.setattr(tickets_router, "broadcast_board", fake_broadcast_board)

    result = await tickets_router.defer_current_ticket(
        DeferTicketRequest(reason="Другое: клиент вернётся позже"),
        operator=type("Operator", (), {"id": 7, "window_id": 3})(),
    )

    assert result["defer_reason"] == "Другое: клиент вернётся позже"
    assert ticket.defer_reason == "Другое: клиент вернётся позже"
    assert ticket.status == "deferred"
    assert db.committed is True
    assert db.refreshed is ticket
    assert db.closed is True
    assert broadcasts == [{"type": "queue_updated"}]
    assert board_updates == [True]


def test_cancel_expired_returned_tickets_finishes_only_waiting_returned_ticket():
    now = datetime(2026, 7, 6, 10, 0)
    expired_returned = Ticket(
        status="waiting",
        returned_to_queue_count=1,
        queue_entered_at=now - timedelta(minutes=31),
    )
    fresh_returned = Ticket(
        status="waiting",
        returned_to_queue_count=1,
        queue_entered_at=now - timedelta(minutes=29),
    )
    ordinary_waiting = Ticket(
        status="waiting",
        returned_to_queue_count=0,
        queue_entered_at=now - timedelta(minutes=40),
    )

    cancelled_count = cancel_expired_returned_tickets(
        FakeDb([expired_returned, fresh_returned, ordinary_waiting]),
        now=now,
    )

    assert AUTO_CANCEL_RETURNED_TICKET_AFTER_MINUTES == 30
    assert cancelled_count == 1
    assert expired_returned.status == "finished"
    assert expired_returned.completion_reason == "cancelled"
    assert expired_returned.cancel_reason == "returned_timeout"
    assert expired_returned.finished_at == now

    assert fresh_returned.status == "waiting"
    assert fresh_returned.completion_reason is None
    assert fresh_returned.finished_at is None

    assert ordinary_waiting.status == "waiting"
    assert ordinary_waiting.completion_reason is None
    assert ordinary_waiting.finished_at is None


@pytest.mark.asyncio
async def test_cancel_expired_returned_tickets_once_broadcasts_after_cancellation(monkeypatch):
    now = datetime(2026, 7, 6, 10, 0)
    ticket = Ticket(
        status="waiting",
        returned_to_queue_count=1,
        queue_entered_at=now - timedelta(minutes=31),
    )
    db = FakeDb([ticket])
    broadcasts = []
    board_updates = []

    async def fake_broadcast(message):
        broadcasts.append(message)

    async def fake_broadcast_board():
        board_updates.append(True)

    monkeypatch.setattr(ticket_service, "SessionLocal", lambda: db)
    monkeypatch.setattr(ticket_service.manager, "broadcast", fake_broadcast)
    monkeypatch.setattr(ticket_service, "broadcast_board", fake_broadcast_board)

    cancelled_count = await cancel_expired_returned_tickets_once(now=now)

    assert cancelled_count == 1
    assert db.committed is True
    assert db.closed is True
    assert broadcasts == [{"type": "queue_updated"}]
    assert board_updates == [True]
