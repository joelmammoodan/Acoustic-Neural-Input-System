import sounddevice as sd
import numpy as np
import webrtcvad
import collections
import threading

SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_DURATION_MS = 20          # 20 ms frames — best WebRTC VAD accuracy
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)   # 320 samples

# How many silent frames before we consider speech ended
# 400 ms of silence  →  400/20 = 20 frames
SILENCE_FRAMES_THRESHOLD = 20

# Pre-roll: keep this many frames before speech starts (captures leading consonants)
PRE_ROLL_FRAMES = 8             # 160 ms

# Minimum voiced frames required before we accept a segment
MIN_SPEECH_FRAMES = 5           # 100 ms — ignores micro-glitches

vad = webrtcvad.Vad(2)          # aggressiveness 0-3; 2 is a good balance


def _to_int16_bytes(frame: np.ndarray) -> bytes:
    """Convert a float32 frame to int16 PCM bytes for WebRTC VAD."""
    pcm = np.clip(frame, -1.0, 1.0)
    return (pcm * 32767).astype(np.int16).tobytes()


def record_utterance(
    timeout: float = 15.0,
    pre_roll: int = PRE_ROLL_FRAMES,
    silence_threshold: int = SILENCE_FRAMES_THRESHOLD,
    min_speech: int = MIN_SPEECH_FRAMES,
) -> np.ndarray | None:
    """
    Block until a complete utterance is captured via VAD, then return it.

    Returns a float32 numpy array at SAMPLE_RATE, or None if nothing usable
    was captured within `timeout` seconds.
    """

    pre_roll_buf = collections.deque(maxlen=pre_roll)  # circular pre-roll
    speech_frames: list[np.ndarray] = []
    silence_count = 0
    in_speech = False
    voiced_count = 0

    # Shared state for the callback thread
    _lock = threading.Lock()
    _done = threading.Event()
    _result: list[np.ndarray | None] = [None]

    def _flush() -> np.ndarray | None:
        if voiced_count < min_speech:
            return None
        combined = np.concatenate(speech_frames, axis=0).astype(np.float32)
        # Normalise, but only if signal is strong enough to avoid amplifying noise
        peak = np.max(np.abs(combined))
        if peak < 0.005:
            return None
        combined = combined / (peak + 1e-9) * 0.9
        return combined

    def callback(indata: np.ndarray, frames: int, time_info, status):
        nonlocal in_speech, silence_count, voiced_count

        # Slice into VAD-sized frames (indata may contain multiple)
        flat = indata[:, 0].copy()
        n_frames = len(flat) // FRAME_SIZE

        with _lock:
            for i in range(n_frames):
                chunk = flat[i * FRAME_SIZE : (i + 1) * FRAME_SIZE]
                is_speech = False
                try:
                    is_speech = vad.is_speech(_to_int16_bytes(chunk), SAMPLE_RATE)
                except Exception:
                    pass

                if is_speech:
                    if not in_speech:
                        # Prepend pre-roll so we don't clip the start
                        speech_frames.extend(list(pre_roll_buf))
                        in_speech = True
                    speech_frames.append(chunk)
                    voiced_count += 1
                    silence_count = 0
                else:
                    if in_speech:
                        speech_frames.append(chunk)
                        silence_count += 1
                        if silence_count >= silence_threshold:
                            _result[0] = _flush()
                            _done.set()
                            return
                    else:
                        pre_roll_buf.append(chunk)

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=FRAME_SIZE,
        callback=callback,
    ):
        print("🎤 Listening…")
        triggered = _done.wait(timeout=timeout)

    if not triggered:
        # Timeout — flush whatever we have
        with _lock:
            _result[0] = _flush()

    return _result[0]


# ---------------------------------------------------------------------------
# Legacy push-to-talk interface (kept for backward compatibility)
# ---------------------------------------------------------------------------

_pt_recording = False
_pt_frames: list[np.ndarray] = []
_pt_stream = None


def _pt_callback(indata, frames, time_info, status):
    if _pt_recording:
        _pt_frames.append(indata[:, 0].copy())


def start_recording():
    global _pt_recording, _pt_stream, _pt_frames
    _pt_frames = []
    _pt_recording = True
    _pt_stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        callback=_pt_callback,
    )
    _pt_stream.start()


def stop_recording() -> np.ndarray | None:
    global _pt_recording, _pt_stream

    _pt_recording = False
    if _pt_stream is None:
        return None
    _pt_stream.stop()
    _pt_stream.close()
    _pt_stream = None

    if not _pt_frames:
        return None

    audio = np.concatenate(_pt_frames).astype(np.float32)
    _pt_frames.clear()

    peak = np.max(np.abs(audio))
    if peak < 0.01:
        print("⚠️  Audio too quiet, ignoring.")
        return None

    return audio / (peak + 1e-9) * 0.9