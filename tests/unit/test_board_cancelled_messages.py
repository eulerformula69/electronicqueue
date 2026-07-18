from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_board_state_contains_temporary_cancelled_messages():
    source = read_text("app/services/tickets.py")
    assert '"cancelled": get_recent_cancelled_tickets_for_board()' in source
    assert 'Ticket.cancel_reason.in_(("no_show", "Клиент не явился"))' in source
    assert '"expires_at"' in source


def test_all_standard_board_profiles_merge_system_and_user_ticker_messages():
    ticker = read_text("queue/js/board-ticker.js")
    board = read_text("queue/js/board.js")
    lite = read_text("queue/js/board-lite.js")

    assert "tickerMessages.concat(systemMessages" in ticker
    assert "window.setBoardSystemMessages" in ticker
    assert "setTimeout" in ticker
    assert "setBoardSystemMessages" in board
    assert "setBoardSystemMessages" in lite
