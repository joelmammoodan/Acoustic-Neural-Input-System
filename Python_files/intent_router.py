import subprocess
import pyautogui

def route_intent(intent: str, text: str):
    if intent == "open_app":
        print("Routing to: Open Application")
        open_app(text)
    elif intent == "close_app":
        close_app(text)
        print("Routing to: Close Application")
    elif intent == "scroll":
        print("Routing to: Scroll")
        cursor_control(text)
    elif intent == "weather":
        print("Routing to: Weather Information")
    elif intent == "scroll_down":
        print("Routing to: Scroll Down")
    elif intent == "click_button":
        print("Routing to: Click Button")
    elif intent == "stop":
        print("Routing to: Stop")
    else:
        print(f"Unknown intent: {intent}")


def open_app(text: str):
    app_name = text.lower().replace("open", "").strip()
    print(f"Opening application: {app_name}")
    
    try:
        subprocess.Popen(app_name + ".exe")
    except FileNotFoundError:
        print(f"Application not found: {app_name}")

def close_app(text: str):
    app_name = text.lower().replace("close", "").strip()
    try:
        subprocess.run(["taskkill", "/f", "/im", app_name + ".exe"], check=True)
    except subprocess.CalledProcessError:
        print(f"Failed to close application: {app_name}")


def cursor_control(text: str):
    direction = text.lower().replace("scroll", "").strip()
    print(f"Scrolling {direction}")
    if direction == "down":
        pyautogui.moveRel(0, 100)  # Scroll down by 100 pixels
    elif direction == "up":
        pyautogui.moveRel(0, -100)   # Scroll up by 100 pixels
    elif direction == "left":
        pyautogui.moveRel(-100, 0)  # Scroll left by 100 pixels
    elif direction == "right":
        pyautogui.moveRel(100, 0)   # Scroll right by 100 pixels    