"""
assistant_mode.py
==================
Drop-in "Assistant Mode" for an existing voice automation pipeline.

Integrates with:
  - MicCapture      (already exists — not modified)
  - transcribe(audio) → str    (already exists — not modified)
  - intent_engine.process_command()  (already exists — not modified)

Adds:
  - Trigger detection  ("assistant" keyword in transcribed text)
  - Conversational loop backed by Groq LLM (llama-3.1-8b-instant)
  - LiveKit real-time data channel for text streaming
  - Graceful fallback when LiveKit / Groq are unavailable
  - Clean state machine with clear entry / exit transitions

Author : Senior AI Systems Engineer
Version: 1.0.0
"""

from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()
import asyncio
import pyttsx3
import json
import logging
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Deque, Optional

import httpx

# ──────────────────────────────────────────────────────────────────
# Logging  (inherits root config set by intent_engine; use own name)
# ──────────────────────────────────────────────────────────────────
log = logging.getLogger("assistant_mode")

# ──────────────────────────────────────────────────────────────────
# Configuration constants  (override via env vars in production)
# ──────────────────────────────────────────────────────────────────
GROQ_URL            = "https://api.groq.com/openai/v1/chat/completions"
GROQ_CHAT_MODEL     = "llama-3.1-8b-instant"
GROQ_MAX_TOKENS     = 512
GROQ_TEMPERATURE    = 0.7
GROQ_TIMEOUT        = 15.0          # seconds per request

MEMORY_WINDOW       = 5             # how many past turns to keep in context

LIVEKIT_URL         = os.getenv("LIVEKIT_URL",         "ws://localhost:7880")
LIVEKIT_API_KEY     = os.getenv("LIVEKIT_API_KEY",     "")
LIVEKIT_API_SECRET  = os.getenv("LIVEKIT_API_SECRET",  "")
LIVEKIT_ROOM        = os.getenv("LIVEKIT_ROOM",        "assistant-room")

# Phrases that end assistant mode (checked after lowercasing)
EXIT_PHRASES = frozenset([
    "stop assistant",
    "exit assistant",
    "exit assistant mode",
    "quit assistant",
    "goodbye assistant",
    "bye assistant",
])

# Fallback reply when Groq is unreachable
FALLBACK_REPLY = (
    "I'm sorry, I couldn't reach my language model right now. "
    "Please check your internet connection or API key and try again."
)

# System prompt that shapes the assistant's personality
ASSISTANT_SYSTEM_PROMPT = """You are a helpful, concise AI desktop assistant integrated into a voice command system.

Guidelines:
- Keep responses SHORT and conversational (1–3 sentences unless detail is explicitly needed).
- You are voice-first: avoid markdown, bullet lists, or code blocks unless asked.
- Be direct. The user is hands-free, so every extra word costs attention.
- If you don't know something, say so briefly.
- Never break character or discuss your underlying model.
"""


# ──────────────────────────────────────────────────────────────────
# 1. STATE  — single source of truth for assistant lifecycle
# ──────────────────────────────────────────────────────────────────

@dataclass
class AssistantState:
    """Tracks whether assistant mode is active and holds session metadata."""

    active:      bool                        = False
    session_id:  str                         = field(default_factory=lambda: uuid.uuid4().hex[:8])
    # Sliding window of {role, content} dicts — fed to Groq as context
    memory:      Deque[dict]                 = field(default_factory=lambda: deque(maxlen=MEMORY_WINDOW * 2))
    turn_count:  int                         = 0
    started_at:  Optional[float]             = None

    # ── convenience ──────────────────────────────────────────────

    def enter(self) -> None:
        self.active     = True
        self.started_at = time.perf_counter()
        self.turn_count = 0
        self.memory.clear()
        log.info("[State] ▶ assistant mode ON  (session=%s)", self.session_id)

    def exit(self) -> None:
        elapsed = (
            f"{time.perf_counter() - self.started_at:.1f}s"
            if self.started_at else "?"
        )
        log.info(
            "[State] ■ assistant mode OFF  (session=%s  turns=%d  elapsed=%s)",
            self.session_id, self.turn_count, elapsed,
        )
        self.active      = False
        self.started_at  = None
        # Regenerate session id for next activation
        self.session_id  = uuid.uuid4().hex[:8]

    def push_memory(self, role: str, content: str) -> None:
        """Append a message to the sliding window."""
        self.memory.append({"role": role, "content": content})

    @property
    def context_messages(self) -> list[dict]:
        """Return [system_prompt] + recent history ready for Groq."""
        return [{"role": "system", "content": ASSISTANT_SYSTEM_PROMPT}] + list(self.memory)


