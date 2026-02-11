from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.connections: dict[int, list[WebSocket]] = {}

    async def connect(self, patient_id: int, ws: WebSocket):
        await ws.accept()
        self.connections.setdefault(patient_id, []).append(ws)

    def disconnect(self, patient_id: int, ws: WebSocket):
        conns = self.connections.get(patient_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, patient_id: int, data: dict):
        for ws in self.connections.get(patient_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(patient_id, ws)


manager = ConnectionManager()
