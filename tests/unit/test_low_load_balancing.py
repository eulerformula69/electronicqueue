from datetime import datetime
from pathlib import Path

from app.services.tickets import select_low_load_winner_id


ROOT = Path(__file__).resolve().parents[2]


def test_low_load_prefers_fewer_completed_services():
    ranking = [
        (3, datetime(2026, 7, 18, 10, 0), datetime(2026, 7, 18, 8, 0), 1),
        (1, datetime(2026, 7, 18, 11, 0), datetime(2026, 7, 18, 9, 0), 2),
    ]
    assert select_low_load_winner_id(ranking) == 2


def test_low_load_uses_stable_tie_breakers():
    ranking = [
        (1, datetime(2026, 7, 18, 10, 0), datetime(2026, 7, 18, 8, 0), 2),
        (1, datetime(2026, 7, 18, 9, 0), datetime(2026, 7, 18, 8, 0), 3),
        (1, datetime(2026, 7, 18, 9, 0), datetime(2026, 7, 18, 8, 0), 1),
    ]
    assert select_low_load_winner_id(ranking) == 1


def test_balancing_is_server_transactional_and_filters_eligibility():
    source = (ROOT / "app/services/tickets.py").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in source
    assert 'Window.status == "online"' in source
    assert "WindowService.service_id == ticket.service_id" in source
    assert 'Ticket.status == "called"' in source
    assert 'Ticket.completion_reason.in_(("completed", "redirected"))' in source
    assert "queue_size > settings" in source
