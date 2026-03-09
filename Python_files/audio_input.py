import sounddevice as sd
import numpy as np

SAMPLE_RATE = 16000
CHANNELS = 1

recording = False
audio_frames = []
stream = None

def audio_callback(indata, frames, time_info, status):
    global recording
    if recording:
        audio_frames.append(indata.copy())

def start_recording():
    global recording, stream, audio_frames

    audio_frames = []
    recording = True

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        callback=audio_callback
    )
    stream.start()

def stop_recording():
    global recording, stream, audio_frames
    recording = False

    if stream is None:
        print("no audio recorded")
        
        return None

    recording = False
    stream.stop()
    stream.close()
    stream = None

    if not audio_frames:
        return None

    audio = np.concatenate(audio_frames, axis=0)[:, 0]
    audio_frames = []
    
    max_val = np.max(np.abs(audio))
    if max_val < 0.01: # Threshold for "silence"
        print("⚠️ Audio too quiet, ignoring.")
        return None
    audio = audio / (max_val + 1e-9)
    audio = audio * 0.9

    return audio
