from datetime import datetime, timedelta
from pathlib import Path

from app.models import Ticket
from app.services.tickets import called_ticket_wait_remaining_seconds


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_called_ticket_wait_is_enforced_from_server_time():
    now = datetime(2026, 7, 18, 12, 0, 0)
    ticket = Ticket(called_at=now - timedelta(seconds=45))

    assert called_ticket_wait_remaining_seconds(ticket, 180, now=now) == 135
    assert called_ticket_wait_remaining_seconds(
        ticket,
        180,
        now=now + timedelta(seconds=135),
    ) == 0


def test_ticket_without_called_at_has_no_artificial_wait():
    assert called_ticket_wait_remaining_seconds(Ticket(called_at=None), 180) == 0


def test_operator_restores_wait_and_service_timers_from_called_at():
    operator_source = read_text("queue/js/operator.js")
    timer_source = read_text("queue/js/operator-ticket-timers.js")
    html = read_text("queue/operator.html")

    assert "currentTicketCalledAt = parseTicketCalledAt(ticket);" in operator_source
    assert "calledTicketWaitRemainingSeconds" in timer_source
    assert "currentTicketCalledAt.getTime()" in timer_source
    assert "setInterval(updateCalledTicketTimers, 1000)" in timer_source
    assert 'id="service-timer-value"' in html
    assert 'id="service-timer" class="service-timer" aria-live="off" hidden' in html
    assert "serviceTimerContainer.hidden = !hasServerStartTime" in timer_source
    assert "ЗАВЕРШИТЬ (ЧЕРЕЗ" in timer_source


def test_finish_button_uses_wait_state_but_other_actions_do_not():
    state_source = read_text("queue/js/operator-ui-state.js")
    css = read_text("queue/css/operator.css")

    assert 'button.id === "finish-btn" && isCalledTicketWaitActive()' in state_source
    assert '"current-ticket-action-inactive"' in state_source
    assert ".current-ticket-action-inactive" in css


def test_admin_can_configure_called_ticket_min_wait():
    modern_source = read_text("queue/js/admin/views/settings.view.js")
    legacy_source = read_text("queue/js/admin/settings.js")

    for source in (modern_source, legacy_source):
        assert "called_ticket_min_wait_seconds" in source
        assert "3600" in source


def test_resume_deferred_response_immediately_contains_new_called_at():
    router_source = read_text("app/routers/tickets.py")
    resume_endpoint = router_source.split(
        'async def resume_operator_deferred_ticket', 1
    )[1].split('@router.get("/tickets/my-queue"', 1)[0]

    assert '"called_at": ticket.called_at' in resume_endpoint
