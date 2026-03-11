"""
intent_router.py — Maps intents to OS-level actions on Windows.

Click strategies (no Tesseract required)
─────────────────────────────────────────
1. Windows UI Automation (pywinauto) — queries the accessibility tree
2. Template image matching (pyautogui) — needs assets/<target>.png
3. Raw coordinate fallback — "click 500 300"
"""

import re
import subprocess
import time
import pyautogui
import numpy as np
from PIL import ImageGrab

# ── Confidence threshold ──────────────────────────────────────────────────────
# Intents below this score from the model are treated as unknown.
MIN_CONFIDENCE = 0.45

# ── App registry ──────────────────────────────────────────────────────────────
# Maps spoken name → executable name (used by close_app / open_app fallback).
APP_MAP: dict[str, str] = {
    "chrome":       "chrome.exe",
    "google chrome":"chrome.exe",
    "spotify":      "spotify.exe",
    "discord":      "discord.exe",
    "vscode":       "Code.exe",
    "vs code":      "Code.exe",
    "visual studio code": "Code.exe",
    "calculator":   "calc.exe",
    "notepad":      "notepad.exe",
    "vlc":          "vlc.exe",
    "terminal":     "wt.exe",
    "windows terminal": "wt.exe",
    "firefox":      "firefox.exe",
    "edge":         "msedge.exe",
    "microsoft edge": "msedge.exe",
    "explorer":     "explorer.exe",
    "file explorer": "explorer.exe",
    "paint":        "mspaint.exe",
    "word":         "WINWORD.EXE",
    "excel":        "EXCEL.EXE",
    "powerpoint":   "POWERPNT.EXE",
    "outlook":      "OUTLOOK.EXE",
    "task manager": "taskmgr.exe",
}

# Words to strip when extracting app names from speech
_NOISE_WORDS = {
    "open", "launch", "start", "run", "close", "quit", "exit", "kill", "shut",
    "the", "a", "an", "my", "please", "app", "application", "program",
    "browser", "editor", "player",
}


# ── Router ────────────────────────────────────────────────────────────────────

def route_intent(intent: str, text: str, confidence: float = 1.0) -> None:
    """
    Dispatch an intent to the appropriate handler.

    Parameters
    ----------
    intent     : classified intent label
    text       : normalized user utterance
    confidence : model confidence (1.0 for rule-based hits)
    """

    # Guard: low-confidence model predictions get dropped
    if confidence < MIN_CONFIDENCE and intent != "not_possible_yet":
        print(f"⚠️  Low confidence ({confidence:.2f}) for intent '{intent}' — ignoring.")
        return

    dispatch = {
        "open_app":        lambda: open_app(text),
        "close_app":       lambda: close_app(text),
        "click":           lambda: click_button(text),
        "scroll_up":       lambda: scroll(direction="up"),
        "scroll_down":     lambda: scroll(direction="down"),
        "type_text":       lambda: type_text(text),
        "press_key":       lambda: press_key(text),
        "screenshot":      lambda: take_screenshot(),
        "search":          lambda: web_search(text),
        "ui_list":         lambda: print("📋 UI list requested (implement in your UI layer)"),
        "not_possible_yet":lambda: print("🤷 Intent not supported yet."),
    }

    handler = dispatch.get(intent)
    if handler:
        print(f"▶  Routing → {intent}")
        try:
            handler()
        except Exception as exc:
            print(f"❌  Handler error for '{intent}': {exc}")
    else:
        print(f"❓  Unknown intent: '{intent}'")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_app_name(text: str) -> str:
    """
    Strip action verbs and noise words, return what's left as the app name.
    Also tries to match a known app name directly from the full text first.
    """
    # Try longest match against APP_MAP keys first
    lower = text.lower()
    for key in sorted(APP_MAP, key=len, reverse=True):
        if key in lower:
            return key

    # Fallback: remove noise words and return remainder
    words = [w for w in lower.split() if w not in _NOISE_WORDS]
    return " ".join(words).strip()


def _resolve_executable(app_name: str) -> str | None:
    """Return the executable string for a given spoken app name, or None."""
    return APP_MAP.get(app_name.lower())


# ── Handlers ──────────────────────────────────────────────────────────────────

def open_app(text: str) -> None:
    app_name = _extract_app_name(text)
    if not app_name:
        print("❌  No application name found in:", text)
        return

    exe = _resolve_executable(app_name) or app_name
    print(f"🚀  Opening: {exe}")
    try:
        subprocess.Popen(["start", "", exe], shell=True)
    except Exception as exc:
        print(f"❌  Failed to open '{exe}': {exc}")


def close_app(text: str) -> None:
    app_name = _extract_app_name(text)
    if not app_name:
        print("❌  No application name found in:", text)
        return

    exe = _resolve_executable(app_name)
    if not exe:
        print(f"❌  Unknown application: '{app_name}'. Add it to APP_MAP.")
        return

    print(f"🛑  Closing: {exe}")
    result = subprocess.run(
        ["taskkill", "/f", "/im", exe],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"✅  {app_name} closed.")
    else:
        print(f"⚠️  Could not close '{exe}': {result.stderr.strip()}")


