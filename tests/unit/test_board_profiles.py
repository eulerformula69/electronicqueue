from pathlib import Path

from app.models import Operator, Service, Ticket, Window
from app.services.tickets import build_ticket_called_event


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_board_html_loads_profiles_before_board_script():
    source = _read("queue/board.html")

    assert '<script src="/queue/js/board-profiles.js"></script>' in source
    assert source.index("/queue/js/board-profiles.js") < source.index("/queue/js/board.js")


def test_board_profiles_normalize_screen_values_and_enable_popup_only_for_screen_2():
    source = _read("queue/js/board-profiles.js")

    assert "const BOARD_PROFILES" in source
    assert "callPopup: false" in source
    assert "callHighlight: true" in source
    assert '"2": {' in source
    assert "callPopup: true" in source
    assert "callHighlight: false" in source
    assert 'value === "1"' in source
    assert 'return "default";' in source
    assert 'new URLSearchParams(window.location.search).get("screen")' in source


def test_board_popup_is_triggered_only_by_deduplicated_ticket_called_events_and_can_replace_highlight():
    source = _read("queue/js/board.js")

    ticket_called_index = source.index('if (data.type === "ticket_called")')
    duplicate_index = source.index("processedCallIds.has(data.call_id)", ticket_called_index)
    popup_index = source.index("window.BoardProfiles.handleTicketCalled(data)", ticket_called_index)
    recall_index = source.index('if (data.type === "recall_ticket" || data.ticket_number)')

    assert duplicate_index < popup_index < recall_index
    assert "window.BoardProfiles.handleTicketCalled(data)" in source
    assert "window.BoardProfiles.shouldHighlightCall()" in source


def test_board_popup_uses_safe_dom_text_assignment_and_auto_hides():
    source = _read("queue/js/board-profiles.js")

    assert "POPUP_DURATION_MS = 5500" in source
    assert ".textContent =" in source
    assert ".innerHTML" not in source
    assert "popup.classList.add(\"is-visible\")" in source
    assert "popup.hidden = true" in source


def test_ticket_called_payload_contains_popup_fields():
    ticket = Ticket(id=123, number=45, service_id=7, operator_id=12)
    window = Window(id=3, name="Окно 3")
    service = Service(id=7, name="Название услуги")
    operator = Operator(id=12, name="Имя оператора")
    settings = {
        "call_message_template": "Талон <number> к <window>",
        "board_ticket_template": "Билет <number> -> <window>",
    }

    payload = build_ticket_called_event(
        ticket,
        window,
        service=service,
        operator=operator,
        settings=settings,
        call_id="123:2026-07-10T10:00:00",
    )

    assert payload["type"] == "ticket_called"
    assert payload["ticket_id"] == 123
    assert payload["number"] == 45
    assert payload["service_id"] == 7
    assert payload["service_name"] == "Название услуги"
    assert payload["window_id"] == 3
    assert payload["window_name"] == "Окно 3"
    assert payload["operator_id"] == 12
    assert payload["operator_name"] == "Имя оператора"
    assert payload["ticket"]["service_name"] == "Название услуги"
    assert payload["ticket"]["operator_name"] == "Имя оператора"
