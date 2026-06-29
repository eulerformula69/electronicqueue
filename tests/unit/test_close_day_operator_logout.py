import json

import pytest

from app.connections import ConnectionManager
from scripts.closeDay import notify_clients


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
