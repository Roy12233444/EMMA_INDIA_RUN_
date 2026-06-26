import asyncio
import websockets
import json
import sys

async def test_websocket_client():
    uri = "ws://localhost:8000/ws/terminal"
    print(f"Connecting to EMMA WebSocket server at {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("[OK] Handshake successful! Connection established.")
            
            # Send an initial control test command to the server
            test_command = {"type": "command", "command": "TEST_LOG_STREAM_KICKOFF"}
            print(f"Sending test trigger command: {test_command}")
            await websocket.send(json.dumps(test_command))
            
            ping_count = 0
            while True:
                # Wait to receive a frame from the server
                message_raw = await websocket.recv()
                message = json.loads(message_raw)
                print(f"[RECV] Received frame from server: {message}")
                
                # Check for server's periodic ping
                if message.get("type") == "ping":
                    ping_count += 1
                    print(f"   [Heartbeat] Server ping #{ping_count} detected.")
                    
                    # Respond with pong frame to keep connection active
                    pong_frame = {"type": "pong"}
                    print("   [Heartbeat] Sending pong response...")
                    await websocket.send(json.dumps(pong_frame))
                    
                    # Stop test after verifying 3 successful heartbeats
                    if ping_count >= 3:
                        print("\n[OK] Successfully verified 3 round-trip heartbeats. Closing connection...")
                        break
                
                elif message.get("type") == "info":
                    print(f"   [Server Info]: {message.get('message')}")
                    
    except websockets.exceptions.ConnectionClosedOK:
        print("[OK] Connection closed gracefully.")
    except ConnectionRefusedError:
        print("[ERROR] Server connection refused. Is FastAPI running on port 8000?")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(test_websocket_client())
    except KeyboardInterrupt:
        print("\nTest cancelled by user.")
