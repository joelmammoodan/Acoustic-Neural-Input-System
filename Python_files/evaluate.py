"""
evaluate.py — ANIS Voice Pipeline Evaluation
=============================================
Single-run script covering all evaluation stages:

  Stage 1 : Filler / VAD text-level rejection
  Stage 2 : Intent classification (Rule Engine vs Phi-2)
            — accuracy, per-intent F1, latency, confidence sweep
  Stage 3 : Whisper ASR — WER and keyword accuracy (requires .wav files)
  Stage 4 : End-to-end summary report

Outputs (all written to eval_outputs/ folder):
  results.json          — full raw results
  summary.txt           — human-readable report for LaTeX
  confusion_matrix.png  — intent confusion matrix
  latency_dist.png      — boxplot: rule vs phi2 latency
  accuracy_by_type.png  — bar chart: accuracy per utterance category
  threshold_sweep.png   — accuracy vs confidence threshold curve
  wer_report.txt        — per-utterance WER (if .wav files provided)

Place this file at:
  Python_files/evaluate.py   (same folder as voice_pipeline.py)

Run:
  cd Python_files
  python evaluate.py

Requirements (beyond project deps):
  pip install scikit-learn matplotlib
  pip install jiwer          # optional — only needed for Whisper WER stage

NOTE: Stages 1 and 2 run purely on text — no mic, no GPU needed.
      Stage 3 (Whisper WER) is optional and requires pre-recorded .wav files.
"""

import os, sys, json, time, re, warnings
import numpy as np
warnings.filterwarnings("ignore")

os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE",  "1")

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_outputs")
os.makedirs(OUT_DIR, exist_ok=True)

def out(filename):
    return os.path.join(OUT_DIR, filename)


# ══════════════════════════════════════════════════════════════════════════════
# TEST DATASET
# ══════════════════════════════════════════════════════════════════════════════
# Each entry: (utterance, expected_intent, category)
# Categories: canonical | natural | noisy_sim | filler | edge

TEST_CASES = [
    # ── open_app ──────────────────────────────────────────────────────────────
    ("open chrome",                     "open_app",         "canonical"),
    ("launch notepad",                  "open_app",         "canonical"),
    ("start discord",                   "open_app",         "canonical"),
    ("open vs code",                    "open_app",         "canonical"),
    ("run calculator",                  "open_app",         "canonical"),
    ("can you open chrome for me",      "open_app",         "natural"),
    ("i need to open the browser",      "open_app",         "natural"),
    ("please launch spotify",           "open_app",         "natural"),

    # ── close_app ─────────────────────────────────────────────────────────────
    ("close chrome",                    "close_app",        "canonical"),
    ("quit spotify",                    "close_app",        "canonical"),
    ("kill notepad",                    "close_app",        "canonical"),
    ("close vs code",                   "close_app",        "canonical"),
    ("could you close the browser",     "close_app",        "natural"),

    # ── click ─────────────────────────────────────────────────────────────────
    ("click the button",                "click",            "canonical"),
    ("tap ok",                          "click",            "canonical"),
    ("click submit",                    "click",            "canonical"),
    ("click cancel",                    "click",            "canonical"),
    ("hit that button",                 "click",            "natural"),

    # ── scroll_up ─────────────────────────────────────────────────────────────
    ("scroll up",                       "scroll_up",        "canonical"),
    ("scroll to the top",               "scroll_up",        "canonical"),
    ("go up",                           "scroll_up",        "edge"),

    # ── scroll_down ───────────────────────────────────────────────────────────
    ("scroll down",                     "scroll_down",      "canonical"),
    ("scroll to bottom",                "scroll_down",      "canonical"),
    ("go down",                         "scroll_down",      "edge"),

    # ── type_text ─────────────────────────────────────────────────────────────
    ("type hello world",                "type_text",        "canonical"),
    ("write my name",                   "type_text",        "canonical"),
    ("input the password",              "type_text",        "canonical"),
    ("type this sentence",              "type_text",        "canonical"),

    # ── press_key ─────────────────────────────────────────────────────────────
    ("press enter",                     "press_key",        "canonical"),
    ("press escape",                    "press_key",        "canonical"),
    ("press ctrl c",                    "press_key",        "canonical"),
    ("press ctrl z",                    "press_key",        "canonical"),
    ("press tab",                       "press_key",        "canonical"),
    ("hit ctrl shift t",                "press_key",        "natural"),

    # ── screenshot ────────────────────────────────────────────────────────────
    ("take a screenshot",               "screenshot",       "canonical"),
    ("screenshot",                      "screenshot",       "canonical"),
    ("capture the screen",              "screenshot",       "canonical"),
    ("take a screen capture",           "screenshot",       "natural"),

    # ── search ────────────────────────────────────────────────────────────────
    ("search for python tutorials",     "search",           "canonical"),
    ("google the weather",              "search",           "canonical"),
    ("look up numpy documentation",     "search",           "canonical"),
    ("search machine learning",         "search",           "canonical"),
    ("find me a python tutorial",       "search",           "natural"),

    # ── filler / none ─────────────────────────────────────────────────────────
    ("um okay",                         "none",             "filler"),
    ("yeah",                            "none",             "filler"),
    ("never mind",                      "none",             "filler"),
    ("uh huh",                          "none",             "filler"),
    ("hmm",                             "none",             "filler"),
    ("alright",                         "none",             "filler"),
    ("thanks",                          "none",             "filler"),

    # ── edge cases ────────────────────────────────────────────────────────────
    ("",                                "none",             "edge"),
    ("open",                            "open_app",         "edge"),   # single word
    ("press",                           "press_key",        "edge"),   # single word
    ("click here",                      "click_here",       "edge"),
    ("tap this",                        "click_here",       "edge"),
]

