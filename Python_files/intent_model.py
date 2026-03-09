import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import os

BASE_DIR = os.path.dirname(__file__)
MODEL_PATH = os.path.join(BASE_DIR, "phi2_intent")
device = "cuda" if torch.cuda.is_available() else "cpu"
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForCausalLM.from_pretrained(MODEL_PATH).to(device)
model.eval()
def handle_intent(text: str) -> str:
    prompt = f"User: {text}\nIntent:"
    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    with torch.no_grad():
        output = model.generate(
         **inputs,
         max_new_tokens=3,
         do_sample=False,
         pad_token_id=tokenizer.eos_token_id
        )
    decoded = tokenizer.decode(output[0], skip_special_tokens=True)

    if "Intent:" in decoded:
        intent = decoded.split("Intent:")[-1].strip().split()[0]
        return intent , text

    return "not_possible_yet"

