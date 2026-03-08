import subprocess
import time
import pyautogui
import pygetwindow as gw

# Path to your text file
file_path = r"C:\Users\LEGION\Documents\beemoviescript.txt"

# Open file in Notepad
subprocess.Popen(["notepad.exe", file_path])

# Wait for Notepad to open
time.sleep(2)

# Find the Notepad window
windows = gw.getWindowsWithTitle("Notepad")
if not windows:
    print("Notepad window not found")
    exit()

notepad = windows[0]

# Bring it to front
notepad.activate()
time.sleep(1)

# Click inside text area (important for scrolling)
pyautogui.click(notepad.left + 200, notepad.top + 200)

# Scroll down
pyautogui.scroll(-800)

# Scroll up
# pyautogui.scroll(800)
