"""
evaluate.py  —  ANIS End-to-End Voice Pipeline Evaluation
==========================================================
TRUE end-to-end evaluation:

    gTTS audio  →  Whisper STT  →  LLM Intent Engine  →  Metrics

Dataset:   intent_dataset.csv  (columns: text, intent, argument)
Audio:     audio_samples/      (generated automatically if missing)

Metrics:
  Intent Accuracy      — correct intent / total
  Argument Accuracy    — correct argument / total (None-safe)
  Task Success Rate    — both intent + argument correct
  STT Accuracy         — transcription match vs ground truth text
  Confusion Matrix     — predicted vs expected intent
  Latency Breakdown    — STT time, LLM time, total per sample
  Failure Analysis     — misclassifications + low-confidence outputs

Outputs  →  eval_outputs/
  summary.txt
  results.json
  confusion_matrix.png
  latency_plot.png
  latency_breakdown.png
  accuracy_by_intent.png

Run:
  cd Python_files
  python evaluate.py [--csv intent_dataset.csv] [--audio audio_samples]
                     [--no-tts] [--noise] [--limit N] [--delay SECS]
                     [--mock-llm] [--no-cache]

Rate-limit flags:
  --limit N       Process only first N samples (default: 20)
  --delay SECS    Sleep between Groq API calls, e.g. 0.5 (default: 0.3)
  --mock-llm      Skip Groq entirely; use keyword-based classifier
  --no-cache      Disable transcript → result cache (cache is on by default)
"""

# ── Silence noisy third-party loggers before any imports ─────────────────────
import logging
logging.basicConfig(level=logging.WARNING)
for _lib in ("asyncio", "matplotlib", "matplotlib.font_manager",
             "faster_whisper", "httpx", "httpcore", "intent_engine"):
    logging.getLogger(_lib).setLevel(logging.WARNING)

# ── Standard library ──────────────────────────────────────────────────────────
import os
import sys
import csv
import json
import time
import asyncio
import argparse
import warnings
from pathlib import Path
from collections import defaultdict
from typing import Optional

warnings.filterwarnings("ignore")

# ── Third-party ───────────────────────────────────────────────────────────────
import numpy as np
from dotenv import load_dotenv

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════

_HERE              = Path(__file__).parent
OUT_DIR            = _HERE / "eval_outputs"
DEFAULT_CSV        = _HERE / "intent_dataset.csv"
DEFAULT_AUDIO      = _HERE / "audio_samples"
CACHE_FILE         = _HERE / "eval_outputs" / "llm_cache.json"
SAMPLE_RATE        = 16_000
LOW_CONF_THRESHOLD = 0.60
DEFAULT_LIMIT      = 20       # safe default for rate-limited dev runs
DEFAULT_DELAY      = 0.3      # seconds between Groq API calls
RETRY_ATTEMPTS     = 3        # max retries on API failure
RETRY_BASE_DELAY   = 2.0      # seconds; doubles each retry (exponential backoff)


def out(name: str) -> Path:
    return OUT_DIR / name


# ══════════════════════════════════════════════════════════════════════════════
# STEP 0 — LOAD DATASET
# ══════════════════════════════════════════════════════════════════════════════