# Module-level singleton — the main pipeline checks / mutates this
_state = AssistantState()



class TTSEngine:
    def __init__(self):
        self.engine = None
        self.queue = asyncio.Queue()
        self.worker_task = None
        self.current_task = None

    def _init_engine(self):
        engine = pyttsx3.init()
        engine.setProperty('rate', 180)
        engine.setProperty('volume', 1.0)
        return engine

    def _speak_blocking(self, text):
        self.engine = self._init_engine()
        self.engine.say(text)
        self.engine.runAndWait()
        self.engine.stop()
        self.engine = None

    def stop(self):
        # 🔥 HARD RESET instead of soft stop
        if self.engine:
            try:
                self.engine.stop()
            except:
                pass
            self.engine = None

        # 🔥 cancel current speaking task
        if self.current_task:
            self.current_task.cancel()

    async def _worker(self):
        while True:
            text = await self.queue.get()

            # 🔥 kill any previous speech completely
            self.stop()

            self.current_task = asyncio.create_task(
                asyncio.to_thread(self._speak_blocking, text)
            )

            try:
                await self.current_task
            except asyncio.CancelledError:
                pass

            self.queue.task_done()

    def start(self):
        if self.worker_task is None:
            self.worker_task = asyncio.create_task(self._worker())

    async def speak(self, text):
        await self.queue.put(text)

tts_engine = TTSEngine()

def is_active() -> bool:
    """Public accessor so main.py can check state without importing internals."""
    return _state.active


# ──────────────────────────────────────────────────────────────────
# 2. EXIT DETECTION
# ──────────────────────────────────────────────────────────────────

def detect_exit(text: str) -> bool:
    """
    Return True if 'text' contains any exit phrase.
    Comparison is case-insensitive; partial phrase matches are accepted
    (e.g. "please stop assistant now" still matches "stop assistant").
    """
    lowered = text.lower().strip()
    return any(phrase in lowered for phrase in EXIT_PHRASES)


# ──────────────────────────────────────────────────────────────────
# 3. GROQ LLM  — streaming chat with memory
# ──────────────────────────────────────────────────────────────────

