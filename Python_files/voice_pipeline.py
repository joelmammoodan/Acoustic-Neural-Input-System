"""
voice_pipeline.py — Voice command pipeline for ANIS.

Architecture
────────────
Mic → Whisper → LLM → actions

Run:  python voice_pipeline.py
"""
import asyncio
import json
import json
import os
import re
import signal
import sys
import time
import threading
import collections
from audioop import rms
from matplotlib import text
import numpy as np
import sounddevice as sd
import torch
from WebSocket_broadcast import send_data
from dotenv import load_dotenv
from assistant_mode import run_assistant, is_active
import sys
sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()
import logging
logging.getLogger("faster_whisper").setLevel(logging.WARNING)
# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════

SAMPLE_RATE   = 16_000

CHUNK_MS      = 80        # faster reaction (was 100)
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_MS // 1000

SILENCE_RMS   = 2.5e-4   # slightly lower → better silence detection
SPEECH_RMS    = 7e-4     # slightly lower → detects softer speech

MIN_SPEECH_MS = 250      # ignore tiny noise, but not too strict
MAX_SPEECH_MS = 6000     # reduce lag on long speech

SILENCE_MS    = 450      # faster response after speaking (was 600)
PRE_ROLL_MS   = 350      # more buffer → prevents cutting first word

MIN_CONFIDENCE = 0.60  # slightly stricter → fewer wrong intents
# Local model directory



def _load_whisper():
    from faster_whisper import WhisperModel

    device  = "cuda" if torch.cuda.is_available() else "cpu"
    compute = "float16" if device == "cuda" else "int8"

    print(f"[Whisper] Loading model on {device}/{compute}...")

    model = WhisperModel("large-v3", device=device, compute_type=compute)

    # Warm-up
    list(model.transcribe(
        np.zeros(SAMPLE_RATE, dtype=np.float32),
        language="en",
        beam_size=1
    )[0])

    print("[Whisper] Ready ")
    return model

print("Loading models...")
_whisper = _load_whisper()


def transcribe(audio: np.ndarray) -> str:
    """Run Whisper on a float32 16 kHz clip. Returns lowercase stripped text."""
    peak = np.max(np.abs(audio))
    if peak < 1e-6:
        return ""
    audio = audio / (peak + 1e-9) * 0.9

    segs, _ = _whisper.transcribe(
        audio,
        language="en",
        beam_size=2,
        best_of=2,
        vad_filter=True,
        vad_parameters={
            "threshold":               0.3,
            "min_speech_duration_ms":  100,
            "min_silence_duration_ms": 300,
            "speech_pad_ms":           60,
        },
        condition_on_previous_text=False,
        temperature=0.0,
        no_speech_threshold=0.5
    )
    parts = [s.text for s in segs if s.no_speech_prob < 0.5]
    return " ".join(parts).strip().lower()


# ══════════════════════════════════════════════════════════════════════════════
# INTENT — LLM-based (Groq → Ollama → HF fallback)
# ══════════════════════════════════════════════════════════════════════════════

from intent_engine import run_command


# ══════════════════════════════════════════════════════════════════════════════
# MIC CAPTURE  — energy-based VAD, ring buffer pre-roll
# ══════════════════════════════════════════════════════════════════════════════

