"""
intent_router.py — Maps classified intents to OS-level actions on Windows.

Click strategies (no Tesseract required)
─────────────────────────────────────────
1. Windows UI Automation (pywinauto) — queries the accessibility tree
2. Template image matching (pyautogui) — needs assets/<target>.png
3. Raw coordinate fallback — "click 500 300"
"""

import os
import re
import threading
import subprocess
import urllib.parse
import webbrowser
import pyautogui
import numpy as np
from PIL import ImageGrab

# ── Confidence threshold ──────────────────────────────────────────────────────
MIN_CONFIDENCE = 0.55

# ── Compiled once at import — used in route_intent() ─────────────────────────
_CLICK_HERE_RE = re.compile(
    r"\b(click|tap|press)\s+(here|this|it|now)\b", re.IGNORECASE
)

# ── App registry ──────────────────────────────────────────────────────────────
APP_MAP: dict[str, str] = {
    "chrome":             "chrome.exe",
    "google chrome":      "chrome.exe",
    "spotify":            "spotify.exe",
    "discord":            "discord.exe",
    "vscode":             "Code.exe",
    "vs code":            "Code.exe",
    "visual studio code": "Code.exe",
    "calculator":         "calc.exe",
    "notepad":            "notepad.exe",
    "vlc":                "vlc.exe",
    "terminal":           "wt.exe",
    "windows terminal":   "wt.exe",
    "firefox":            "firefox.exe",
    "edge":               "msedge.exe",
    "microsoft edge":     "msedge.exe",
    "explorer":           "explorer.exe",
    "file explorer":      "explorer.exe",
    "paint":              "mspaint.exe",
    "word":               "WINWORD.EXE",
    "excel":              "EXCEL.EXE",
    "powerpoint":         "POWERPNT.EXE",
    "outlook":            "OUTLOOK.EXE",
    "task manager":       "taskmgr.exe",
}

_NOISE_WORDS = {
    "open", "launch", "start", "run", "close", "quit", "exit", "kill", "shut",
    "the", "a", "an", "my", "please", "app", "application", "program",
    "browser", "editor", "player",
}

# Key name normalisation — module-level so it's built once
_KEY_MAP: dict[str, str] = {
    "control": "ctrl", "cmd": "ctrl", "win": "win",
    "alt": "alt", "shift": "shift", "ctrl": "ctrl",
    "enter": "enter", "return": "enter", "escape": "esc",
    "space": "space", "tab": "tab", "backspace": "backspace",
    "delete": "delete", "home": "home", "end": "end",
    "up": "up", "down": "down", "left": "left", "right": "right",
}

# Screenshots saved next to this file
_HERE = os.path.dirname(os.path.abspath(__file__))


# ── Router ────────────────────────────────────────────────────────────────────

def route_intent(intent: str, text: str, confidence: float = 1.0) -> None:
    """Dispatch an intent to the appropriate OS-level handler."""

    # "click here" always fires immediately — bypasses confidence gate
    if _CLICK_HERE_RE.search(text):
        x, y = pyautogui.position()
        pyautogui.click(x, y)
        print(f"[CLICK HERE] Clicked at ({x}, {y})")
        return

    if confidence < MIN_CONFIDENCE:
        print(f"[WARN] Low confidence ({confidence:.2f}) for '{intent}' — ignoring.")
        return

    dispatch = {
        "open_app":    lambda: open_app(text),
        "close_app":   lambda: close_app(text),
        "click":       lambda: click_button(text),
        "click_here":  lambda: click_button(text),
        "scroll_up":   lambda: scroll(direction="up"),
        "scroll_down": lambda: scroll(direction="down"),
        "type_text":   lambda: type_text(text),
        "press_key":   lambda: press_key(text),
        "screenshot":  lambda: take_screenshot(),
        "search":      lambda: web_search(text),
    }

    handler = dispatch.get(intent)
    if handler:
        print(f"[->] Routing → {intent}")
        try:
            handler()
        except Exception as exc:
            print(f"[ERR] Handler error for '{intent}': {exc}")
    else:
        print(f"[?] Unknown intent: '{intent}'")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_app_name(text: str) -> str:
    lower = text.lower()
    # Check longest keys first so "google chrome" beats "chrome"
    for key in sorted(APP_MAP, key=len, reverse=True):
        if key in lower:
            return key
    words = [w for w in lower.split() if w not in _NOISE_WORDS]
    return " ".join(words).strip()


def _resolve_executable(app_name: str) -> str | None:
    return APP_MAP.get(app_name.lower())


# ── Handlers ──────────────────────────────────────────────────────────────────

def open_app(text: str) -> None:
    app_name = _extract_app_name(text)
    if not app_name:
        print("[ERR] No application name found in:", text)
        return
    exe = _resolve_executable(app_name) or app_name
    print(f"[OPEN] Opening: {exe}")
    try:
        subprocess.Popen(["start", "", exe], shell=True)
    except Exception as exc:
        print(f"[ERR] Failed to open '{exe}': {exc}")


def close_app(text: str) -> None:
    app_name = _extract_app_name(text)
    if not app_name:
        print("[ERR] No application name found in:", text)
        return
    exe = _resolve_executable(app_name)
    if not exe:
        print(f"[ERR] Unknown app: '{app_name}'. Add it to APP_MAP.")
        return
    print(f"[STOP] Closing: {exe}")
    result = subprocess.run(
        ["taskkill", "/f", "/im", exe],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"[OK] {app_name} closed.")
    else:
        print(f"[WARN] Could not close '{exe}': {result.stderr.strip()}")


