import serial
import pyautogui
import asyncio
import json
import time

import WebSocket_broadcast as ws  # your WebSocket module

SERIAL_PORT = "COM3"
BAUD_RATE = 115200

MOVE_AMOUNT = 2
SLOPE_THRESHOLD = 0.1
NEUTRAL_ZONE = 0.06
SEND_INTERVAL = 1/120 # 60 Hz

pyautogui.PAUSE = 0

# Track previous values
prev_h = 0
prev_v = 0
move_state_x = 0
move_state_y = 0

Stat = 'ERROR'
dir_x = "CENTRE"
dir_y = "CENTRE"

print("Listening...")

async def read_and_send():
    global prev_h, prev_v, move_state_x, move_state_y, Stat, dir_x, dir_y
    ser = None
    last_send_time = time.time()

    while True:
        # Connect to serial if not connected
        if ser is None or not ser.is_open:
            try:
                ser = serial.Serial(SERIAL_PORT, BAUD_RATE)
                print("Serial connected")
                Stat = 'ACTIVE'
            except serial.SerialException:
                Stat = 'ERROR'
                dir_x = "CENTRE"
                dir_y = "CENTRE"
                data = {"stat": Stat, "h": -1, "v": -1, "dir_x": dir_x, "dir_y": dir_y}
                try:
                    await ws.send_data(json.dumps(data))
                except:
                    pass
                await asyncio.sleep(0.5)
                continue

        # Read line from serial in a thread to avoid blocking
        try:
            line = await asyncio.to_thread(ser.readline)
            line = line.decode(errors='ignore').strip()
        except serial.SerialException:
            print("Serial disconnected, retrying...")
            ser.close()
            ser = None
            continue

        # Parse data
        try:
            h_str, v_str = line.split(",")
            current_h = float(h_str)
            current_v = float(v_str)
            Stat = 'ACTIVE'
        except Exception:
            Stat = 'ERROR'
            current_h = prev_h
            current_v = prev_v

        # Calculate slopes
        slope_h = current_h - prev_h
        slope_v = current_v - prev_v

        # Horizontal control
        if move_state_x == 0:
            if slope_h > SLOPE_THRESHOLD:
                dir_x = 'RIGHT'
                move_state_x = 1
            elif slope_h < -SLOPE_THRESHOLD:
                dir_x = 'LEFT'
                move_state_x = -1
        else:
            if abs(current_h) < NEUTRAL_ZONE:
                dir_x = "CENTRE"
                move_state_x = 0

        # Vertical control
        if move_state_y == 0:
            if slope_v > SLOPE_THRESHOLD:
                dir_y = 'UP'
                move_state_y = -1
            elif slope_v < -SLOPE_THRESHOLD:
                dir_y = 'DOWN'
                move_state_y = 1
        else:
            if abs(current_v) < NEUTRAL_ZONE:
                dir_y = "CENTRE"
                move_state_y = 0

        # Move cursor
        move_x = move_state_x * MOVE_AMOUNT
        move_y = move_state_y * MOVE_AMOUNT
        if move_x != 0 or move_y != 0:
            pyautogui.moveRel(move_x, move_y)

        # Send data at 60Hz
        now = time.time()
        if now - last_send_time >= SEND_INTERVAL:
            data = {
                "stat": Stat,
                "h": current_h,
                "v": current_v,
                "dir_x": dir_x,
                "dir_y": dir_y,
            }
            try:
                await ws.send_data(json.dumps(data))
                print("data sent")
            except:
                pass
            last_send_time = now

        # Update previous values
        prev_h = current_h
        prev_v = current_v

        # Small sleep to yield control
        await asyncio.sleep(0)

# Run the async loop
asyncio.run(read_and_send())