def load_dataset(csv_path: Path, limit: Optional[int] = None) -> list[dict]:
    """
    Load intent_dataset.csv.
    Strips whitespace from all values.
    Normalises argument: 'None' string → None.
    Skips blank rows.
    If limit is set, returns only the first N rows.
    """
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            row = {k.strip(): (v.strip() if v else "") for k, v in raw.items()}
            if not row.get("text"):
                continue
            if row.get("argument", "").lower() in ("none", ""):
                row["argument"] = None
            rows.append(row)

    if limit is not None:
        rows = rows[:limit]
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — AUDIO GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def ensure_audio(dataset: list[dict], audio_dir: Path) -> list[dict]:
    """
    Generate MP3 for each sample via gTTS if not already present.
    Adds 'audio_path' key to each row.
    Returns only rows with valid audio.
    """
    try:
        from gtts import gTTS
        HAS_GTTS = True
    except ImportError:
        print("[WARN] gTTS not installed — pip install gtts")
        HAS_GTTS = False

    audio_dir.mkdir(parents=True, exist_ok=True)
    valid = []

    for i, row in enumerate(dataset):
        filename = f"sample_{i:04d}.mp3"
        filepath = audio_dir / filename
        row["audio_path"] = str(filepath)

        if filepath.exists():
            valid.append(row)
            continue

        if not HAS_GTTS:
            print(f"  [SKIP] {filename}")
            continue

        try:
            gTTS(text=row["text"], lang="en", slow=False).save(str(filepath))
            valid.append(row)
        except Exception as e:
            print(f"  [ERR] gTTS failed for {row['text']!r}: {e}")

    return valid


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — WHISPER STT
# ══════════════════════════════════════════════════════════════════════════════

def load_whisper():
    """Load Whisper. Uses local snapshot if present, else downloads."""
    import torch
    from faster_whisper import WhisperModel

    device  = "cuda" if torch.cuda.is_available() else "cpu"
    compute = "float16" if device == "cuda" else "int8"

    local   = _HERE / "model" / "snapshots" / \
              "edaa852ec7e145841d8ffdb056a99866b5f0a478"
    model_id = str(local) if local.is_dir() else "large-v3"

    print(f"[Whisper] Loading {Path(model_id).name}  on {device}/{compute} ...")
    model = WhisperModel(model_id, device=device, compute_type=compute,
                         cpu_threads=4)
    list(model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32),
                          language="en", beam_size=1)[0])
    print("[Whisper] Ready")
    return model


def mp3_to_float32(filepath: str) -> np.ndarray:
    """MP3 → float32 numpy array at 16 kHz via pydub (needs ffmpeg)."""
    from pydub import AudioSegment
    seg = (AudioSegment.from_file(filepath)
           .set_frame_rate(SAMPLE_RATE)
           .set_channels(1))
    raw = np.array(seg.get_array_of_samples(), dtype=np.float32)
    return raw / 32768.0


def run_stt(model, filepath: str) -> tuple[str, float]:
    """Returns (transcript_lowercase, latency_ms)."""
    audio = mp3_to_float32(filepath)
    t0    = time.perf_counter()
    segs, _ = model.transcribe(
        audio, language="en", beam_size=2, best_of=2,
        vad_filter=True,
        vad_parameters=dict(threshold=0.25, min_speech_duration_ms=80,
                            min_silence_duration_ms=300, speech_pad_ms=60),
        condition_on_previous_text=False,
        temperature=0.0, no_speech_threshold=0.50,
    )
    transcript = " ".join(s.text for s in segs).strip().lower()
    return transcript, (time.perf_counter() - t0) * 1000


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3a — MOCK INTENT CLASSIFIER (no API calls)
# ══════════════════════════════════════════════════════════════════════════════

# Keyword rules: order matters — first match wins.
# Extend this list as your intent set grows.
_MOCK_RULES: list[tuple[str, list[str], Optional[str]]] = [
    # (intent,           keywords,                          argument_hint)
    ("play_music",      ["play", "music", "song", "track"], None),
    ("set_timer",       ["timer", "set timer", "remind"],   None),
    ("get_weather",     ["weather", "temperature", "forecast", "rain", "sunny"], None),
    ("send_message",    ["send", "message", "text", "whatsapp", "sms"],          None),
    ("make_call",       ["call", "phone", "dial", "ring"],  None),
    ("search_web",      ["search", "google", "look up", "find", "who is", "what is"], None),
    ("open_app",        ["open", "launch", "start"],        None),
    ("set_alarm",       ["alarm", "wake me", "wake up"],    None),
    ("get_news",        ["news", "headlines", "latest"],    None),
    ("control_volume",  ["volume", "louder", "quieter", "mute", "unmute"],       None),
    ("control_lights",  ["light", "lights", "dim", "bright", "lamp"],            None),
    ("stop",            ["stop", "cancel", "quit", "exit", "end"],               None),
    ("none",            [],                                 None),   # fallback
]

