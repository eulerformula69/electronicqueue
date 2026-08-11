from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.models import Ticket
from app.routers.admin_tickets import serialize_ticket
from app.services.ticket_status import TicketStatusError, cancel_ticket


def make_ticket(status="waiting"):
    return SimpleNamespace(
        id=42,
        status=status,
        completion_reason=None,
        cancel_reason=None,
        finished_at=None,
        operator_id=None,
    )


def test_admin_cancel_updates_ticket_and_writes_audit():
    db = Mock()
    ticket = make_ticket("called")
    admin = SimpleNamespace(id=7, login="chief")

    previous = cancel_ticket(db, ticket, "  Ошибка регистрации  ", admin=admin)

    assert previous == "called"
    assert ticket.status == "cancelled"
    assert ticket.completion_reason == "cancelled"
    assert ticket.cancel_reason == "Ошибка регистрации"
    assert ticket.finished_at is not None
    audit = db.add.call_args.args[0]
    assert audit.ticket_id == 42
    assert audit.admin_id == 7
    assert audit.admin_login == "chief"
    assert audit.previous_status == "called"
    assert audit.new_status == "cancelled"


def test_cancel_rejects_completed_ticket():
    with pytest.raises(TicketStatusError, match="активный"):
        cancel_ticket(Mock(), make_ticket("finished"), "Причина")


def test_cancel_requires_reason():
    with pytest.raises(TicketStatusError, match="причину"):
        cancel_ticket(Mock(), make_ticket(), "   ")


def test_admin_ticket_payload_contains_readable_window_and_root_ticket_names():
    ticket = Ticket(id=42, number=108, status="waiting", target_window_id=3, root_ticket_id=9)

    payload = serialize_ticket(
        ticket,
        "Получение документов",
        None,
        None,
        "Окно 3",
        101,
    )

    assert payload["target_window_name"] == "Окно 3"
    assert payload["root_ticket_number"] == 101
