import time
import keyboard
from audio_input import start_recording, stop_recording
from asr_speechrec import transcribe_audio
from intent_model import handle_intent
def main():
    print("Hold 'Spacebar' to speak. Release to transcribe.")

    is_recording = False
    
    try:
        while True:
            if keyboard.is_pressed("space"):
                if not is_recording:
                    print("🔴 Recording...")
                    start_recording()
                    is_recording = True
            
            else:
                if is_recording:
                    print("⏹️ Stopped. Processing...")
                    audio = stop_recording()
                    is_recording = False
                    try:
                        text = transcribe_audio(audio)
                        print(f"✅ You said: {text}")
                        intent = handle_intent(text)
                        print(f"Intent: {intent}")
                    except Exception as e:
                        print(f"❌ Transcription failed: {e}")
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nProgram interrupted.")

if __name__ == "__main__":
    main()