def click_button(text: str) -> None:
    match = re.search(r"\b(?:click|press|tap|hit)\s+(.*)", text)
    raw_target = match.group(1).strip() if match else text.strip()
    raw_target = re.sub(r"^(on|the|an?|at|in)\s+", "", raw_target, flags=re.IGNORECASE).strip()
    target = raw_target
    print(f"[CLICK] Looking for '{target}'...")

    # Strategy 1 — raw coordinates e.g. "click 500 300"
    coord_match = re.fullmatch(r"(\d+)[,\s]+(\d+)", target)
    if coord_match:
        x, y = int(coord_match.group(1)), int(coord_match.group(2))
        print(f"[OK] Clicking coordinates ({x}, {y}).")
        pyautogui.click(x, y)
        return

    # Strategy 2 — Windows UI Automation
    _uia_result: list[tuple[int, int] | None] = [None]

    def _uia_search():
        try:
            from pywinauto import Desktop
            import win32gui
            desktop      = Desktop(backend="uia")
            target_lower = target.lower()

            # Search active window first (faster)
            try:
                hwnd       = win32gui.GetForegroundWindow()
                active_win = desktop.window(handle=hwnd)
                for ctrl in active_win.descendants():
                    try:
                        name = (ctrl.window_text() or "").strip().lower()
                        if name == target_lower or target_lower in name:
                            rect = ctrl.rectangle()
                            _uia_result[0] = (
                                (rect.left + rect.right)  // 2,
                                (rect.top  + rect.bottom) // 2,
                            )
                            return
                    except Exception:
                        continue
            except Exception:
                pass

            # Fallback — search all windows
            for win in desktop.windows():
                try:
                    for ctrl in win.descendants():
                        try:
                            name = (ctrl.window_text() or "").strip().lower()
                            if name == target_lower or target_lower in name:
                                rect = ctrl.rectangle()
                                _uia_result[0] = (
                                    (rect.left + rect.right)  // 2,
                                    (rect.top  + rect.bottom) // 2,
                                )
                                return
                        except Exception:
                            continue
                except Exception:
                    continue
        except ImportError:
            pass
        except Exception as exc:
            print(f"[WARN] UI Automation error: {exc}")

    uia_thread = threading.Thread(target=_uia_search, daemon=True)
    uia_thread.start()
    uia_thread.join(timeout=4.0)

    if _uia_result[0]:
        cx, cy = _uia_result[0]
        print(f"[OK] UI Automation found '{target}' at ({cx}, {cy}) — clicking.")
        pyautogui.click(cx, cy)
        return

    if uia_thread.is_alive():
        print("[WARN] UI Automation timed out — trying template match.")

    # Strategy 3 — template image match
    asset_path = os.path.join(
        _HERE, "assets",
        f"{re.sub(r'[^a-z0-9_]', '_', target.lower())}.png",
    )
    if os.path.isfile(asset_path):
        try:
            location = pyautogui.locateOnScreen(asset_path, confidence=0.8)
            if location:
                cx, cy = pyautogui.center(location)
                print(f"[OK] Template match for '{target}' at ({cx}, {cy}) — clicking.")
                pyautogui.click(cx, cy)
                return
        except Exception as exc:
            print(f"[WARN] Template match failed: {exc}")
    else:
        print(f"[INFO] No asset image at '{asset_path}' (optional).")

    print(f"[ERR] Could not find '{target}' on screen via any strategy.")


def scroll(direction: str = "down", amount: int = 500) -> None:
    clicks = amount if direction == "up" else -amount
    pyautogui.scroll(clicks)
    print(f"[SCROLL] Scrolled {direction}.")


def type_text(text: str) -> None:
    cleaned = re.sub(
        r"^\s*(type|write|enter|input)\s+", "", text, flags=re.IGNORECASE
    ).strip()
    if not cleaned:
        print("[ERR] Nothing to type.")
        return
    print(f"[KEY] Typing: {cleaned!r}")
    pyautogui.write(cleaned, interval=0.03)


def press_key(text: str) -> None:
    cleaned = re.sub(
        r"^\s*(press\s+key|press|hotkey|shortcut)\s*", "", text, flags=re.IGNORECASE
    ).strip()
    tokens = cleaned.lower().replace("+", " ").split()
    keys   = [_KEY_MAP.get(t, t) for t in tokens if t]
    if not keys:
        print("[ERR] No keys found in:", text)
        return
    print(f"[KEY] Pressing: {' + '.join(keys)}")
    if len(keys) == 1:
        pyautogui.press(keys[0])
    else:
        pyautogui.hotkey(*keys)


def take_screenshot(save_path: str = "") -> None:
    if not save_path:
        save_path = os.path.join(_HERE, "screenshot.png")
    img = ImageGrab.grab()
    img.save(save_path)
    print(f"[SHOT] Screenshot saved to '{save_path}'.")


def web_search(text: str) -> None:
    query = re.sub(
        r"^\s*(search\s+(for|up)?|find|look\s+up|google)\s*",
        "", text, flags=re.IGNORECASE
    ).strip()
    if not query:
        print("[ERR] No search query found.")
        return
    url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
    print(f"[SEARCH] Searching: {query!r}")
    webbrowser.open(url)