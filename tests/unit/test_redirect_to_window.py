import asyncio
from operator import eq

import pytest
from fastapi import HTTPException

from app.models import Operator, Service, Ticket, Window, WindowService
from app.routers import tickets as tickets_router
from app.schemas import RedirectToWindowRequest


class FakeQuery:
    def __init__(self, items):
        self._items = list(items)

    def filter(self, *conditions):
        items = self._items
        for condition in conditions:
            field = condition.left.name
            value = condition.right.value
            op = condition.operator
            if op is not eq:
                raise AssertionError(f"Unexpected operator in test query: {op}")
            items = [item for item in items if getattr(item, field) == value]
        self._items = items
        return self

    def first(self):
        return self._items[0] if self._items else None


class FakeDb:
    def __init__(self, *, tickets, windows, services, window_services):
        self._tickets = tickets
        self._windows = windows
        self._services = services
        self._window_services = window_services
        self.added = []
        self.committed = False
        self.closed = False

    def query(self, model):
        if model is Ticket:
            return FakeQuery(self._tickets)
        if model is Window:
            return FakeQuery(self._windows)
        if model is Service:
            return FakeQuery(self._services)
        if model is WindowService:
            return FakeQuery(self._window_services)
        raise AssertionError(f"Unexpected model in test query: {model}")

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed = True

    def refresh(self, item):
        return item

    def close(self):
        self.closed = True


def test_redirect_to_window_creates_ticket_for_selected_service(monkeypatch):
    source_ticket = Ticket(id=10, number=42, service_id=1, status="called", window_id=5)
    target_window = Window(id=7, name="Window 7", status="online")
    selected_service = Service(id=3, name="Selected", is_archived=0)
    operator = Operator(id=2, window_id=5)
    db = FakeDb(
        tickets=[source_ticket],
        windows=[target_window],
        services=[selected_service],
        window_services=[WindowService(window_id=7, service_id=3)],
    )
    broadcasts = []

    async def fake_broadcast(message):
        broadcasts.append(("queue", message))

    async def fake_broadcast_board():
        broadcasts.append(("board", None))

    monkeypatch.setattr(tickets_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(tickets_router.manager, "broadcast", fake_broadcast)
    monkeypatch.setattr(tickets_router, "broadcast_board", fake_broadcast_board)

    result = asyncio.run(
        tickets_router.redirect_ticket_to_window(
            RedirectToWindowRequest(ticket_id=10, window_id=7, new_service_id=3),
            operator=operator,
        )
    )

    redirected_ticket = result["ticket"]
    assert redirected_ticket.service_id == 3
    assert redirected_ticket.target_window_id == 7
    assert source_ticket.status == "finished"
    assert source_ticket.completion_reason == "redirected"
    assert db.added == [redirected_ticket]
    assert db.committed is True
    assert db.closed is True
    assert broadcasts == [("queue", {"type": "queue_updated"}), ("board", None)]


def test_redirect_to_window_rejects_service_not_supported_by_window(monkeypatch):
    source_ticket = Ticket(id=10, number=42, service_id=1, status="called", window_id=5)
    target_window = Window(id=7, name="Window 7", status="online")
    selected_service = Service(id=3, name="Selected", is_archived=0)
    operator = Operator(id=2, window_id=5)
    db = FakeDb(
        tickets=[source_ticket],
        windows=[target_window],
        services=[selected_service],
        window_services=[WindowService(window_id=7, service_id=99)],
    )

    monkeypatch.setattr(tickets_router, "SessionLocal", lambda: db)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            tickets_router.redirect_ticket_to_window(
                RedirectToWindowRequest(ticket_id=10, window_id=7, new_service_id=3),
                operator=operator,
            )
        )

    assert exc.value.status_code == 400
    assert db.added == []
    assert db.committed is False
    assert db.closed is True
