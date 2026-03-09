import asyncio
import websockets 
import threading
import json


clients=set()
latest_data=None
async def handler(websocket):
    clients.add(websocket)
    global latest_data
    try:
        async for message in websocket:
            try:
                latest_data = json.loads(message)
            except json.JSONDecodeError:
                print("Invalid JSON received")
    finally:
        clients.remove(websocket)

async def send_data(data):
    if clients:
        await asyncio.gather(*(client.send(data) for client in clients))

async def receive_data():
    return latest_data
async def start_server():
    async with websockets.serve(handler,"localhost",8765):
        print("Websocket server started at ws://localhost:8765")
        await asyncio.Future()


def run_server():
    asyncio.run(start_server())

threading.Thread(target=run_server,daemon=True).start()