async def _stream_groq_tokens(
    messages: list[dict],
    client: httpx.AsyncClient,
) -> AsyncIterator[str]:
    """
    Yield text tokens as they arrive from Groq's SSE stream.
    Raises httpx.HTTPError on non-2xx responses.
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY is not set.")

    payload = {
        "model":       GROQ_CHAT_MODEL,
        "messages":    messages,
        "temperature": GROQ_TEMPERATURE,
        "max_tokens":  GROQ_MAX_TOKENS,
        "stream":      True,
    }

    async with client.stream(
        "POST",
        GROQ_URL,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=GROQ_TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        async for raw_line in resp.aiter_lines():
            # SSE lines look like:  "data: {...}"  or  "data: [DONE]"
            if not raw_line.startswith("data:"):
                continue
            chunk_str = raw_line[len("data:"):].strip()
            if chunk_str == "[DONE]":
                break
            try:
                chunk = json.loads(chunk_str)
                token = chunk["choices"][0]["delta"].get("content", "")
                if token:
                    yield token
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


async def groq_chat(
    user_text: str,
    state: AssistantState,
    livekit_session: Optional["LiveKitSession"] = None,
) -> str:
    """
    Send user_text to Groq with conversation memory.
    Streams tokens to console (and LiveKit if available).
    Returns the full assistant reply as a string.

    Falls back to FALLBACK_REPLY on any error.
    """
    # Add user turn to memory before calling Groq
    state.push_memory("user", user_text)

    full_reply: list[str] = []
    t0 = time.perf_counter()

    try:
        async with httpx.AsyncClient() as client:
            print("\n🤖 Assistant: ", end="", flush=True)

            async for token in _stream_groq_tokens(state.context_messages, client):
                print(token, end="", flush=True)
                full_reply.append(token)

                # Stream each token to LiveKit data channel in real time
                if livekit_session:
                    await livekit_session.publish_token(token)

            print()   # newline after streaming ends

        reply = "".join(full_reply).strip()
        if not reply:
            raise ValueError("Empty reply from Groq")

    except EnvironmentError as exc:
        log.error("Groq auth error: %s", exc)
        reply = FALLBACK_REPLY
        print(f"\n🤖 Assistant: {reply}")

    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        log.error("Groq network error: %s", exc)
        reply = FALLBACK_REPLY
        print(f"\n🤖 Assistant: {reply}")

    except Exception as exc:
        log.error("Unexpected Groq error: %s", exc)
        reply = FALLBACK_REPLY
        print(f"\n🤖 Assistant: {reply}")

    else:
        # Only add to memory on success (don't pollute context with fallbacks)
        state.push_memory("assistant", reply)
        latency = (time.perf_counter() - t0) * 1000
        log.debug("Groq reply in %.0f ms  (%d tokens)", latency, len(full_reply))

    # Publish full reply as a single event (for UI rendering)
    if livekit_session:
        await livekit_session.publish_event("assistant_reply", reply)

    return reply


# ──────────────────────────────────────────────────────────────────
# 4. LIVEKIT SESSION  — real-time text streaming layer
# ──────────────────────────────────────────────────────────────────

class LiveKitSession:
    """
    Wraps the LiveKit Python SDK to provide a minimal real-time text channel.

    Publishes two kinds of messages over the LiveKit data channel:
      • token events  → streamed token-by-token for real-time UI updates
      • named events  → structured JSON for state changes (user_input, assistant_reply, etc.)

    Degrades gracefully: if `livekit` is not installed or connection fails,
    all publish_* calls become no-ops so the rest of the system is unaffected.
    """

    def __init__(self, room_name: str = LIVEKIT_ROOM):
        self._room_name  = room_name
        self._room       = None       # livekit.rtc.Room instance (or None)
        self._available  = False      # True only after successful connect
        self._token      = ""

    # ── connection management ─────────────────────────────────────

    async def connect(self) -> bool:
        """
        Attempt to connect to the LiveKit server.
        Returns True on success, False if unavailable (no SDK / no server).
        """
        if not (LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
            log.info("[LiveKit] Credentials not set — running without LiveKit")
            return False

        try:
            from livekit import api as lk_api    # type: ignore
            from livekit import rtc as lk_rtc    # type: ignore
        except ImportError:
            log.info("[LiveKit] SDK not installed — running without LiveKit")
            return False

        try:
            # Generate an access token for a bot participant
            token_builder = (
                lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
                .with_identity("assistant-bot")
                .with_name("AI Assistant")
                .with_grants(lk_api.VideoGrants(
                    room_join=True,
                    room=self._room_name,
                    can_publish_data=True,
                ))
            )
            self._token = token_builder.to_jwt()

            self._room = lk_rtc.Room()
            await self._room.connect(LIVEKIT_URL, self._token)
            self._available = True
            log.info("[LiveKit] ✓ Connected to room '%s'", self._room_name)
            return True

        except Exception as exc:
            log.warning("[LiveKit] Connection failed: %s — running without LiveKit", exc)
            self._room      = None
            self._available = False
            return False

    async def disconnect(self) -> None:
        if self._room and self._available:
            try:
                await self._room.disconnect()
                log.info("[LiveKit] Disconnected from room '%s'", self._room_name)
            except Exception as exc:
                log.debug("[LiveKit] Disconnect error (ignored): %s", exc)
        self._available = False
        self._room      = None

    # ── publishing helpers ────────────────────────────────────────

    async def publish_token(self, token: str) -> None:
        """Stream a single LLM token to connected LiveKit subscribers."""
        if not self._available or not self._room:
            return
        await self._publish_raw(json.dumps({"type": "token", "data": token}))

    async def publish_event(self, event_type: str, data: str) -> None:
        """Publish a named event (user_input, assistant_reply, state_change)."""
        if not self._available or not self._room:
            return
        payload = json.dumps({"type": event_type, "data": data, "ts": time.time()})
        await self._publish_raw(payload)

    async def _publish_raw(self, payload: str) -> None:
        try:
            await self._room.local_participant.publish_data(
                payload.encode("utf-8"),
                reliable=True,          # TCP-like delivery guarantee
            )
        except Exception as exc:
            log.debug("[LiveKit] publish error (ignored): %s", exc)

    # ── context manager support ───────────────────────────────────

    async def __aenter__(self) -> "LiveKitSession":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.disconnect()


# ──────────────────────────────────────────────────────────────────
# 5. CONVERSATION HANDLER  — one turn of the dialogue
# ──────────────────────────────────────────────────────────────────

async def handle_conversation(
    user_text: str,
    state: AssistantState,
    livekit_session: Optional[LiveKitSession] = None,
) -> str:
    """
    Process one user turn:
      1. Publish user input to LiveKit
      2. Get Groq response (streaming)
      3. Return assistant reply

    Does NOT check exit conditions — that is the caller's responsibility.
    """
    state.turn_count += 1
    log.debug("[Turn %d] user said: %r", state.turn_count, user_text)

    print(f"\n👤 You: {user_text}")

    # Let LiveKit subscribers see the user's input in real time
    if livekit_session:
        await livekit_session.publish_event("user_input", user_text)

    # Get and stream the assistant reply
    reply = await groq_chat(user_text, state, livekit_session)
    return reply


# ──────────────────────────────────────────────────────────────────
# 6. MAIN ASSISTANT LOOP
# ──────────────────────────────────────────────────────────────────

async def start_assistant_loop(
    initial_text: str,
    transcribe: Callable[[], str],
) -> None:
    """
    Enter assistant mode and run the conversational loop.

    Parameters
    ----------
    initial_text : str
        The utterance that triggered assistant mode (e.g. "assistant what's the weather").
        The keyword "assistant" is stripped before sending to the LLM.
    transcribe : Callable[[], str]
        Reference to the existing transcribe() function from the pipeline.
        Called with no arguments each iteration; returns the next user utterance.
        For testing, pass `lambda: input("You: ")`.
    """
    _state.enter()
    tts_engine.start()
    # Strip the trigger keyword so it doesn't confuse the LLM
    first_query = _strip_trigger(initial_text)

    print("\n" + "─" * 55)
    print("  🎙️  Assistant Mode  ACTIVE  (say 'exit assistant' to quit)")
    print("─" * 55)

    async with LiveKitSession() as lk:
        await lk.publish_event("state_change", "assistant_mode_on")

        try:
            # ── Handle the opening utterance ──
            if first_query:
                reply = await handle_conversation(first_query, _state, lk)
                asyncio.create_task(tts_engine.speak(reply))

            # ── Continuous loop ──
            while _state.active:
                try:
                    user_text = await asyncio.wait_for(
                        asyncio.to_thread(transcribe),
                        timeout=30.0,
                    )

                except asyncio.TimeoutError:
                    log.info("[Loop] No speech for 30 s — exiting assistant mode")
                    print("\n⏱️  No input detected. Returning to command mode.")
                    break

                except asyncio.CancelledError:
                    log.info("[Loop] Cancelled — exiting cleanly")
                    break

                if not user_text or not user_text.strip():
                    continue

                if detect_exit(user_text):
                    print("\n✋ Exiting assistant mode. Returning to command system.")
                    break
                
                # when user speaks → interrupt TTS immediately
                tts_engine.stop()
                reply = await handle_conversation(user_text, _state, lk)
                asyncio.create_task(tts_engine.speak(reply))

        except KeyboardInterrupt:
            print("\n\n⚡ Interrupted — returning to command mode.")

        except Exception as exc:
            log.error("[Loop] Unexpected error: %s", exc, exc_info=True)
            print(f"\n⚠️  An error occurred in assistant mode: {exc}")

        finally:
            await lk.publish_event("state_change", "assistant_mode_off")
            _state.exit()
            print("\n" + "─" * 55)
            print("  ✅  Returned to voice command mode")
            print("─" * 55 + "\n")


def _strip_trigger(text: str) -> str:
    """
    Remove the leading trigger keyword so the LLM sees a clean query.
    """
    lowered = text.lower()
    for marker in ("hey assistant", "ok assistant", "assistant"):
        idx = lowered.find(marker)
        if idx != -1:
            remainder = text[idx + len(marker):].strip()
            return remainder if remainder else text
    return text

# ──────────────────────────────────────────────────────────────────
# 7. PUBLIC SYNC WRAPPER  — for callers that aren't async
# ──────────────────────────────────────────────────────────────────

def run_assistant(initial_text: str, transcribe: Callable[[], str]) -> None:
    """
    Synchronous entry point. Wraps start_assistant_loop in asyncio.run().
    Use this when calling from a synchronous main pipeline.
    """
    asyncio.run(start_assistant_loop(initial_text, transcribe))



# ──────────────────────────────────────────────────────────────────
# Demo / manual test
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 55)
    print("  Assistant Mode — Interactive Demo")
    print("  (Uses stdin to simulate microphone input)")
    print("=" * 55)

    # Check for GROQ_API_KEY
    if not os.getenv("GROQ_API_KEY"):
        print("\n⚠️  GROQ_API_KEY not set — responses will use fallback message.")
        print("   Export it with:  export GROQ_API_KEY='gsk_...'\n")

    # Simulate the voice pipeline: just read from terminal
    def mock_transcribe() -> str:
        try:
            return input("🎤  Speak (type here): ").strip()
        except EOFError:
            return "exit assistant"

    # Simulate the trigger from main loop
    trigger = "assistant hello, what can you help me with?"
    print(f'\n[Main Loop] Detected trigger utterance: "{trigger}"')
    print("[Main Loop] Handing off to assistant_mode...\n")

    run_assistant(trigger, transcribe=mock_transcribe)

    print("[Main Loop] Assistant mode exited — command engine resumes.\n")