import asyncio
import websockets 
import serial


ser=serial.Serial("COM3",115200)

async def send_data(websocket):
    while True:
        line = ser.readline().decode().strip()
        await websocket.send(line)

async def main():
    async with websockets.serve(send_data,'localhost',8765):
        await asyncio.Future()
asyncio.run(main())




