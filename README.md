🎙️🧠 Acoustic Neural Input System (ANIS)

A multimodal human–computer interaction system enabling hands-free computer control using voice commands and bio-signal inputs, designed for accessibility-focused interaction.

---

📌 Project Overview

ANIS is an accessibility-driven system that allows users to interact with a computer without traditional input devices.

It combines:
- Voice-based command execution
- Conversational AI assistant mode
- Bio-signal-based input using EOG/EEG hardware

The system is built using open-source tools and low-cost hardware, making it suitable for real-world assistive applications and experimentation.

---

🧩 Key Features

### 🎤 Voice Command System
- Speech-to-text using Whisper  
- LLM-based intent detection  
- Execution of system-level commands  
- Validation layer for safe operation  

---

### 🤖 Assistant Mode
- Activated using the keyword **"assistant"**  
- Runs a conversational loop using Groq LLM  
- Maintains short-term context  
- Supports natural queries and exit commands  

---

### 🧠 Bio-Signal Input (EOG / EEG)

- Signal acquisition using:
  - BioAmp EXG Pill  
  - ESP32 ADC interface  

- Processing pipeline:
  - Signal filtering and smoothing  
  - Noise reduction  
  - Direction / pattern detection  

- Maps signals to:
  - Cursor movement  
  - Navigation commands  

⚠️ Note:  
This module is functional but experimental, and accuracy depends on calibration and hardware conditions.

---

### ⚡ Real-Time UI

- WebSocket-based live communication  
- Displays:
  - Voice transcripts  
  - Assistant responses  
  - Bio-signal visualizations  
- Includes animated feedback elements  

---

🧠 System Architecture

Voice Pipeline:  
Mic → Whisper → LLM → Intent → Execution  

Assistant Mode:  
Trigger → Conversational Loop → Response → TTS  

Bio-Signal Pipeline:  
Electrodes → BioAmp → ESP32 → Processing → Command Mapping  

Frontend:  
Backend → WebSocket → Live UI  

---

🚧 Limitations

- Bio-signal accuracy depends heavily on hardware quality and calibration  
- EEG/EOG signals are noisy and require controlled conditions  
- Voice recognition is affected by background noise  
- System is not suitable for safety-critical environments  

---

🔮 Future Scope

- Improved EEG-based intent classification  
- Adaptive calibration for bio-signal inputs  
- Multi-step command planning  
- Overlay-based persistent UI  
- Parallel processing for multimodal inputs  