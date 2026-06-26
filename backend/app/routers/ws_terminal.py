from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
import asyncio
import json
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ws_terminal")

router = APIRouter()

class ConnectionManager:
    """Manages active WebSocket connections for the real-time EMMA terminal."""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accepts the handshake and registers the socket session."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Unregisters the socket session upon disconnect."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Active connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Sends a JSON frame to a single specific connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")

    async def broadcast(self, message: dict):
        """Broadcasts a JSON frame to all active client dashboards."""
        logger.debug(f"Broadcasting message to {len(self.active_connections)} clients")
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client session, pruning: {e}")
                self.disconnect(connection)

manager = ConnectionManager()

async def send_periodic_pings(websocket: WebSocket, interval: int = 5):
    """Sends lightweight heartbeat frames to prevent connection timeouts."""
    try:
        while True:
            await asyncio.sleep(interval)
            logger.debug("Sending server ping")
            await websocket.send_json({"type": "ping"})
    except asyncio.CancelledError:
        logger.debug("Ping-pong heartbeat task cancelled.")
    except Exception as e:
        logger.error(f"Error in ping task: {e}")

@router.websocket("/ws/terminal")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time terminal route streaming agent logs and actions."""
    await manager.connect(websocket)
    
    # Spawn background task to send pings every 5 seconds to keep connection alive
    ping_task = asyncio.create_task(send_periodic_pings(websocket, interval=5))
    
    try:
        while True:
            # Wait for any message sent from the client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                logger.info(f"Received message from client: {message}")
                
                # Check for standard client pong responses
                if message.get("type") == "pong":
                    logger.debug("Heartbeat pong received from client.")
                
                # Check for control commands sent from dashboard
                elif message.get("type") == "command":
                    cmd = message.get("command")
                    logger.info(f"Client trigger command received: {cmd}")
                    # Acknowledge command execution back to the client
                    await manager.send_personal_message(
                        {"type": "info", "message": f"Command received and acknowledged: {cmd}"},
                        websocket
                    )
            except json.JSONDecodeError:
                logger.warning("Client sent invalid non-JSON payload.")
                await manager.send_personal_message(
                    {"type": "error", "message": "Invalid JSON format received."},
                    websocket
                )
                
    except WebSocketDisconnect:
        logger.info("WebSocket disconnect initiated by client.")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Error in websocket loop: {e}")
        manager.disconnect(websocket)
    finally:
        # Cancel the heartbeat ping task to clean up resources
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass
