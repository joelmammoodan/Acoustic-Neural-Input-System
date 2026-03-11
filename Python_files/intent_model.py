"""
intent_model.py — Intent classification client.

Preferred path : connects to intent_server.py (127.0.0.1:62199) which keeps
                 Phi-2 loaded in GPU memory permanently → zero reload time.

Fallback path  : if the server is unreachable, loads Phi-2 locally (old
                 behaviour).  A warning is printed once so you know which
                 path is active.

Usage
─────
  Recommended:
    1.  python intent_server.py      ← run once, leave open
    2.  python main.py               ← connects instantly every time

  Without server:
    python main.py                   ← loads model locally (~17 s first run)
"""

import json
import os
import re
import socket
import threading
import torch

# ── Server connection config ──────────────────────────────────────────────────
_SERVER_HOST     = "127.0.0.1"
_SERVER_PORT     = 62199
_CONNECT_TIMEOUT = 1.0    # seconds — how long to wait when checking if server is up
_RECV_TIMEOUT    = 10.0   # seconds — max wait for a classification response

# ── Shared socket (one persistent connection reused across calls) ─────────────
_sock: socket.socket | None = None
_sock_lock = threading.Lock()
_using_server = False


def _try_connect() -> bool:
    global _sock, _using_server
    try:
        s = socket.create_connection((_SERVER_HOST, _SERVER_PORT),
                                     timeout=_CONNECT_TIMEOUT)
        s.settimeout(_RECV_TIMEOUT)
        _sock = s
        _using_server = True
        print(f"[intent_model] Connected to intent_server on "
              f"{_SERVER_HOST}:{_SERVER_PORT} — model already loaded.")
        return True
    except OSError:
        return False


def _server_classify(text: str) -> tuple[str, str, float] | None:
    global _sock
    payload = (json.dumps({"text": text}) + "\n").encode("utf-8")
    with _sock_lock:
        try:
            _sock.sendall(payload)
            buf = b""
            while b"\n" not in buf:
                chunk = _sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Server closed connection.")
                buf += chunk
            line = buf.split(b"\n")[0]
            data = json.loads(line.decode("utf-8"))
            if "error" in data:
                return None
            return data["intent"], data["normalized"], data["confidence"]
        except Exception as exc:
            print(f"[intent_model] Server comm error: {exc} — falling back to local.")
            try:
                _sock.close()
            except Exception:
                pass
            _sock = None
            return None


# ── Local fallback ────────────────────────────────────────────────────────────
_local_model     = None
_local_tokenizer = None
_local_device    = None
_local_lock      = threading.Lock()

def _ensure_local_model():
    global _local_model, _local_tokenizer, _local_device
    if _local_model is not None:
        return
    with _local_lock:
        if _local_model is not None:
            return
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from peft import PeftModel

        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        BASE_MODEL = "microsoft/phi-2"
        LORA_MODEL = r"C:\Users\User\Documents\Mini project\Model\lora-training\phi2_intent_lora"

        _local_device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[intent_model] Server not found — loading Phi-2 locally on {_local_device}...")

        tok = AutoTokenizer.from_pretrained(BASE_MODEL)
        tok.pad_token = tok.eos_token

        if _local_device == "cuda":
            bnb = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )
            base = AutoModelForCausalLM.from_pretrained(
                BASE_MODEL, quantization_config=bnb,
                device_map="cuda", trust_remote_code=True,
            )
        else:
            base = AutoModelForCausalLM.from_pretrained(
                BASE_MODEL, torch_dtype=torch.float32,
                device_map="cpu", trust_remote_code=True,
            )

        mdl = PeftModel.from_pretrained(base, LORA_MODEL, is_trainable=False)
        mdl.eval()

        with torch.no_grad():
            wu = tok("open notepad", return_tensors="pt").to(_local_device)
            mdl.generate(**wu, max_new_tokens=2, do_sample=False,
                         pad_token_id=tok.eos_token_id)

        _local_tokenizer = tok
        _local_model     = mdl
        print("[intent_model] Local model ready.")


_PROMPT_TEMPLATE = """\
### Instruction:
Classify the user command into exactly one intent label.
Valid labels: open_app, close_app, click, scroll_up, scroll_down, \
type_text, press_key, screenshot, search, ui_list, not_possible_yet.
Reply with the label only — no explanation.

### Input:
{text}

### Output:
"""

VALID_INTENTS = {
    "open_app", "close_app", "click", "scroll_up", "scroll_down",
    "type_text", "press_key", "screenshot", "search", "ui_list",
    "not_possible_yet",
}

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

_FILLERS = {
    "okay", "ok", "uh", "um", "hmm", "yeah", "yes", "no", "done",
    "alright", "right", "sure", "well", "so", "anyway", "never mind",
    "thanks", "thank you", "hello", "hi", "hey", "good", "great",
}


def _local_classify(normalized: str) -> tuple[str, float]:
    _ensure_local_model()
    try:
        prompt = _PROMPT_TEMPLATE.format(text=normalized)
        inputs = _local_tokenizer(prompt, return_tensors="pt").to(_local_device)
        with torch.no_grad():
            output = _local_model.generate(
                **inputs, max_new_tokens=6, do_sample=False,
                pad_token_id=_local_tokenizer.eos_token_id,
                output_scores=True, return_dict_in_generate=True,
            )
        new_tokens = output.sequences[0][inputs["input_ids"].shape[1]:]
        decoded    = _local_tokenizer.decode(new_tokens, skip_special_tokens=True)
        label      = re.sub(r"[^a-z_]", "",
                            decoded.lower().split()[0] if decoded.split() else "")
        confidence = 0.0
        if output.scores:
            probs      = torch.softmax(output.scores[0][0], dim=-1)
            confidence = float(probs.max().item())
        if label not in VALID_INTENTS:
            label = "not_possible_yet"
        return label, confidence
    except Exception as exc:
        print(f"[intent_model] Local inference error: {exc}")
        return "not_possible_yet", 0.0


# ── Attempt server connection at import time ──────────────────────────────────
_try_connect()


# ── Public API ────────────────────────────────────────────────────────────────

def handle_intent(text: str) -> tuple[str, str, float]:
    normalized = text.lower().strip() if text else ""

    if not normalized:
        return "not_possible_yet", "", 0.0

    words = [w for w in re.findall(r"[a-z]+", normalized) if len(w) > 1]
    if len(words) < 2:
        return "not_possible_yet", normalized, 0.0

    if normalized.rstrip(".,!?") in _FILLERS or all(w in _FILLERS for w in words):
        return "not_possible_yet", normalized, 0.0

    # Rule engine — always fast, no network
    for pattern, intent in _RULES:
        if pattern.search(normalized):
            return intent, normalized, 1.0

    # Server path
    if _sock is not None:
        result = _server_classify(normalized)
        if result:
            return result

    # Local fallback
    intent, confidence = _local_classify(normalized)
    return intent, normalized, confidence