# Whisper WER test pairs — only used if .wav files exist
# Format: (wav_path, reference_transcript)
# Place .wav files in eval_outputs/wav/ and update paths here
WAV_TEST_CASES = [
    # ("eval_outputs/wav/open_chrome.wav",   "open chrome"),
    # ("eval_outputs/wav/screenshot.wav",    "take a screenshot"),
    # ("eval_outputs/wav/press_ctrl_c.wav",  "press ctrl c"),
]


# ══════════════════════════════════════════════════════════════════════════════
# IMPORTS
# ══════════════════════════════════════════════════════════════════════════════

print("=" * 70)
print("ANIS VOICE PIPELINE EVALUATION")
print("=" * 70)

# Intent classifier
print("\n[1/4] Loading intent classifier...")
from voice_pipeline import classify
CLASSIFIER = "voice_pipeline"
print("      Loaded from voice_pipeline.py (rule engine + distilbert)")
# sklearn
try:
    from sklearn.metrics import (
        accuracy_score, classification_report,
        ConfusionMatrixDisplay, confusion_matrix
    )
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    SKLEARN_OK = True
    print("[2/4] sklearn + matplotlib ready")
except ImportError:
    SKLEARN_OK = False
    print("[2/4] sklearn/matplotlib missing — install with: pip install scikit-learn matplotlib")
    print("      Continuing without visualisations...")

# jiwer (optional)
try:
    from jiwer import wer as compute_wer
    JIWER_OK = True
    print("[3/4] jiwer ready (WER computation enabled)")
except ImportError:
    JIWER_OK = False
    print("[3/4] jiwer not installed — WER stage will be skipped")
    print("      Install with: pip install jiwer")

print("[4/4] Running evaluation...\n")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 — FILLER REJECTION
# ══════════════════════════════════════════════════════════════════════════════

print("─" * 70)
print("STAGE 1: Filler / VAD Text-Level Rejection")
print("─" * 70)

filler_cases  = [(u, e, c) for u, e, c in TEST_CASES if c == "filler"]
filler_correct = 0

for utterance, expected, _ in filler_cases:
    intent, conf = classify(utterance)
    got_none = (intent in ("none", "not_possible_yet"))
    if got_none:
        filler_correct += 1
    marker = "✓" if got_none else "✗"
    print(f"  {marker} '{utterance}' → {intent} ({conf:.2f})")

frr = filler_correct / len(filler_cases) * 100 if filler_cases else 0
print(f"\nFiller Rejection Rate: {filler_correct}/{len(filler_cases)} ({frr:.1f}%)")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2 — INTENT CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "─" * 70)
print("STAGE 2: Intent Classification")
print("─" * 70)

INTENTS = [
    "open_app", "close_app", "click", "click_here",
    "scroll_up", "scroll_down", "type_text",
    "press_key", "screenshot", "search", "none",
]

results      = []
y_true       = []
y_pred       = []
rule_lats    = []
phi2_lats    = []
confidences  = []

header = f"{'Utterance':<40} {'Expected':<14} {'Got':<14} {'Conf':>5}  {'Path':<6} {'OK'}"
print(header)
print("-" * len(header))

