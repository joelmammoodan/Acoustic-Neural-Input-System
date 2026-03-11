import numpy as np
from faster_whisper import WhisperModel
import os

print("Loading Whisper…")

MODEL_PATH = os.path.join(
    "model",
    "snapshots",
    "edaa852ec7e145841d8ffdb056a99866b5f0a478",
)

model = WhisperModel(
    MODEL_PATH,
    device="cuda",
    compute_type="float16",
    # CPU fallback — remove or change if you only target GPU
    cpu_threads=4,
    num_workers=2,          # parallel segment decoding
)

print("Whisper ready — running warm-up…")

# ── Warm-up inference ────────────────────────────────────────────────────────
# The first real inference always takes longer due to CUDA kernel compilation.
# Feeding a silent dummy clip eliminates that latency spike.
_WARMUP_AUDIO = np.zeros(SAMPLE_RATE := 16000, dtype=np.float32)
list(model.transcribe(_WARMUP_AUDIO, language="en", beam_size=1)[0])
print("Warm-up done ✓")


# ── Audio pre-processing ─────────────────────────────────────────────────────

def _preprocess(audio: np.ndarray) -> np.ndarray | None:
    """
    Validate and normalise a float32 audio array.

    Returns None if the clip should be discarded (too short / too quiet).
    """
    if audio is None or len(audio) == 0:
        return None

    # Must be at least 200 ms — shorter clips confuse Whisper
    if len(audio) < SAMPLE_RATE * 0.2:
        return None

    # Noise gate — discard clips that are effectively silence
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < 3e-4:
        return None

    # Peak-normalise to 0.9 FS
    peak = np.max(np.abs(audio))
    audio = audio / (peak + 1e-9) * 0.9

    return audio.astype(np.float32)


# ── Public API ───────────────────────────────────────────────────────────────

def transcribe_audio(
    audio: np.ndarray,
    language: str = "en",
    beam_size: int = 5,
) -> str:
    """
    Transcribe a float32, 16 kHz audio array.

    Parameters
    ----------
    audio       : float32 numpy array, any amplitude
    language    : BCP-47 language code; set to None for auto-detect
    beam_size   : higher = more accurate but slower (3-5 is a good range)

    Returns
    -------
    Lowercased, stripped transcript string, or "" if nothing was heard.
    """
    audio = _preprocess(audio)
    if audio is None:
        return ""

    segments, info = model.transcribe(
        audio,
        language=language,
        beam_size=beam_size,
        best_of=beam_size,          # candidates per beam step
        vad_filter=True,
        vad_parameters={
            "threshold": 0.35,           # lower = more sensitive
            "min_speech_duration_ms": 100,
            "max_speech_duration_s": 30,
            "min_silence_duration_ms": 300,
            "speech_pad_ms": 100,        # pad edges so words aren't clipped
        },
        condition_on_previous_text=False,  # avoids hallucination loops
        temperature=0.0,                   # greedy at 0; add fallbacks if needed
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
    )

    parts: list[str] = []
    for segment in segments:
        # Skip segments Whisper flagged as low-confidence
        if segment.no_speech_prob > 0.8:
            continue
        parts.append(segment.text)

    return " ".join(parts).strip().lower()