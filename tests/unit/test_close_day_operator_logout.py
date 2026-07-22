import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.connections import ConnectionManager
from scripts.closeDay import notify_clients
from scripts.close_day_schedule import parse_run_at, schedule_close_days


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.messages = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_connection_manager_sends_message_by_session_id():
    manager = ConnectionManager()
    websocket = FakeWebSocket()

    await manager.connect(websocket)
    manager.session_id_to_ws["operator-session"] = websocket
    manager.ws_id_to_session_id[id(websocket)] = "operator-session"

    await manager.send_to_sessions(
        ["operator-session", "missing-session"],
        {"type": "session_expired"},
    )

    assert websocket.messages == [{"type": "session_expired"}]


@pytest.mark.asyncio
async def test_close_day_notification_includes_deleted_operator_sessions(monkeypatch):
    sent_messages = []

    class FakeConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def send(self, message):
            sent_messages.append(message)

    monkeypatch.setattr(
        "scripts.closeDay.websockets.connect",
        lambda *args, **kwargs: FakeConnection(),
    )

    await notify_clients(("session-a", "session-b"))

    assert json.loads(sent_messages[0]) == {
        "type": "close_day_updated",
        "deleted_session_ids": ["session-a", "session-b"],
    }


def test_close_day_session_expiration_redirects_operator_without_browser_alert():
    websocket_source = (PROJECT_ROOT / "app/routers/websocket.py").read_text(
        encoding="utf-8"
    )
    operator_source = (PROJECT_ROOT / "queue/js/operator.js").read_text(
        encoding="utf-8"
    )

    assert '"silent": True' in websocket_source
    assert "if (options.silent)" in operator_source
    assert "OperatorFeedback.acknowledge" in operator_source
    assert "alert(" not in operator_source
    assert "handleExpiredSession(data.message, { silent: data.silent === true })" in operator_source


def test_parse_close_day_schedule_uses_irkutsk_time():
    run_at = parse_run_at(
        "24.07.2026 18:00",
        now=datetime(2026, 7, 22, 12, 0, tzinfo=ZoneInfo("Asia/Irkutsk")),
    )

    assert run_at.isoformat() == "2026-07-24T18:00:00+08:00"


def test_schedule_close_days_creates_one_at_job_per_date(monkeypatch):
    calls = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = "job 12 at Fri Jul 24 18:00:00 2026"

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Result()

    monkeypatch.setattr("scripts.close_day_schedule.shutil.which", lambda name: "/usr/bin/at")
    monkeypatch.setattr("scripts.close_day_schedule.subprocess.run", fake_run)

    scheduled = schedule_close_days(
        ["24.07.2026 18:00", "25.07.2026 14:00"],
        now=datetime(2026, 7, 22, 12, 0, tzinfo=ZoneInfo("Asia/Irkutsk")),
    )

    assert [call[0] for call in calls] == [
        ["at", "-t", "202607241800"],
        ["at", "-t", "202607251400"],
    ]
    assert all(
        call[1]["input"] == "/usr/local/bin/queue-close-day --run-now\n"
        for call in calls
    )
    assert [item.run_at.hour for item in scheduled] == [18, 14]


def test_schedule_rejects_past_date():
    with pytest.raises(ValueError, match="в будущем"):
        parse_run_at(
            "21.07.2026 18:00",
            now=datetime(2026, 7, 22, 12, 0, tzinfo=ZoneInfo("Asia/Irkutsk")),
        )