for utterance, expected, category in TEST_CASES:
    t0     = time.perf_counter()
    intent, conf = classify(utterance)
    elapsed = (time.perf_counter() - t0) * 1000

    # Normalise "not_possible_yet" → "none" for consistent labelling
    if intent == "not_possible_yet":
        intent = "none"

    path   = "rule" if conf == 1.0 else "phi2"
    match  = (intent == expected)
    marker = "✓" if match else "✗"

    if path == "rule":
        rule_lats.append(elapsed)
    else:
        phi2_lats.append(elapsed)
        confidences.append((conf, match))

    y_true.append(expected)
    y_pred.append(intent)

    results.append({
        "utterance":  utterance,
        "expected":   expected,
        "predicted":  intent,
        "confidence": round(conf, 4),
        "latency_ms": round(elapsed, 2),
        "correct":    match,
        "path":       path,
        "category":   category,
    })

    print(f"  {utterance:<40} {expected:<14} {intent:<14} {conf:>5.2f}  {path:<6} {marker}")

# ── Summary stats ─────────────────────────────────────────────────────────────
total   = len(results)
correct = sum(r["correct"] for r in results)
acc     = correct / total * 100

rule_r  = [r for r in results if r["path"] == "rule"]
phi2_r  = [r for r in results if r["path"] == "phi2"]

rule_acc  = sum(r["correct"] for r in rule_r)  / len(rule_r)  * 100 if rule_r  else 0
phi2_acc  = sum(r["correct"] for r in phi2_r)  / len(phi2_r)  * 100 if phi2_r  else 0
rule_cov  = len(rule_r) / total * 100

avg_rule_lat  = np.mean(rule_lats)  if rule_lats  else 0
avg_phi2_lat  = np.mean(phi2_lats)  if phi2_lats  else 0

print("\n" + "=" * 70)
print(f"OVERALL ACCURACY  : {correct}/{total} ({acc:.1f}%)")
print(f"Rule engine       : {sum(r['correct'] for r in rule_r)}/{len(rule_r)} "
      f"({rule_acc:.1f}%)  coverage {rule_cov:.1f}%  avg {avg_rule_lat:.2f} ms")
print(f"Phi-2 / clf path  : {sum(r['correct'] for r in phi2_r)}/{len(phi2_r)} "
      f"({phi2_acc:.1f}%)  avg {avg_phi2_lat:.2f} ms")

# ── Per-intent ────────────────────────────────────────────────────────────────
print("\nPer-intent accuracy:")
intent_stats = {}
for r in results:
    intent_stats.setdefault(r["expected"], []).append(r["correct"])
for k, v in sorted(intent_stats.items()):
    n = len(v); c = sum(v)
    bar = "█" * c + "░" * (n - c)
    print(f"  {k:<16} {c}/{n}  ({c/n*100:>5.1f}%)  {bar}")

# ── Per-category ──────────────────────────────────────────────────────────────
print("\nAccuracy by utterance category:")
cat_stats = {}
for r in results:
    cat_stats.setdefault(r["category"], []).append(r["correct"])
for k, v in sorted(cat_stats.items()):
    n = len(v); c = sum(v)
    print(f"  {k:<12} {c}/{n}  ({c/n*100:>5.1f}%)")

# ── Confidence threshold sweep ────────────────────────────────────────────────
if confidences:
    print("\nConfidence threshold sweep (Phi-2 / clf path only):")
    print(f"  {'Threshold':>10}  {'Accepted':>10}  {'Accuracy':>10}")
    threshold_data = []
    for thresh in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.82, 0.85, 0.90]:
        accepted = [(c, m) for c, m in confidences if c >= thresh]
        if accepted:
            ta = sum(m for _, m in accepted) / len(accepted) * 100
        else:
            ta = 0
        threshold_data.append((thresh, len(accepted), ta))
        print(f"  {thresh:>10.2f}  {len(accepted):>10}  {ta:>9.1f}%")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 3 — WHISPER WER (optional)
# ══════════════════════════════════════════════════════════════════════════════

wer_results = []

