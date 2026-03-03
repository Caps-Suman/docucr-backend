from fastapi import WebSocket
from typing import Dict, List
import json

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        try:
            print(f"WebSocketManager: Attempting to accept connection for user_id: {user_id}")
            await websocket.accept()
            print(f"WebSocketManager: Connection accepted for user_id: {user_id}")
            
            if user_id not in self.active_connections:
                self.active_connections[user_id] = []
            self.active_connections[user_id].append(websocket)
            print(f"WebSocketManager: Connection added to active connections for user_id: {user_id}")
            print(f"WebSocketManager: Total active connections: {len(self.active_connections)}")
        except Exception as e:
            print(f"WebSocketManager: Error accepting connection for user_id {user_id}: {str(e)}")
            import traceback
            print(f"WebSocketManager: Traceback: {traceback.format_exc()}")
            raise
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
            except ValueError:
                pass # Already removed
            
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
    
    async def send_personal_message(self, message: dict, user_id: str):
        if user_id in self.active_connections:
            # Iterate over a copy to safely remove items
            for connection in self.active_connections[user_id][:]:
                try:
                    await connection.send_text(json.dumps(message))
                except:
                    # Remove broken connections
                    try:
                        self.active_connections[user_id].remove(connection)
                    except ValueError:
                        pass
    
    async def broadcast_document_status(self, document_id: int, status: str, user_id: str, progress: int = 0, error_message: str = None):
        message = {
            "type": "document_status_update",
            "document_id": document_id,
            "status": status,
            "progress": progress,
            "error_message": error_message
        }
        await self.send_personal_message(message, user_id)

websocket_manager = WebSocketManager()