"""
intent_server.py -- Run this ONCE. Loads Phi-2 + LoRA into GPU memory and
stays alive as a background process. main.py connects to it via a local
TCP socket, so the model is never reloaded between runs.

Usage
─────
  # Terminal 1 -- start the server (do this once after boot)
  python intent_server.py

  # Terminal 2 -- run the voice pipeline as many times as you like
  python main.py

The server listens on 127.0.0.1:62199 (localhost only, not exposed externally).
Send a UTF-8 JSON line:  {"text": "open chrome"}
Receive a UTF-8 JSON line: {"intent": "open_app", "normalized": "open chrome", "confidence": 1.0}
"""

import json
import os
import re
import socket
import threading
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel

# ── Config ────────────────────────────────────────────────────────────────────
HOST       = "127.0.0.1"
PORT       = 62199
BACKLOG    = 8          # max queued connections

os.environ["TRANSFORMERS_OFFLINE"] = "1"

BASE_MODEL = "microsoft/phi-2"
LORA_MODEL = r"C:\Users\User\Documents\Mini project\Model\lora-training\phi2_intent_lora"

# ── Valid intents ─────────────────────────────────────────────────────────────
VALID_INTENTS = {
    "open_app", "close_app", "click", "scroll_up", "scroll_down",
    "type_text", "press_key", "screenshot", "search", "ui_list",
    "not_possible_yet",
}

# ── Filler / noise phrases ────────────────────────────────────────────────────
_FILLERS = {
    "okay", "ok", "uh", "um", "hmm", "yeah", "yes", "no", "done",
    "alright", "right", "sure", "well", "so", "anyway", "never mind",
    "thanks", "thank you", "hello", "hi", "hey", "good", "great",
}

# ── Rule engine ───────────────────────────────────────────────────────────────
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(open|launch|start|run)\b\s+\w"),              "open_app"),
    (re.compile(r"\b(close|quit|kill|shut\s+down)\b\s+\w"),        "close_app"),
    (re.compile(r"\b(click|tap|hit)\b"),                           "click"),
    (re.compile(r"\bscroll\s+up\b"),                               "scroll_up"),
    (re.compile(r"\bscroll\s+(down|bottom)\b"),                    "scroll_down"),
    (re.compile(r"\b(type|write|input)\b\s+\w"),                   "type_text"),
    (re.compile(r"\b(press\s+key|hotkey|shortcut)\b"),             "press_key"),
    (re.compile(r"\bpress\s+(enter|escape|esc|tab|space|backspace|delete|ctrl|alt|shift|win)\b"), "press_key"),
    (re.compile(r"\b(screenshot|capture\s+screen|take\s+a?\s*screenshot)\b"), "screenshot"),
    (re.compile(r"\b(search|look\s+up|google)\b\s+\w"),            "search"),
    (re.compile(r"\b(list|show\s+me|display)\b"),                  "ui_list"),
]

_PROMPT_TEMPLATE = """\
### Instruction:
Classify the user command into exactly one intent label.
Valid labels: open_app, close_app, click, scroll_up, scroll_down, \
type_text, press_key, screenshot, search, ui_list, not_possible_yet.
Reply with the label only -- no explanation.

### Input:
{text}

### Output:
"""

# ── Load model ────────────────────────────────────────────────────────────────
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[intent_server] Loading Phi-2 on {device}...")

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
tokenizer.pad_token = tokenizer.eos_token

if device == "cuda":
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="cuda",
        trust_remote_code=True,
    )
else:
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float32,
        device_map="cpu",
        trust_remote_code=True,
    )

model = PeftModel.from_pretrained(base_model, LORA_MODEL, is_trainable=False)
model.eval()

print("[intent_server] Running warm-up...")
with torch.no_grad():
    _wu = tokenizer("open notepad", return_tensors="pt").to(device)
    model.generate(**_wu, max_new_tokens=2, do_sample=False,
                   pad_token_id=tokenizer.eos_token_id)
print(f"[intent_server] Ready -- listening on {HOST}:{PORT}")


# ── Inference ─────────────────────────────────────────────────────────────────
_infer_lock = threading.Lock()   # one inference at a time on the GPU

def _classify(text: str) -> tuple[str, str, float]:
    normalized = text.lower().strip()

    if not normalized:
        return "not_possible_yet", normalized, 0.0

    words = [w for w in re.findall(r"[a-z]+", normalized) if len(w) > 1]
    if len(words) < 2:
        return "not_possible_yet", normalized, 0.0

    if normalized.rstrip(".,!?") in _FILLERS or all(w in _FILLERS for w in words):
        return "not_possible_yet", normalized, 0.0

    # Rule engine
    for pattern, intent in _RULES:
        if pattern.search(normalized):
            return intent, normalized, 1.0

    # Phi-2 + LoRA
    try:
        with _infer_lock:
            prompt = _PROMPT_TEMPLATE.format(text=normalized)
            inputs = tokenizer(prompt, return_tensors="pt").to(device)
            with torch.no_grad():
                output = model.generate(
                    **inputs,
                    max_new_tokens=6,
                    do_sample=False,
                    pad_token_id=tokenizer.eos_token_id,
                    output_scores=True,
                    return_dict_in_generate=True,
                )
            new_tokens = output.sequences[0][inputs["input_ids"].shape[1]:]
            decoded    = tokenizer.decode(new_tokens, skip_special_tokens=True)
            label      = re.sub(r"[^a-z_]", "",
                                decoded.lower().split()[0] if decoded.split() else "")
            confidence = 0.0
            if output.scores:
                probs      = torch.softmax(output.scores[0][0], dim=-1)
                confidence = float(probs.max().item())
            if label not in VALID_INTENTS:
                label = "not_possible_yet"
            return label, normalized, confidence
    except Exception as exc:
        print(f"[intent_server] Inference error: {exc}")
        return "not_possible_yet", normalized, 0.0


# ── Connection handler ────────────────────────────────────────────────────────
def _handle_client(conn: socket.socket, addr) -> None:
    with conn:
        buf = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    payload = json.loads(line.decode("utf-8"))
                    text    = payload.get("text", "")
                    intent, normalized, confidence = _classify(text)
                    response = json.dumps({
                        "intent":     intent,
                        "normalized": normalized,
                        "confidence": confidence,
                    }) + "\n"
                    conn.sendall(response.encode("utf-8"))
                except Exception as exc:
                    err = json.dumps({"error": str(exc)}) + "\n"
                    conn.sendall(err.encode("utf-8"))


# ── Server loop ───────────────────────────────────────────────────────────────
def main() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(BACKLOG)
        print(f"[intent_server] Accepting connections...  (Ctrl+C to stop)")
        try:
            while True:
                conn, addr = srv.accept()
                t = threading.Thread(
                    target=_handle_client, args=(conn, addr), daemon=True
                )
                t.start()
        except KeyboardInterrupt:
            print("\n[intent_server] Shutting down.")


if __name__ == "__main__":
    main()