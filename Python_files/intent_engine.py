"""
Voice Command Intent Engine
============================
Replaces a rule-based engine with an LLM classifier.
Priority: Groq API → Ollama (local) → HuggingFace (local)

"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from functools import lru_cache
from typing import Optional
import httpx
from dotenv import load_dotenv
load_dotenv()
# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("intent_engine")

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
VALID_INTENTS = {
    "open_app", "close_app", "click", "click_here",
    "scroll_up", "scroll_down", "type_text",
    "press_key", "screenshot", "search", "none",
}

CONFIDENCE_THRESHOLD = 0.50      # Ignore results below this
GROQ_MODEL = "llama-3.1-8b-instant"
OLLAMA_MODEL         = "llama3"
OLLAMA_URL           = "http://localhost:11434/api/generate"
GROQ_URL             = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """You are a strict intent classifier for a voice command system.

VALID INTENTS (choose EXACTLY one):
open_app, close_app, click, click_here, scroll_up, scroll_down,
type_text, press_key, screenshot, search, none

RULES:
- Return ONLY valid JSON. No extra text, no markdown, no code fences.
- Never invent new intents.
- If unsure, use "none" with confidence 0.0.
- Extract "argument" only when clearly present; otherwise null.

OUTPUT FORMAT (strict):
{"intent": "<intent>", "argument": "<value or null>", "confidence": <0.0-1.0>}

