from typing import Set

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        # session_id -> websocket (для heartbeat/idle ливнеса)
        self.session_id_to_ws: dict[str, WebSocket] = {}
        # websocket object id -> session_id
        self.ws_id_to_session_id: dict[int, str] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        ws_id = id(websocket)
        session_id = self.ws_id_to_session_id.pop(ws_id, None)
        if session_id:
            # Убираем ливнес-маппинг при отключении сокета
            self.session_id_to_ws.pop(session_id, None)

    async def broadcast(self, message: dict):
        dead = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                dead.append(connection)

        for conn in dead:
            self.disconnect(conn)
    
    async def send_personal_message(self, message: dict, session_id: str):
        if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            try:
                await websocket.send_json(message)
            except Exception:
                # Если соединение мертво, просто игнорируем
                pass


class OperatorConnectionManager:
    def __init__(self):
        # ключ = operator_id, значение = WebSocket
        self.connections: dict[int, WebSocket] = {}

    async def connect(self, operator_id: int, websocket: WebSocket):
        await websocket.accept()
        self.connections[operator_id] = websocket

    def disconnect(self, operator_id: int):
        if operator_id in self.connections:
            del self.connections[operator_id]

    async def send_to_operator(self, operator_id: int, message: dict):
        ws = self.connections.get(operator_id)
        if ws:
            try:
                await ws.send_json(message)
            except:
                self.disconnect(operator_id)

    async def broadcast(self, message: dict):
        dead = []
        for operator_id, connection in self.connections.items():
            try:
                await connection.send_json(message)
            except:
                dead.append(operator_id)
        for oid in dead:
            self.disconnect(oid)

manager = ConnectionManager()
operatorManager = OperatorConnectionManager()
