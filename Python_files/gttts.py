import os
import csv
from gtts import gTTS

OUTPUT_DIR = "audio_samples"
CSV_FILE = "dataset.csv"

os.makedirs(OUTPUT_DIR, exist_ok=True)

data = [
    ("open chrome","open_app","chrome"),
    ("launch chrome browser","open_app","chrome"),
    # 👉 paste full dataset here
]

with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["filename", "text", "intent", "argument"])

    for i, (text, intent, arg) in enumerate(data):
        filename = f"sample_{i}.mp3"
        filepath = os.path.join(OUTPUT_DIR, filename)

        tts = gTTS(text)
        tts.save(filepath)

        writer.writerow([filename, text, intent, arg])

print("Dataset + audio generated successfully")