def mock_classify(text: str) -> dict:
    """
    Keyword-based intent classifier.
    Used in --mock-llm mode to avoid any Groq API calls.
    Returns same dict shape as get_intent(): {intent, argument, confidence}.
    """
    lower = text.lower()
    for intent, keywords, _ in _MOCK_RULES:
        if any(kw in lower for kw in keywords):
            # Naively extract everything after the first keyword as the argument
            argument = None
            for kw in keywords:
                idx = lower.find(kw)
                if idx != -1:
                    tail = text[idx + len(kw):].strip(" .,?!")
                    if tail:
                        argument = tail
                    break
            return {"intent": intent, "argument": argument, "confidence": 0.75}

    return {"intent": "none", "argument": None, "confidence": 0.5}


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3b — LLM CACHE  (transcript → result, persisted to JSON)
# ══════════════════════════════════════════════════════════════════════════════

class LLMCache:
    """
    Thin persistent cache: maps transcript text → intent result dict.
    Backed by a JSON file so it survives between runs.
    Thread/async safety: single-process only (sufficient here).
    """

    def __init__(self, path: Path, enabled: bool = True):
        self._path    = path
        self._enabled = enabled
        self._data: dict[str, dict] = {}
        if enabled and path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                print(f"[Cache] Loaded {len(self._data)} cached results from {path.name}")
            except Exception as e:
                print(f"[Cache] Could not load cache ({e}); starting fresh")

    def get(self, key: str) -> Optional[dict]:
        if not self._enabled:
            return None
        return self._data.get(key)

    def set(self, key: str, value: dict) -> None:
        if not self._enabled:
            return
        self._data[key] = value
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            print(f"[Cache] Write failed: {e}")

    def __len__(self) -> int:
        return len(self._data)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3c — INTENT ENGINE  (single event loop for all samples)
# ══════════════════════════════════════════════════════════════════════════════

# Fallback result returned when all retries are exhausted
_FALLBACK_RESULT = {"intent": "none", "argument": None, "confidence": 0.0}


async def _call_with_retry(text: str) -> dict:
    """
    Call get_intent() with exponential backoff on failure.
    Returns a safe fallback dict if all attempts fail.
    """
    from intent_engine import get_intent

    delay = RETRY_BASE_DELAY
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            result = await get_intent(text)
            return result
        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "rate" in err_str.lower()
            if attempt < RETRY_ATTEMPTS:
                wait = delay if is_rate_limit else delay / 2
                print(f"  [RETRY {attempt}/{RETRY_ATTEMPTS}] "
                      f"{'Rate limit' if is_rate_limit else 'Error'}: "
                      f"{err_str[:80]} — waiting {wait:.1f}s")
                await asyncio.sleep(wait)
                delay *= 2   # exponential backoff
            else:
                print(f"  [FAIL] All {RETRY_ATTEMPTS} attempts failed for "
                      f"{text!r:.40} — using fallback")

    return _FALLBACK_RESULT.copy()


