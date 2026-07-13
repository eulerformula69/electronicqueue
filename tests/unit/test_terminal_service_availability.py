from pathlib import Path

from app.models import AVAILABLE_WINDOW_STATUSES


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_text(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_online_and_break_windows_keep_terminal_services_available():
    assert AVAILABLE_WINDOW_STATUSES == {"online", "break"}


def test_terminal_service_paths_share_available_window_statuses():
    services_router = read_text("app/routers/services.py")
    tickets_router = read_text("app/routers/tickets.py")
    operator_service = read_text("app/services/operators.py")

    assert services_router.count("Window.status.in_(AVAILABLE_WINDOW_STATUSES)") == 2
    assert tickets_router.count("Window.status.in_(AVAILABLE_WINDOW_STATUSES)") == 2
    assert "Window.status.in_(AVAILABLE_WINDOW_STATUSES)" in operator_service
    assert "service.id in available_service_ids" in operator_service