EXAMPLES:
Input: "open chrome"      → {"intent": "open_app",    "argument": "chrome", "confidence": 0.95}
Input: "scroll down"      → {"intent": "scroll_down",  "argument": null,     "confidence": 0.98}
Input: "click here"       → {"intent": "click_here",   "argument": null,     "confidence": 0.95}
Input: "type hello world" → {"intent": "type_text",    "argument": "hello world", "confidence": 0.97}
Input: "take screenshot"  → {"intent": "screenshot",   "argument": null,     "confidence": 0.99}
Input: "search for cats"  → {"intent": "search",       "argument": "cats",   "confidence": 0.96}
Input: "uh okay yeah"     → {"intent": "none",         "argument": null,     "confidence": 0.0}
"""

NULL_INTENT = {"intent": "none", "argument": None, "confidence": 0.0}


# ──────────────────────────────────────────────
# 1.  LLM WRAPPER
# ──────────────────────────────────────────────

def _parse_json_safe(raw: str) -> Optional[dict]:
    """Extract and validate JSON from model output."""
    raw = raw.strip()
    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw)
        if data.get("intent") not in VALID_INTENTS:
            log.warning("Unknown intent '%s' – clamping to 'none'", data.get("intent"))
            data["intent"] = "none"
            data["confidence"] = 0.0
        return data
    except json.JSONDecodeError:
        return None


async def _call_groq(text: str, client: httpx.AsyncClient) -> Optional[dict]:
    api_key = os.getenv("GROQ_API_KEY", "")
    print("API KEY:", api_key[:8], "...")
    if not api_key:
        return None

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": text},
        ],
        "temperature": 0.0,
        "max_tokens": 80,
    }
    try:
        resp = await client.post(
            GROQ_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",  # ← ADD THIS
            },
            timeout=8.0,
        )
        print("GROQ RAW:", resp.text)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        return _parse_json_safe(raw)
    except Exception as exc:
        log.warning("Groq call failed: %s", exc)
        return None


async def _call_ollama(text: str, client: httpx.AsyncClient) -> Optional[dict]:
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"User command: {text}\n"
        "JSON response:"
    )
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 80},
    }
    try:
        resp = await client.post(OLLAMA_URL, json=payload, timeout=15.0)
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        return _parse_json_safe(raw)
    except Exception as exc:
        log.warning("Ollama call failed: %s", exc)
        return None



# Simple in-memory cache (avoids model calls for repeated commands)
_intent_cache: dict[str, dict] = {}


async def get_intent(text: str) -> dict:
    """
    Primary entry point.
    Tries Groq → Ollama → HuggingFace.
    Returns a validated intent dict.
    """
    text = text.strip().lower()
    if not text:
        return NULL_INTENT

    # Cache hit
    if text in _intent_cache:
        log.debug("Cache hit for '%s'", text)
        return _intent_cache[text]

    t0 = time.perf_counter()
    result: Optional[dict] = None

    async with httpx.AsyncClient() as client:
        result = await _call_groq(text, client)

    if result is None:
        log.warning("Groq failed — returning 'none'")
        result = NULL_INTENT

        if result is None:
            log.warning("Groq failed — returning 'none'")
            result = NULL_INTENT

    latency_ms = (time.perf_counter() - t0) * 1000
    log.info(
        "Intent='%s' arg='%s' conf=%.2f  text='%s'  latency=%.1f ms",
        result["intent"], result.get("argument"), result.get("confidence", 0),
        text, latency_ms,
    )

    # Cache and return
    _intent_cache[text] = result
    return result


# ──────────────────────────────────────────────
# 2.  ACTION HANDLERS  (stub implementations)
# ──────────────────────────────────────────────

def open_app(app_name: str):
    import subprocess, shutil
    log.info("[ACTION] open_app('%s')", app_name)
    if shutil.which(app_name):
        subprocess.Popen([app_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # Try xdg-open on Linux, 'open' on macOS, 'start' on Windows
        import platform, sys
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", app_name])
        elif sys.platform.startswith("win"):
            os.startfile(app_name)       # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", app_name])


def close_app(app_name: str):
    import subprocess, sys
    log.info("[ACTION] close_app('%s')", app_name)
    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/IM", f"{app_name}.exe", "/F"], check=False)
    else:
        subprocess.run(["pkill", "-f", app_name], check=False)


def click_button(label: Optional[str] = None):
    log.info("[ACTION] click at current position (label=%s)", label)
    try:
        import pyautogui  # type: ignore
        pyautogui.click()
    except ImportError:
        log.warning("pyautogui not installed — skipping click")


def scroll(direction: str):
    log.info("[ACTION] scroll %s", direction)
    try:
        import pyautogui  # type: ignore
        amount = 3 if direction == "up" else -3
        pyautogui.scroll(amount)
    except ImportError:
        log.warning("pyautogui not installed — skipping scroll")


def type_text(text: str):
    log.info("[ACTION] type_text('%s')", text)
    try:
        import pyautogui  # type: ignore
        pyautogui.typewrite(text, interval=0.03)
    except ImportError:
        log.warning("pyautogui not installed — skipping type_text")


def press_key(key: str):
    log.info("[ACTION] press_key('%s')", key)
    try:
        import pyautogui  # type: ignore
        pyautogui.hotkey(*key.split("+"))
    except ImportError:
        log.warning("pyautogui not installed — skipping press_key")


def take_screenshot():
    import datetime
    log.info("[ACTION] take_screenshot()")
    try:
        import pyautogui  # type: ignore
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"screenshot_{ts}.png"
        pyautogui.screenshot(path)
        log.info("Screenshot saved → %s", path)
    except ImportError:
        log.warning("pyautogui not installed — skipping screenshot")


def web_search(query: str):
    import webbrowser, urllib.parse
    log.info("[ACTION] web_search('%s')", query)
    url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
    webbrowser.open(url)


# ──────────────────────────────────────────────
# 3.  ROUTER
# ──────────────────────────────────────────────

def route(intent: str, argument: Optional[str], text: str):
    """Dispatch an intent to its handler."""
    arg = argument or text          # fall back to raw text when no arg extracted

    dispatch = {
        "open_app":    lambda: open_app(arg),
        "close_app":   lambda: close_app(arg),
        "click":       lambda: click_button(arg),
        "click_here":  lambda: click_button(None),
        "scroll_up":   lambda: scroll("up"),
        "scroll_down": lambda: scroll("down"),
        "type_text":   lambda: type_text(arg),
        "press_key":   lambda: press_key(arg),
        "screenshot":  lambda: take_screenshot(),
        "search":      lambda: web_search(arg),
        "none":        lambda: log.debug("Intent 'none' – no action taken"),
    }

    handler = dispatch.get(intent)
    if handler:
        handler()
    else:
        log.warning("Unknown intent '%s' — no handler registered", intent)


# ──────────────────────────────────────────────
# 4.  SAFETY LAYER  (thin wrapper over get_intent)
# ──────────────────────────────────────────────

async def process_command(text: str, threshold: float = CONFIDENCE_THRESHOLD) -> dict:
    """
    Full pipeline:
      text → get_intent (with 1 retry on bad JSON) → safety check → route
    Returns the intent dict for the caller.
    """
    result = await get_intent(text)

    # If we somehow got back invalid data, retry once
    if result.get("intent") not in VALID_INTENTS:
        log.warning("Invalid intent received, retrying…")
        _intent_cache.pop(text.strip().lower(), None)
        result = await get_intent(text)
        if result.get("intent") not in VALID_INTENTS:
            result = NULL_INTENT

    confidence = result.get("confidence", 0.0)
    if confidence < threshold:
        log.info(
            "Confidence %.2f below threshold %.2f — ignoring command '%s'",
            confidence, threshold, text,
        )
        return NULL_INTENT

    route(result["intent"], result.get("argument"), text)
    return result


# ──────────────────────────────────────────────
# 5.  CONVENIENCE: synchronous wrapper
# ──────────────────────────────────────────────

def run_command(text: str, threshold: float = CONFIDENCE_THRESHOLD) -> dict:
    """Synchronous entry point — useful for integration with non-async code."""
    return asyncio.run(process_command(text, threshold))


# ──────────────────────────────────────────────
# Example usage
# ──────────────────────────────────────────────

if __name__ == "__main__":
    TEST_COMMANDS = [
        "open chrome",
    ]

    print("\n" + "=" * 60)
    print("  Voice Command Intent Engine — Demo")
    print("=" * 60 + "\n")

    for cmd in TEST_COMMANDS:
        print(f"▶  Input : {cmd!r}")
        result = run_command(cmd)
        print(
            f"   Intent : {result['intent']}  |  "
            f"Arg: {result.get('argument')}  |  "
            f"Conf: {result.get('confidence', 0):.2f}"
        )
        print()