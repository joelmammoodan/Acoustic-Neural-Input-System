"""
main.py -- Voice pipeline with concurrent audio capture and transcription.

Architecture
────────────
  Capture thread  →  audio queue  →  Transcription thread  →  Intent routing

The capture thread runs record_utterance() in a tight loop and pushes raw
audio into a queue.  The transcription thread pops from that queue and calls
Whisper, so the microphone is never blocked waiting for the GPU.
"""

import queue
import threading
import signal
import sys

# Force UTF-8 output on Windows consoles (cp1252 chokes on unicode)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from audio_input import record_utterance
from whisper_asr import transcribe_audio
from intent_model import handle_intent
from intent_router import route_intent


# ── Configuration ─────────────────────────────────────────────────────────────

AUDIO_QUEUE_MAXSIZE = 4       # drop oldest clip if pipeline falls behind
CAPTURE_TIMEOUT_S   = 12.0    # max seconds to wait for a single utterance
TRANSCRIBE_WORKERS  = 1       # increase to 2 if you have a second GPU/CPU slot


# ── Shared state ──────────────────────────────────────────────────────────────

_audio_queue: queue.Queue[bytes | None] = queue.Queue(maxsize=AUDIO_QUEUE_MAXSIZE)
_shutdown = threading.Event()


# ── Capture thread ─────────────────────────────────────────────────────────────

def capture_loop() -> None:
    """Continuously capture utterances and push them onto the audio queue."""
    print("[MIC]  Capture thread started.")
    while not _shutdown.is_set():
        audio = record_utterance(timeout=CAPTURE_TIMEOUT_S)
        if audio is None:
            continue
        try:
            # Non-blocking put; if queue is full we drop the oldest clip
            # so the mic never stalls waiting for a slow GPU.
            _audio_queue.put_nowait(audio)
        except queue.Full:
            print("[WARN]  Audio queue full -- dropping oldest clip.")
            try:
                _audio_queue.get_nowait()
            except queue.Empty:
                pass
            _audio_queue.put_nowait(audio)

    # Poison pill -- wake up transcription thread(s)
    for _ in range(TRANSCRIBE_WORKERS):
        _audio_queue.put(None)
    print("[MIC]  Capture thread exiting.")


# ── Transcription + intent thread ─────────────────────────────────────────────

# ── Intent debounce ───────────────────────────────────────────────────────────
# Minimum seconds that must pass before the same intent can fire again.
# Prevents double-triggers from overlapping VAD segments or mic bleed.
INTENT_COOLDOWN: dict[str, float] = {
    "open_app":   5.0,   # opening an app should never double-fire
    "close_app":  5.0,   # same -- destructive action
    "click":      3.0,   # UI clicks need time for the UI to respond
    "scroll_up":  1.0,
    "scroll_down":1.0,
    "type_text":  3.0,
    "press_key":  2.0,
    "screenshot": 4.0,
    "search":     4.0,
    "ui_list":    2.0,
}
_DEFAULT_COOLDOWN = 3.0  # catch-all for any unlisted intent


def transcribe_loop(worker_id: int = 0) -> None:
    """
    Pop audio clips from the queue, transcribe them, and route the intent.
    """
    import time as _time
    _last_fired: dict[str, float] = {}   # intent → epoch time of last execution

    print(f"[AI]  Transcription worker {worker_id} started.")
    while not _shutdown.is_set():
        try:
            audio = _audio_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        if audio is None:          # poison pill → shut down
            break

        try:
            text = transcribe_audio(audio)
        except Exception as exc:
            print(f"[ERR]  Transcription error: {exc}")
            continue

        if not text:
            print("(no speech detected)")
            continue

        print(f"[TEXT]  You said: {text!r}")

        try:
            intent, normalized, confidence = handle_intent(text)
            print(f"[INTENT]  Intent: {intent}  (confidence: {confidence:.2f})")

            # ── Debounce check ────────────────────────────────────────────────
            now     = _time.monotonic()
            cooldown = INTENT_COOLDOWN.get(intent, _DEFAULT_COOLDOWN)
            last    = _last_fired.get(intent, 0.0)
            elapsed = now - last

            if elapsed < cooldown:
                print(f"[WAIT]  Debounced '{intent}' "
                      f"(fired {elapsed:.1f}s ago, cooldown {cooldown}s).")
                continue

            _last_fired[intent] = now
            route_intent(intent, normalized, confidence)

        except Exception as exc:
            print(f"[ERR]  Intent/routing error: {exc}")

    print(f"[AI]  Transcription worker {worker_id} exiting.")


# ── Graceful shutdown ─────────────────────────────────────────────────────────

def _handle_signal(sig, frame):
    print("\n[HALT]  Shutting down...")
    _shutdown.set()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    print("[OK]  System ready -- just speak.\n")

    # Start transcription workers first so the queue is always drained
    workers: list[threading.Thread] = []
    for i in range(TRANSCRIBE_WORKERS):
        t = threading.Thread(target=transcribe_loop, args=(i,), daemon=True)
        t.start()
        workers.append(t)

    # Start capture in a dedicated thread so the main thread can join cleanly
    cap = threading.Thread(target=capture_loop, daemon=True)
    cap.start()

    # Block main thread until shutdown is signalled
    _shutdown.wait()

    cap.join(timeout=5)
    for t in workers:
        t.join(timeout=5)

    print("[BYE]  Goodbye.")
    sys.exit(0)


if __name__ == "__main__":
    main()