if WAV_TEST_CASES and JIWER_OK:
    print("\n" + "─" * 70)
    print("STAGE 3: Whisper ASR — Word Error Rate")
    print("─" * 70)

    try:
        from whisper_asr import transcribe_audio
        import soundfile as sf

        for wav_path, reference in WAV_TEST_CASES:
            if not os.path.isfile(wav_path):
                print(f"  SKIP {wav_path} (file not found)")
                continue
            audio, sr = sf.read(wav_path, dtype="float32")
            t0         = time.perf_counter()
            hypothesis = transcribe_audio(audio)
            lat        = (time.perf_counter() - t0) * 1000
            score      = compute_wer(reference, hypothesis)
            keyword    = reference.split()[0]
            kw_ok      = keyword in hypothesis

            wer_results.append({
                "wav":        wav_path,
                "reference":  reference,
                "hypothesis": hypothesis,
                "wer":        round(score, 4),
                "kw_correct": kw_ok,
                "latency_ms": round(lat, 2),
            })
            marker = "✓" if kw_ok else "✗"
            print(f"  {marker} ref: '{reference}'")
            print(f"      hyp: '{hypothesis}'  WER={score:.2f}  lat={lat:.0f}ms")

        if wer_results:
            avg_wer = np.mean([r["wer"] for r in wer_results])
            cka     = sum(r["kw_correct"] for r in wer_results) / len(wer_results) * 100
            avg_lat = np.mean([r["latency_ms"] for r in wer_results])
            print(f"\n  Avg WER              : {avg_wer:.3f}")
            print(f"  Command Keyword Acc  : {cka:.1f}%")
            print(f"  Avg Whisper latency  : {avg_lat:.0f} ms")

            with open(out("wer_report.txt"), "w") as f:
                f.write("WHISPER WER REPORT\n" + "="*50 + "\n\n")
                for r in wer_results:
                    f.write(f"File : {r['wav']}\n")
                    f.write(f"Ref  : {r['reference']}\n")
                    f.write(f"Hyp  : {r['hypothesis']}\n")
                    f.write(f"WER  : {r['wer']:.4f}  KW_OK: {r['kw_correct']}  "
                            f"Lat: {r['latency_ms']:.0f}ms\n\n")
            print(f"  Saved: eval_outputs/wer_report.txt")

    except ImportError as e:
        print(f"  SKIP: {e}")
else:
    print("\n[STAGE 3] Whisper WER: SKIPPED")
    print("  To enable: add .wav file paths to WAV_TEST_CASES and install jiwer")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 4 — VISUALISATIONS
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "─" * 70)
print("STAGE 4: Generating Visualisations")
print("─" * 70)

if not SKLEARN_OK:
    print("  SKIPPED — install scikit-learn and matplotlib")
else:
    # ── 1. Confusion matrix ───────────────────────────────────────────────────
    labels = sorted(set(y_true + y_pred))
    cm     = confusion_matrix(y_true, y_pred, labels=labels)
    fig, ax = plt.subplots(figsize=(10, 8))
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=labels)
    disp.plot(ax=ax, colorbar=True, cmap="Blues")
    ax.set_title("Intent Classification — Confusion Matrix", fontsize=13)
    plt.xticks(rotation=45, ha="right", fontsize=9)
    plt.yticks(fontsize=9)
    plt.tight_layout()
    plt.savefig(out("confusion_matrix.png"), dpi=150)
    plt.close()
    print("  Saved: confusion_matrix.png")

    # ── 2. Latency distribution ───────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(7, 5))
    data    = [rule_lats, phi2_lats] if phi2_lats else [rule_lats]
    labels_lat = ["Rule Engine", "Phi-2 / clf"] if phi2_lats else ["Rule Engine"]
    bp = ax.boxplot(data, labels=labels_lat, patch_artist=True,
                    boxprops=dict(facecolor="#a8d8ea"),
                    medianprops=dict(color="navy", linewidth=2))
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Intent Classification Latency by Path")
    ax.set_yscale("log")
    plt.tight_layout()
    plt.savefig(out("latency_dist.png"), dpi=150)
    plt.close()
    print("  Saved: latency_dist.png")

    # ── 3. Accuracy by category ───────────────────────────────────────────────
    cats  = sorted(cat_stats.keys())
    accs  = [sum(cat_stats[c]) / len(cat_stats[c]) * 100 for c in cats]
    colors = ["#2ecc71" if a >= 80 else "#e67e22" if a >= 60 else "#e74c3c" for a in accs]
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(cats, accs, color=colors, edgecolor="white")
    ax.set_ylim(0, 110)
    ax.set_ylabel("Accuracy (%)")
    ax.set_title("Intent Classification Accuracy by Utterance Category")
    for bar, acc in zip(bars, accs):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f"{acc:.0f}%", ha="center", va="bottom", fontsize=10)
    plt.tight_layout()
    plt.savefig(out("accuracy_by_type.png"), dpi=150)
    plt.close()
    print("  Saved: accuracy_by_type.png")

    # ── 4. Confidence threshold sweep ─────────────────────────────────────────
    if confidences and len(threshold_data) > 1:
        thresholds = [t for t, _, _ in threshold_data]
        accs_t     = [a for _, _, a in threshold_data]
        accepted_t = [n for _, n, _ in threshold_data]
        fig, ax1 = plt.subplots(figsize=(8, 5))
        ax2 = ax1.twinx()
        ax1.plot(thresholds, accs_t,     "b-o", label="Accuracy (%)")
        ax2.plot(thresholds, accepted_t, "r--s", label="Accepted samples")
        ax1.axvline(x=0.82, color="gray", linestyle=":", label="Current threshold (0.82)")
        ax1.set_xlabel("Confidence Threshold")
        ax1.set_ylabel("Accuracy (%)", color="blue")
        ax2.set_ylabel("Accepted Samples", color="red")
        ax1.set_title("Phi-2 / Classifier: Accuracy vs Confidence Threshold")
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="lower left")
        plt.tight_layout()
        plt.savefig(out("threshold_sweep.png"), dpi=150)
        plt.close()
        print("  Saved: threshold_sweep.png")