class MicCapture:
    """Streams mic audio, detects speech via RMS energy,
    queues complete utterances as float32 numpy arrays."""

    PRE_ROLL_CHUNKS = max(1, PRE_ROLL_MS  // CHUNK_MS)
    SILENCE_CHUNKS  = max(1, SILENCE_MS   // CHUNK_MS)
    MAX_CHUNKS      = max(1, MAX_SPEECH_MS // CHUNK_MS)

    def __init__(self):
        self._pre_roll    = collections.deque(maxlen=self.PRE_ROLL_CHUNKS)
        self._speech      = []
        self._silence_ctr = 0
        self._in_speech   = False
        self._result_q    = collections.deque()
        self._lock        = threading.Lock()
        self._stream      = None

    def _callback(self, indata, frames, time_info, status):
        chunk = indata[:, 0].copy()
        rms   = float(np.sqrt(np.mean(chunk ** 2)))

        with self._lock:
            if not self._in_speech:
                self._pre_roll.append(chunk)
                if rms > SPEECH_RMS:
                    self._in_speech   = True
                    self._silence_ctr = 0
                    self._speech      = list(self._pre_roll)
                   # print(" Listening...")
            else:
                self._speech.append(chunk)
                if rms < SILENCE_RMS:
                    self._silence_ctr += 1
                else:
                    self._silence_ctr = 0

                if self._silence_ctr >= self.SILENCE_CHUNKS or len(self._speech) >= self.MAX_CHUNKS:
                    audio = np.concatenate(self._speech).astype(np.float32)
                    if len(audio) / SAMPLE_RATE * 1000 >= MIN_SPEECH_MS:
                        self._result_q.append(audio)
                    self._speech      = []
                    self._silence_ctr = 0
                    self._in_speech   = False
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    send_data(json.dumps({
                        "type": "audio_level",
                        "level": float(rms)
                        })),
                    loop
                )
        except:
            pass

    def start(self):
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            blocksize=CHUNK_SAMPLES, callback=self._callback,
        )
        self._stream.start()
        print("[MIC] Listening...")

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()

    def get(self) -> np.ndarray | None:
        """Non-blocking — returns next utterance or None."""
        with self._lock:
            return self._result_q.popleft() if self._result_q else None


# ══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════
import asyncio

async def main():
    shutdown = asyncio.Event()

    def _sig(sig, frame):
        print("\n[HALT] Shutting down...")
        shutdown.set()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    print("[OK] Voice pipeline ready\n")

    mic = MicCapture()
    mic.start()

    try:
        while not shutdown.is_set():

            # 🔊 get audio (non-blocking wrapper)
            audio = await asyncio.to_thread(mic.get)

            if audio is None:
                await asyncio.sleep(0.02)
                continue

            # ─── TRANSCRIBE ─────────────────────────────
            t0 = time.monotonic()
            text = await asyncio.to_thread(transcribe, audio)
            t1 = time.monotonic()

            if not text or not text.strip():
                continue

            latency = (t1 - t0) * 1000

            print(f"🎤 {text}")
            print(f"⚡ {latency:.0f} ms")

            # 🔥 SEND TO UI
            await send_data(json.dumps({
                "type": "user_transcript",
                "text": text
            }))

            # ─── ASSISTANT MODE TRIGGER ─────────────────
            def is_trigger(t):
                return "assistant" in t.lower()

            async def next_utterance():
                while True:
                    audio = await asyncio.to_thread(mic.get)
                    if audio is not None:
                        return await asyncio.to_thread(transcribe, audio)
                    await asyncio.sleep(0.02)

            if is_trigger(text) and not is_active():
                print("🚀 Entering Assistant Mode...\n")

                # ⚠️ run assistant in thread (since it uses asyncio internally)
                def next_utterance_sync():
                    while True:
                        audio = mic.get()
                        if audio is not None:
                            return transcribe(audio)
                        time.sleep(0.02)

                await asyncio.to_thread(
                    run_assistant,
                    text,
                    next_utterance_sync
                )

                print("🔙 Back to command mode\n")
                continue

            # ─── THINKING STATE ─────────────────────────
            await send_data(json.dumps({
                "type": "voice_state",
                "state": "thinking"
            }))

            # ─── INTENT ─────────────────────────────────
            result = await asyncio.to_thread(run_command, text)

            intent = result.get("intent", "none")
            conf   = result.get("confidence", 0.0)

            print(f"🧠 {intent} ({conf:.2f})")

            if intent == "none" or conf < MIN_CONFIDENCE:
                print("❌ Ignored\n")
                continue

            # ─── RESPONSE TO UI ─────────────────────────
            await send_data(json.dumps({
                "type": "assistant_reply",
                "text": f"{intent}"
            }))

            # ─── SPEAKING STATE ─────────────────────────
            await send_data(json.dumps({
                "type": "voice_state",
                "state": "speaking"
            }))

            print("✅ Executed\n")

            # ─── BACK TO LISTENING ──────────────────────
            await send_data(json.dumps({
                "type": "voice_state",
                "state": "listening"
            }))

    finally:
        mic.stop()
        print("[BYE]")


if __name__ == "__main__":
    asyncio.run(main())