def click_button(text: str) -> None:
    """
    Find and click a UI element using three strategies (no Tesseract needed):

    1. Windows UI Automation (pywinauto) — accessibility tree, runs with a
       hard timeout so it never blocks the transcription thread.
    2. pyautogui.locateOnScreen — template image in assets/<target>.png
    3. Raw coordinate fallback — "click 500 300"
    """
    import threading, os

    # ── Parse target label ────────────────────────────────────────────────────
    match = re.search(r"\b(?:click|press|tap|hit)\s+(.*)", text)
    raw_target = match.group(1).strip() if match else text.strip()

    # Strip leading prepositions/articles: "on", "the", "a", "an", "at", "in"
    raw_target = re.sub(r"^(on|the|an?|at|in)\s+", "", raw_target, flags=re.IGNORECASE).strip()
    target = raw_target
    print(f"🖱️  Looking for '{target}'…")

    # ── Strategy 3: raw coordinates ───────────────────────────────────────────
    coord_match = re.fullmatch(r"(\d+)[,\s]+(\d+)", target)
    if coord_match:
        x, y = int(coord_match.group(1)), int(coord_match.group(2))
        print(f"✅  Clicking coordinates ({x}, {y}).")
        pyautogui.click(x, y)
        return

    # ── Strategy 1: Windows UI Automation (with 4-second timeout) ────────────
    _uia_result: list[tuple[int, int] | None] = [None]

    def _uia_search():
        try:
            from pywinauto import Desktop
            desktop = Desktop(backend="uia")
            target_lower = target.lower()

            windows_to_search = []
            try:
                windows_to_search.append(desktop.window(active_only=True))
            except Exception:
                pass
            windows_to_search.extend(desktop.windows())

            for win in windows_to_search:
                try:
                    for ctrl in win.descendants():
                        try:
                            name = (ctrl.window_text() or "").strip().lower()
                            if name == target_lower or target_lower in name:
                                rect = ctrl.rectangle()
                                cx = (rect.left + rect.right) // 2
                                cy = (rect.top  + rect.bottom) // 2
                                _uia_result[0] = (cx, cy)
                                return
                        except Exception:
                            continue
                except Exception:
                    continue
        except ImportError:
            pass
        except Exception as exc:
            print(f"⚠️  UI Automation search error: {exc}")

    uia_thread = threading.Thread(target=_uia_search, daemon=True)
    uia_thread.start()
    uia_thread.join(timeout=4.0)   # never block transcription loop more than 4 s

    if _uia_result[0]:
        cx, cy = _uia_result[0]
        print(f"✅  UI Automation found '{target}' at ({cx}, {cy}) — clicking.")
        pyautogui.click(cx, cy)
        return

    if uia_thread.is_alive():
        print("⚠️  UI Automation timed out — trying template match.")

    # ── Strategy 2: template image matching ──────────────────────────────────
    asset_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "assets",
        f"{re.sub(r'[^a-z0-9_]', '_', target.lower())}.png",
    )
    if os.path.isfile(asset_path):
        try:
            location = pyautogui.locateOnScreen(asset_path, confidence=0.8)
            if location:
                cx, cy = pyautogui.center(location)
                print(f"✅  Template match for '{target}' at ({cx}, {cy}) — clicking.")
                pyautogui.click(cx, cy)
                return
        except Exception as exc:
            print(f"⚠️  Template match failed: {exc}")
    else:
        print(f"ℹ️  No asset image at '{asset_path}' (optional).")

    print(f"❌  Could not find '{target}' on screen via any strategy.")


def scroll(direction: str = "down", amount: int = 500) -> None:
    clicks = amount if direction == "up" else -amount
    pyautogui.scroll(clicks)
    print(f"🖱️  Scrolled {direction}.")


def type_text(text: str) -> None:
    # Strip the intent verb from what to type
    cleaned = re.sub(
        r"^\s*(type|write|enter|input)\s+", "", text, flags=re.IGNORECASE
    ).strip()
    if not cleaned:
        print("❌  Nothing to type.")
        return
    print(f"⌨️  Typing: {cleaned!r}")
    pyautogui.write(cleaned, interval=0.03)


def press_key(text: str) -> None:
    """
    Parse and execute a keyboard shortcut from natural language.
    Handles 'press ctrl c', 'press enter', 'ctrl shift t', etc.
    """
    cleaned = re.sub(
        r"^\s*(press\s+key|press|hotkey|shortcut)\s*", "", text, flags=re.IGNORECASE
    ).strip()

    # Map spoken modifiers to pyautogui key names
    _KEY_MAP = {
        "control": "ctrl", "cmd": "ctrl", "win": "win",
        "alt": "alt", "shift": "shift", "ctrl": "ctrl",
        "enter": "enter", "return": "enter", "escape": "esc",
        "space": "space", "tab": "tab", "backspace": "backspace",
        "delete": "delete", "home": "home", "end": "end",
        "up": "up", "down": "down", "left": "left", "right": "right",
    }

    tokens = cleaned.lower().replace("+", " ").split()
    keys   = [_KEY_MAP.get(t, t) for t in tokens if t]

    if not keys:
        print("❌  No keys found in:", text)
        return

    print(f"⌨️  Pressing: {' + '.join(keys)}")
    if len(keys) == 1:
        pyautogui.press(keys[0])
    else:
        pyautogui.hotkey(*keys)


def take_screenshot(save_path: str = "screenshot.png") -> None:
    img = ImageGrab.grab()
    img.save(save_path)
    print(f"📸  Screenshot saved to '{save_path}'.")


def web_search(text: str) -> None:
    query = re.sub(
        r"^\s*(search\s+(for|up)?|find|look\s+up|google)\s*",
        "", text, flags=re.IGNORECASE
    ).strip()
    if not query:
        print("❌  No search query found.")
        return
    import urllib.parse, webbrowser
    url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
    print(f"🔍  Searching: {query!r}")
    webbrowser.open(url)