async def classify_all(
    texts: list[str],
    cache: LLMCache,
    inter_call_delay: float,
    mock_mode: bool,
) -> list[tuple[str, Optional[str], float, float]]:
    """
    Classify a list of texts.
    Returns list of (intent, argument, confidence, latency_ms).

    Behaviour:
      - mock_mode=True  → keyword classifier, no API calls
      - cache hit       → reuse cached result, no API call
      - cache miss      → call Groq with retry + throttle delay
    """
    results = []
    cache_hits = 0

    for idx, text in enumerate(texts):
        t0 = time.perf_counter()

        if mock_mode:
            # ── Mock mode: pure local classification ──────────────────────────
            raw = mock_classify(text)
        else:
            # ── Check cache first ─────────────────────────────────────────────
            cached = cache.get(text)
            if cached is not None:
                raw = cached
                cache_hits += 1
            else:
                # ── Live Groq call with retry + inter-call throttle ───────────
                raw = await _call_with_retry(text)
                cache.set(text, raw)
                # Throttle: sleep between real API calls to respect TPM limits
                if inter_call_delay > 0:
                    await asyncio.sleep(inter_call_delay)

        t1 = time.perf_counter()

        intent   = raw.get("intent",     "none")
        argument = raw.get("argument",   None)
        conf     = raw.get("confidence", 0.0)

        if isinstance(argument, str) and argument.lower() == "none":
            argument = None

        results.append((intent, argument, conf, (t1 - t0) * 1000))

    if not mock_mode:
        total  = len(texts)
        misses = total - cache_hits
        print(f"  Cache hits: {cache_hits}/{total}  |  "
              f"Groq API calls made: {misses}")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — METRICS
# ══════════════════════════════════════════════════════════════════════════════

def _norm(arg) -> Optional[str]:
    if arg is None or str(arg).lower() in ("none", ""):
        return None
    return str(arg).lower().strip()


def compute_metrics(records: list[dict]) -> dict:
    n = len(records)
    if n == 0:
        return {}

    intent_correct = argument_correct = task_correct = stt_match = 0
    y_true, y_pred = [], []
    stt_lats, llm_lats, total_lats = [], [], []
    failures, low_conf = [], []
    intent_stats = defaultdict(lambda: {"n": 0, "correct": 0})

    for r in records:
        gt_intent = r["intent_gt"]
        gt_arg    = _norm(r["argument_gt"])
        pr_intent = r["intent_pred"]
        pr_arg    = _norm(r["argument_pred"])
        conf      = r["confidence"]

        # STT exact match
        if r["text"].lower().strip() == r["transcript"].lower().strip():
            stt_match += 1

        # Intent
        ok_intent = (pr_intent == gt_intent)
        if ok_intent:
            intent_correct += 1

        # Argument (substring match — "youtube" in "youtube videos" → ok)
        if gt_arg is None:
            ok_arg = (pr_arg is None)
        else:
            ok_arg = pr_arg is not None and gt_arg in pr_arg
        if ok_arg:
            argument_correct += 1

        if ok_intent and ok_arg:
            task_correct += 1

        intent_stats[gt_intent]["n"] += 1
        if ok_intent:
            intent_stats[gt_intent]["correct"] += 1

        y_true.append(gt_intent)
        y_pred.append(pr_intent)
        stt_lats.append(r["stt_ms"])
        llm_lats.append(r["llm_ms"])
        total_lats.append(r["total_ms"])

        if not ok_intent:
            failures.append(dict(text=r["text"], gt=gt_intent, pred=pr_intent,
                                 conf=round(conf, 3), transcript=r["transcript"]))
        if conf < LOW_CONF_THRESHOLD:
            low_conf.append(dict(text=r["text"], intent=pr_intent, conf=round(conf, 3)))

    def _s(lst):
        a = np.array(lst)
        return dict(mean=round(float(np.mean(a)), 1),
                    median=round(float(np.median(a)), 1),
                    p95=round(float(np.percentile(a, 95)), 1),
                    std=round(float(np.std(a)), 1),
                    min=round(float(np.min(a)), 1),
                    max=round(float(np.max(a)), 1))

    return dict(
        n=n,
        intent_accuracy     = round(intent_correct   / n * 100, 2),
        argument_accuracy   = round(argument_correct / n * 100, 2),
        task_success_rate   = round(task_correct     / n * 100, 2),
        stt_exact_match_pct = round(stt_match        / n * 100, 2),
        stt_latency=_s(stt_lats), llm_latency=_s(llm_lats),
        total_latency=_s(total_lats),
        y_true=y_true, y_pred=y_pred,
        intent_stats=dict(intent_stats),
        failures=failures, low_confidence=low_conf,
        stt_lats=stt_lats, llm_lats=llm_lats, total_lats=total_lats,
    )


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — VISUALISATIONS
# ══════════════════════════════════════════════════════════════════════════════