# ══════════════════════════════════════════════════════════════════════════════
# SAVE FULL RESULTS
# ══════════════════════════════════════════════════════════════════════════════

def _avg(lst): return round(float(np.mean(lst)), 3) if lst else 0
def _std(lst): return round(float(np.std(lst)),  3) if lst else 0

summary = {
    "classifier":       CLASSIFIER,
    "total_cases":      total,
    "overall_accuracy": round(acc, 1),
    "filler_rejection": round(frr, 1),
    "rule_engine": {
        "total":        len(rule_r),
        "correct":      sum(r["correct"] for r in rule_r),
        "accuracy_pct": round(rule_acc, 1),
        "coverage_pct": round(rule_cov, 1),
        "latency_mean_ms": _avg(rule_lats),
        "latency_std_ms":  _std(rule_lats),
    },
    "phi2_clf": {
        "total":        len(phi2_r),
        "correct":      sum(r["correct"] for r in phi2_r),
        "accuracy_pct": round(phi2_acc, 1),
        "latency_mean_ms": _avg(phi2_lats),
        "latency_std_ms":  _std(phi2_lats),
    },
    "per_intent":       {k: {"n": len(v), "correct": sum(v),
                              "accuracy_pct": round(sum(v)/len(v)*100, 1)}
                          for k, v in intent_stats.items()},
    "per_category":     {k: {"n": len(v), "correct": sum(v),
                              "accuracy_pct": round(sum(v)/len(v)*100, 1)}
                          for k, v in cat_stats.items()},
    "wer_results":      wer_results,
    "per_case":         results,
}

with open(out("results.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

# Human-readable summary for LaTeX
with open(out("summary.txt"), "w", encoding="utf-8") as f:
    f.write("ANIS VOICE PIPELINE — EVALUATION SUMMARY\n")
    f.write("=" * 50 + "\n\n")
    f.write(f"Classifier backend   : {CLASSIFIER}\n")
    f.write(f"Total test cases     : {total}\n")
    f.write(f"Overall accuracy     : {acc:.1f}%\n")
    f.write(f"Filler rejection     : {frr:.1f}%\n\n")
    f.write(f"Rule engine accuracy : {rule_acc:.1f}%  "
            f"(coverage {rule_cov:.1f}%,  avg {_avg(rule_lats):.2f} ms)\n")
    f.write(f"Phi-2/clf accuracy   : {phi2_acc:.1f}%  "
            f"(avg {_avg(phi2_lats):.2f} ms ± {_std(phi2_lats):.2f})\n\n")
    f.write("Per-intent accuracy:\n")
    for k, v in sorted(intent_stats.items()):
        n = len(v); c = sum(v)
        f.write(f"  {k:<18} {c}/{n}  ({c/n*100:.1f}%)\n")
    f.write("\nPer-category accuracy:\n")
    for k, v in sorted(cat_stats.items()):
        n = len(v); c = sum(v)
        f.write(f"  {k:<14} {c}/{n}  ({c/n*100:.1f}%)\n")
    if wer_results:
        avg_wer = np.mean([r["wer"] for r in wer_results])
        cka     = sum(r["kw_correct"] for r in wer_results) / len(wer_results) * 100
        f.write(f"\nWhisper WER          : {avg_wer:.3f}\n")
        f.write(f"Keyword accuracy     : {cka:.1f}%\n")

print("\n" + "=" * 70)
print("EVALUATION COMPLETE")
print(f"Overall accuracy : {correct}/{total} ({acc:.1f}%)")
print(f"Outputs saved to : {OUT_DIR}/")
print("  results.json | summary.txt | *.png")
print("=" * 70)
print("\nPaste numbers from summary.txt directly into your LaTeX report.")
