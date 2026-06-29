from datetime import datetime
from types import SimpleNamespace

from app.routers.tickets import build_operator_queue_ticket_payload


def make_queue_ticket(**kwargs):
    defaults = {
        "id": 1,
        "number": 101,
        "service_id": 7,
        "service_name": "Consultation",
        "created_at": datetime(2026, 6, 29, 10, 30),
        "priority": 1,
        "target_window_id": 3,
        "completion_reason": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_operator_choice_ticket_is_not_marked_as_redirected():
    ticket = make_queue_ticket(
        target_window_id=3,
        completion_reason=None,
    )

    payload = build_operator_queue_ticket_payload(ticket, operator_window_id=3)

    assert payload["target_window_id"] == 3
    assert payload["is_redirected_to_window"] is False


def test_operator_redirected_ticket_is_marked_as_redirected():
    ticket = make_queue_ticket(
        target_window_id=3,
        completion_reason="redirected",
    )

    payload = build_operator_queue_ticket_payload(ticket, operator_window_id=3)

    assert payload["target_window_id"] == 3
    assert payload["is_redirected_to_window"] is True
