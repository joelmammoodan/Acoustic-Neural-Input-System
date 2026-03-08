import serial
import pyautogui
import time

SERIAL_PORT = "COM3"
BAUD_RATE = 115200

MOVE_AMOUNT = 2
SLOPE_THRESHOLD = 0.1
NEUTRAL_ZONE = 0.06   # Stop when signal returns near 0

ser = serial.Serial(SERIAL_PORT, BAUD_RATE)
pyautogui.PAUSE = 0
time.sleep(2)

prev_h = 0
prev_v = 0

move_state_x = 0   # -1 left, 1 right, 0 idle
move_state_y = 0   # -1 up, 1 down, 0 idle

print("Listening...")

while True:
    line = ser.readline().decode().strip()

    try:
        h_str, v_str = line.split(",")
        current_h = float(h_str)
        current_v = float(v_str)
    except:
        continue

    #to calculate slope
    slope_h = current_h - prev_h
    slope_v = current_v - prev_v

    #Horizontal State Control
    if move_state_x == 0:
        if slope_h > SLOPE_THRESHOLD:
            move_state_x = 1     # RIGHT
        elif slope_h < -SLOPE_THRESHOLD:
            move_state_x = -1    # LEFT
    else:
        # Stop when signal returns near zero
        if abs(current_h) < NEUTRAL_ZONE:
            move_state_x = 0

    #Vertical State Control
    if move_state_y == 0:
        if slope_v > SLOPE_THRESHOLD:
            move_state_y = -1    # UP (screen inverted)
        elif slope_v < -SLOPE_THRESHOLD:
            move_state_y = 1     # DOWN
    else:
        if abs(current_v) < NEUTRAL_ZONE:
            move_state_y = 0

    #Movement-
    move_x = move_state_x * MOVE_AMOUNT
    move_y = move_state_y * MOVE_AMOUNT

    if move_x != 0 or move_y != 0:
        pyautogui.moveRel(move_x, move_y)

    prev_h = current_h
    prev_v = current_v
