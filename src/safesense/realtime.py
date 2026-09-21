from fastapi import WebSocket


class DashboardHub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def connect(self, socket: WebSocket) -> None:
        await socket.accept()
        self.clients.add(socket)

    def disconnect(self, socket: WebSocket) -> None:
        self.clients.discard(socket)

    async def broadcast(self, message: dict) -> None:
        for socket in list(self.clients):
            try:
                await socket.send_json(message)
            except Exception:
                self.disconnect(socket)


hub = DashboardHub()
