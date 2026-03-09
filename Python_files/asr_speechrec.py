import numpy as np
import speech_recognition as sr

_recognizer = sr.Recognizer()

def transcribe_audio(audio_np, sample_rate=16000):
    if audio_np is None or len(audio_np) == 0:
        print("short audio")
        return ""
    int16_audio = np.int16(audio_np * 32767)

    audio_data = sr.AudioData(
        int16_audio.tobytes(),
        sample_rate,
        2
    )
    return _recognizer.recognize_google(audio_data)