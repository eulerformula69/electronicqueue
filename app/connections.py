from typing import Set

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.session_id_to_ws: dict[str, WebSocket] = {}
        self.ws_id_to_session_id: dict[int, str] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        ws_id = id(websocket)
        session_id = self.ws_id_to_session_id.pop(ws_id, None)
        if session_id:
            self.session_id_to_ws.pop(session_id, None)

    async def broadcast(self, message: dict):
        dead = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)

        for connection in dead:
            self.disconnect(connection)

    async def send_personal_message(self, message: dict, session_id: str):
        websocket = self.session_id_to_ws.get(session_id)
        if not websocket:
            return

        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)

    async def send_to_sessions(self, session_ids: list[str], message: dict):
        for session_id in session_ids:
            await self.send_personal_message(message, session_id)


class OperatorConnectionManager:
    def __init__(self):
        self.connections: dict[int, WebSocket] = {}

    async def connect(self, operator_id: int, websocket: WebSocket):
        await websocket.accept()
        self.connections[operator_id] = websocket

    def disconnect(self, operator_id: int):
        if operator_id in self.connections:
            del self.connections[operator_id]

    async def send_to_operator(self, operator_id: int, message: dict):
        websocket = self.connections.get(operator_id)
        if not websocket:
            return

        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(operator_id)

    async def broadcast(self, message: dict):
        dead = []
        for operator_id, connection in self.connections.items():
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(operator_id)
        for operator_id in dead:
            self.disconnect(operator_id)


manager = ConnectionManager()
operatorManager = OperatorConnectionManager()
