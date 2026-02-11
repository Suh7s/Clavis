from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.patient_connections: dict[int, list[WebSocket]] = {}
        self.department_connections: dict[str, list[WebSocket]] = {}
        self.status_connections: list[WebSocket] = []

    async def connect(self, patient_id: int, ws: WebSocket):
        await self.connect_patient(patient_id, ws)

    async def connect_patient(self, patient_id: int, ws: WebSocket):
        await ws.accept()
        self.patient_connections.setdefault(patient_id, []).append(ws)

    def disconnect(self, patient_id: int, ws: WebSocket):
        self.disconnect_patient(patient_id, ws)

    def disconnect_patient(self, patient_id: int, ws: WebSocket):
        conns = self.patient_connections.get(patient_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns and patient_id in self.patient_connections:
            del self.patient_connections[patient_id]

    async def broadcast(self, patient_id: int, data: dict):
        await self.broadcast_patient(patient_id, data)

    async def broadcast_patient(self, patient_id: int, data: dict):
        for ws in list(self.patient_connections.get(patient_id, [])):
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect_patient(patient_id, ws)

    async def connect_department(self, department: str, ws: WebSocket):
        await ws.accept()
        key = department.strip().casefold()
        self.department_connections.setdefault(key, []).append(ws)

    def disconnect_department(self, department: str, ws: WebSocket):
        key = department.strip().casefold()
        conns = self.department_connections.get(key, [])
        if ws in conns:
            conns.remove(ws)
        if not conns and key in self.department_connections:
            del self.department_connections[key]

    async def broadcast_department(self, department: str, data: dict):
        key = department.strip().casefold()
        for ws in list(self.department_connections.get(key, [])):
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect_department(department, ws)

    async def connect_status(self, ws: WebSocket):
        await ws.accept()
        self.status_connections.append(ws)

    def disconnect_status(self, ws: WebSocket):
        if ws in self.status_connections:
            self.status_connections.remove(ws)

    async def broadcast_status(self, data: dict):
        for ws in list(self.status_connections):
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect_status(ws)


manager = ConnectionManager()