def make_charts(metrics: dict) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
    except ImportError:
        print("  [SKIP] pip install scikit-learn matplotlib")
        return

    y_true, y_pred = metrics["y_true"], metrics["y_pred"]

    # 1. Confusion matrix ──────────────────────────────────────────────────────
    labels = sorted(set(y_true + y_pred))
    cm     = confusion_matrix(y_true, y_pred, labels=labels)
    fig, ax = plt.subplots(figsize=(12, 9))
    ConfusionMatrixDisplay(cm, display_labels=labels).plot(
        ax=ax, colorbar=True, cmap="Blues")
    ax.set_title("ANIS Voice Pipeline — Intent Confusion Matrix\n"
                 "(gTTS → Whisper → Groq llama-3.1-8b-instant)", fontsize=12)
    plt.xticks(rotation=45, ha="right", fontsize=9)
    plt.yticks(fontsize=9)
    plt.tight_layout()
    plt.savefig(out("confusion_matrix.png"), dpi=150)
    plt.close()
    print("  confusion_matrix.png")

    # 2. Per-sample stacked latency bar ───────────────────────────────────────
    n     = metrics["n"]
    x     = np.arange(n)
    stt_l = np.array(metrics["stt_lats"])
    llm_l = np.array(metrics["llm_lats"])
    fig, ax = plt.subplots(figsize=(max(10, n // 4), 5))
    ax.bar(x, stt_l,               label="STT (Whisper)", color="#3498db", alpha=0.85)
    ax.bar(x, llm_l, bottom=stt_l, label="LLM (Groq)",   color="#e67e22", alpha=0.85)
    ax.axhline(np.mean(metrics["total_lats"]), color="red", linestyle="--",
               linewidth=1.2,
               label=f"Avg total ({np.mean(metrics['total_lats']):.0f} ms)")
    ax.set_xlabel("Sample index")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Per-Sample Pipeline Latency — STT + LLM")
    ax.legend()
    plt.tight_layout()
    plt.savefig(out("latency_plot.png"), dpi=120)
    plt.close()
    print("  latency_plot.png")

    # 3. Latency boxplot ───────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.boxplot(
        [metrics["stt_lats"], metrics["llm_lats"], metrics["total_lats"]],
        labels=["STT\n(Whisper)", "LLM\n(Groq)", "Total"],
        patch_artist=True,
        boxprops=dict(facecolor="#a8d8ea"),
        medianprops=dict(color="navy", linewidth=2),
    )
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Latency Distribution — STT vs LLM vs Total")
    for i, d in enumerate([metrics["stt_lats"], metrics["llm_lats"],
                            metrics["total_lats"]]):
        ax.text(i + 1, np.median(d), f" {np.median(d):.0f}ms",
                va="center", fontsize=9, color="navy")
    plt.tight_layout()
    plt.savefig(out("latency_breakdown.png"), dpi=150)
    plt.close()
    print("  latency_breakdown.png")

    # 4. Per-intent accuracy ───────────────────────────────────────────────────
    istats  = metrics["intent_stats"]
    intents = sorted(istats.keys())
    accs    = [istats[i]["correct"] / istats[i]["n"] * 100 for i in intents]
    counts  = [istats[i]["n"] for i in intents]
    colors  = ["#2ecc71" if a >= 80 else "#e67e22" if a >= 60 else "#e74c3c"
               for a in accs]
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(intents, accs, color=colors, edgecolor="white")
    ax.set_ylim(0, 118)
    ax.set_ylabel("Accuracy (%)")
    ax.set_title("Per-Intent Accuracy  (End-to-End Pipeline)")
    plt.xticks(rotation=30, ha="right")
    for bar, a, cnt in zip(bars, accs, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{a:.0f}%\nn={cnt}", ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    plt.savefig(out("accuracy_by_intent.png"), dpi=150)
    plt.close()
    print("  accuracy_by_intent.png")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — SAVE REPORT
# ══════════════════════════════════════════════════════════════════════════════

def save_report(metrics: dict, records: list[dict]) -> None:
    with open(out("results.json"), "w", encoding="utf-8") as f:
        json.dump({
            "pipeline": "gTTS → Whisper (large-v3-turbo) → Groq llama-3.1-8b-instant",
            "samples":  metrics["n"],
            "metrics": {
                "intent_accuracy_pct":   metrics["intent_accuracy"],
                "argument_accuracy_pct": metrics["argument_accuracy"],
                "task_success_rate_pct": metrics["task_success_rate"],
                "stt_exact_match_pct":   metrics["stt_exact_match_pct"],
            },
            "latency_ms": {
                "stt":   metrics["stt_latency"],
                "llm":   metrics["llm_latency"],
                "total": metrics["total_latency"],
            },
            "per_intent": {
                k: {"n": v["n"], "correct": v["correct"],
                    "accuracy_pct": round(v["correct"]/v["n"]*100, 1)}
                for k, v in metrics["intent_stats"].items()
            },
            "failures":       metrics["failures"],
            "low_confidence": metrics["low_confidence"],
            "per_sample":     records,
        }, f, indent=2)

    lines = []
    w = lines.append
    w("ANIS VOICE PIPELINE — END-TO-END EVALUATION")
    w("=" * 55)
    w("")
    w("Pipeline : gTTS → Whisper (large-v3-turbo) → Groq llama-3.1-8b-instant")
    w(f"Samples  : {metrics['n']}")
    w("")
    w("── ACCURACY ──────────────────────────────────")
    w(f"Intent Accuracy     : {metrics['intent_accuracy']}%")
    w(f"Argument Accuracy   : {metrics['argument_accuracy']}%")
    w(f"Task Success Rate   : {metrics['task_success_rate']}%")
    w(f"STT Exact Match     : {metrics['stt_exact_match_pct']}%")
    w("")
    w("── LATENCY (ms) ──────────────────────────────")
    for stage, key in [("STT (Whisper)", "stt_latency"),
                        ("LLM (Groq)",   "llm_latency"),
                        ("Total",        "total_latency")]:
        s = metrics[key]
        w(f"{stage:<18} mean={s['mean']}  median={s['median']}"
          f"  p95={s['p95']}  min={s['min']}  max={s['max']}")
    w("")
    w("── PER-INTENT ACCURACY ───────────────────────")
    for intent, v in sorted(metrics["intent_stats"].items()):
        n, c = v["n"], v["correct"]
        w(f"  {intent:<18}  {c:2d}/{n:2d}  ({c/n*100:.1f}%)")
    w("")
    w("── FAILURES ──────────────────────────────────")
    if metrics["failures"]:
        for f in metrics["failures"]:
            w(f"  [{f['gt']} → {f['pred']}]  "
              f"text={f['text']!r}  transcript={f['transcript']!r}  conf={f['conf']}")
    else:
        w("  None")
    w("")
    w("── LOW CONFIDENCE ────────────────────────────")
    if metrics["low_confidence"]:
        for f in metrics["low_confidence"]:
            w(f"  {f['intent']:<18}  conf={f['conf']}  text={f['text']!r}")
    else:
        w(f"  None below {LOW_CONF_THRESHOLD}")

    with open(out("summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("  results.json")
    print("  summary.txt")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN — everything runs inside a single asyncio.run()
# ══════════════════════════════════════════════════════════════════════════════

async def pipeline(
    csv_path:     Path,
    audio_dir:    Path,
    skip_tts:     bool,
    noise_mode:   bool,
    limit:        Optional[int],
    inter_delay:  float,
    mock_llm:     bool,
    use_cache:    bool,
) -> None:

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Print run configuration so the user knows what mode they're in
    print("╔══════════════════════════════════════════╗")
    print("║  ANIS Evaluation — Run Configuration    ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  Sample limit  : {str(limit) if limit else 'ALL':<23}║")
    print(f"║  LLM mode      : {'MOCK (keyword rules)' if mock_llm else 'Groq API':<23}║")
    print(f"║  API delay     : {f'{inter_delay}s' if not mock_llm else 'N/A (mock)':<23}║")
    print(f"║  Cache         : {'ON' if use_cache and not mock_llm else 'OFF':<23}║")
    print("╚══════════════════════════════════════════╝\n")

    # 0. Dataset ───────────────────────────────────────────────────────────────
    print(f"[1/6] Loading dataset  {csv_path.name} ...")
    dataset = load_dataset(csv_path, limit=limit)
    print(f"      {len(dataset)} samples"
          + (f"  (limited from full set)" if limit else ""))

    # 1. Audio ─────────────────────────────────────────────────────────────────
    if skip_tts:
        print("[2/6] --no-tts: checking existing audio ...")
        for i, row in enumerate(dataset):
            row["audio_path"] = str(audio_dir / f"sample_{i:04d}.mp3")
        valid = [r for r in dataset if Path(r["audio_path"]).exists()]
    else:
        print(f"[2/6] Ensuring audio in {audio_dir} ...")
        valid = ensure_audio(dataset, audio_dir)
    print(f"      {len(valid)}/{len(dataset)} audio files ready")

    if not valid:
        print("[ERR] No audio available. Run without --no-tts first.")
        return

    # 2. STT ───────────────────────────────────────────────────────────────────
    print("[3/6] Loading Whisper ...")
    whisper_model = load_whisper()

    print(f"[4/6] STT on {len(valid)} samples ...")
    transcripts, stt_lats = [], []
    for i, row in enumerate(valid):
        try:
            tr, ms = run_stt(whisper_model, row["audio_path"])
        except Exception as e:
            print(f"  [WARN] STT failed sample {i}: {e}")
            tr, ms = "", 0.0
        transcripts.append(tr)
        stt_lats.append(ms)
        ok = "✓" if tr.strip() else "?"
        print(f"  {ok} [{i+1:03d}/{len(valid)}]  "
              f"{row['text']!r:<38}  →  {tr!r:<38}  ({ms:.0f}ms)")

    # 3. LLM intent ────────────────────────────────────────────────────────────
    mode_label = "MOCK (no API)" if mock_llm else "Groq API"
    print(f"\n[5/6] Intent classification ({mode_label}) on {len(valid)} transcripts ...")
    if not mock_llm:
        print(f"      delay={inter_delay}s between calls  |  cache={'ON' if use_cache else 'OFF'}\n")

    # Initialise cache (disabled in mock mode or when --no-cache is passed)
    cache = LLMCache(CACHE_FILE, enabled=(use_cache and not mock_llm))

    intent_results = await classify_all(
        transcripts,
        cache=cache,
        inter_call_delay=inter_delay,
        mock_mode=mock_llm,
    )

    # Assemble records
    records = []
    for row, tr, stt_ms, (intent, arg, conf, llm_ms) in zip(
            valid, transcripts, stt_lats, intent_results):
        records.append({
            "text":          row["text"],
            "intent_gt":     row["intent"],
            "argument_gt":   row.get("argument"),
            "audio_path":    row["audio_path"],
            "transcript":    tr,
            "intent_pred":   intent,
            "argument_pred": arg,
            "confidence":    round(conf, 3),
            "stt_ms":        round(stt_ms, 1),
            "llm_ms":        round(llm_ms, 1),
            "total_ms":      round(stt_ms + llm_ms, 1),
        })

    # 4. Metrics ───────────────────────────────────────────────────────────────
    metrics = compute_metrics(records)

    # 5. Print ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print(f"  Samples             : {metrics['n']}")
    print(f"  Intent Accuracy     : {metrics['intent_accuracy']}%")
    print(f"  Argument Accuracy   : {metrics['argument_accuracy']}%")
    print(f"  Task Success Rate   : {metrics['task_success_rate']}%")
    print(f"  STT Exact Match     : {metrics['stt_exact_match_pct']}%")
    print(f"\n  Avg STT latency     : {metrics['stt_latency']['mean']} ms")
    print(f"  Avg LLM latency     : {metrics['llm_latency']['mean']} ms")
    print(f"  Avg Total latency   : {metrics['total_latency']['mean']} ms")
    print("\n  Per-intent accuracy:")
    for intent, v in sorted(metrics["intent_stats"].items()):
        n, c = v["n"], v["correct"]
        bar  = "█" * int(c / n * 20)
        print(f"    {intent:<18}  {c:2d}/{n:2d}  ({c/n*100:5.1f}%)  {bar}")
    if metrics["failures"]:
        print(f"\n  Misclassifications ({len(metrics['failures'])}):")
        for f in metrics["failures"]:
            print(f"    [{f['gt']} → {f['pred']}]  {f['text']!r}")
    if metrics["low_confidence"]:
        print(f"\n  Low confidence (<{LOW_CONF_THRESHOLD}):")
        for f in metrics["low_confidence"]:
            print(f"    conf={f['conf']}  {f['text']!r}")

    try:
        from sklearn.metrics import classification_report
        print("\n  Classification report (sklearn):")
        print(classification_report(metrics["y_true"], metrics["y_pred"],
                                    labels=sorted(set(metrics["y_true"])),
                                    zero_division=0))
    except ImportError:
        pass

    # 6. Charts + report ───────────────────────────────────────────────────────
    print("\n[6/6] Saving charts and report ...")
    make_charts(metrics)
    save_report(metrics, records)

    print("\n" + "=" * 70)
    print("  DONE")
    print(f"  All outputs → {OUT_DIR}/")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ANIS End-to-End Voice Pipeline Evaluation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # ── Original flags ────────────────────────────────────────────────────────
    parser.add_argument("--csv",    type=Path, default=DEFAULT_CSV)
    parser.add_argument("--audio",  type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--no-tts", action="store_true",
                        help="Skip audio generation (use existing files only)")
    parser.add_argument("--noise",  action="store_true",
                        help="[Reserved] Noise augmentation mode")

    # ── Rate-limit / dev flags ────────────────────────────────────────────────
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT, metavar="N",
        help=(f"Process only the first N samples (default: {DEFAULT_LIMIT}). "
              "Pass 0 to run the full dataset."),
    )
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY, metavar="SECS",
        help="Seconds to sleep between Groq API calls (throttle). "
             "Ignored in --mock-llm mode.",
    )
    parser.add_argument(
        "--mock-llm", action="store_true",
        help="Skip Groq entirely; use a keyword-based intent classifier. "
             "Lets you test the full audio→STT→metrics pipeline with zero API calls.",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Disable the transcript→result cache. "
             "By default, results are cached to avoid redundant API calls.",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"[ERR] Dataset not found: {args.csv}")
        sys.exit(1)

    # limit=0 means "no limit" (process all samples)
    sample_limit = args.limit if args.limit > 0 else None

    asyncio.run(pipeline(
        csv_path    = args.csv,
        audio_dir   = args.audio,
        skip_tts    = args.no_tts,
        noise_mode  = args.noise,
        limit       = sample_limit,
        inter_delay = args.delay,
        mock_llm    = args.mock_llm,
        use_cache   = not args.no_cache,
    ))