import asyncio
import websockets 
import threading


clients=set()

async def handler(websocket):
    clients.add(websocket)
    try:
        async for message in websocket:
            print("Recieved from client:",message)
    finally:
        clients.remove(websocket)

async def send_data(data):
    if clients:
        await asyncio.gather(*(client.send(data) for client in clients))

async def start_server():
    async with websockets.serve(handler,"localhost",8765):
        print("Websocket server started at ws://localhost:8765")
        await asyncio.Future()


def run_server():
    asyncio.run(start_server())

threading.Thread(target=run_server,daemon=True).start()



