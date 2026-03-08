🎙️🧠 Voice & EEG Assisted Navigational Accessibility System
  A multimodal accessibility system enabling hands-free computer navigation using voice commands and EEG-based signals, designed for users with motor impairments.

📌 Project Overview
  This project proposes and implements a hybrid human–computer interaction system that allows users to control and navigate a computer system using natural voice commands and brain signal inputs (EEG).
  The system focuses on accessibility-first design, enabling users with physical disabilities to interact with standard desktop environments without relying on traditional input devices such as a mouse or keyboard.
  This is developed as a BTech Mini Project using only free and open-source tools, optimized to run on consumer-grade hardware without GPU dependency.
  
  🎯 Objectives
    Enable hands-free system navigation using voice commands
    Integrate EEG-based intent detection as an alternative input method
    Design a deterministic and safe command execution pipeline  
    Provide overlay-based visual navigation aids (grid, number overlays)
    Ensure low-latency, real-time interaction
    Maintain modularity for future assistive extensions

🧩 Key Features
  Voice Navigation
    Command-based cursor control
    Application launch and window management
    Scroll, click, select, and grid-based navigation
    Ambiguity handling using validation layers

  EEG Assistance (Experimental)
    Real-time EEG signal acquisition
    Signal preprocessing and feature extraction
    Mapping EEG patterns to navigation intents
    Acts as a fallback or complementary control mode

  System Overlays
    Grid overlay for precise screen selection
    Numbered UI overlays for accessibility
    Non-intrusive, always-on-top rendering

+---------------------------------------------------+
|           VOICE INPUT & PROCESSING                |
|---------------------------------------------------|
|  Voice Activity Detection (VAD)                   |
|  Voice Input                                     |
|  Speech-to-Text (STT)                             |
|  LLM Engine (Intent & Context Detection)          |
|  Parsed JSON Output                               |
+---------------------------+-----------------------+
                            |
                            v
+---------------------------------------------------+
|           COMMAND EXECUTION PIPELINE               |
|---------------------------------------------------|
|  Parsed JSON Input                                |
|  Category Router                                  |
|                                                   |
|  +------------------+  +----------------------+  |
|  | Navigation       |  | Information          |  |
|  | Commands         |  | Commands              |  |
|  +------------------+  +----------------------+  |
|  | Control Commands |                           |
|  +------------------+                           |
|                                                   |
|  Validation Layer (Whitelist / Safety Rules)      |
|                                                   |
|  Application Executor (OS Actions)                |
|  Confirmation Feedback (Audio / Visual)           |
+---------------------------+-----------------------+
                            |
                            v
+---------------------------------------------------+
|                NAVIGATION SIGNALS                  |
+---------------------------+-----------------------+
                            |
                            v
+---------------------------------------------------+
|               EXECUTE NAVIGATION                   |
|---------------------------------------------------|
|  Grid Overlay (3x3 / 5x5)                          |
|  Move Cursor to Cell                               |
|  Click / Scroll                                   |
|  Visual + Audio Feedback                           |
+---------------------------------------------------+


                 ┌────────────────────────────┐
                 │        DASHBOARD            │
                 │----------------------------│
                 │  System Control Visuals     │
                 │  Audio Waveform             │
                 │  Raw Signal Plots            │
                 │  Control Visuals             │
                 └─────────────┬──────────────┘
                               |
                               v
+---------------------------------------------------+
|                  COMMUNICATIONS                    |
+---------------------------------------------------+


+---------------------------------------------------+
|             EEG SIGNAL ACQUISITION                 |
|---------------------------------------------------|
|  Dry/Wet Electrodes                                |
|  BioAmp EXG Pill                                   |
|  ESP32 ADC                                         |
|  Computer (USB / Serial Input)                     |
+---------------------------+-----------------------+
                            |
                            v
+---------------------------------------------------+
|              SIGNAL PREPROCESSING                  |
|---------------------------------------------------|
|  Remove Offsets                                    |
|  Bandpass Filter                                   |
|  Remove External Noise                             |
|  Signal Smoothing                                  |
|  (Python Processing)                               |
+---------------------------+-----------------------+
                            |
                            v
+---------------------------------------------------+
|               COMMAND MAPPING                      |
|---------------------------------------------------|
|  Window Segmentation                               |
|  Baseline Reference                                |
|  Decision Logic                                    |
|                                                   |
|  Rule-Based Mapping                                |
|  OR                                                |
|  Classifier Model                                  |
|                                                   |
|  Generated Command                                 |
+---------------------------+-----------------------+
                            |
                            v
                   (Feeds into Command
                    Execution Pipeline)


🧠 Use Cases
  Users with motor disabilities
  Hands-free system operation
  Assistive navigation in educational or workplace setups
  Research in multimodal human–computer interaction

🚧 Limitations
  EEG accuracy depends on hardware quality
  Voice recognition performance affected by noise
  EEG module is experimental and under active improvement
  Not intended for safety-critical system control

🔮 Future Enhancements
  Custom-trained intent classification models
  Adaptive learning for user-specific EEG patterns
  Multilingual voice support
  Mobile companion application
  Improved calibration workflows

📚 Academic Relevance
This project aligns with topics in:
  Assistive Technologies
  Human–Computer Interaction (HCI)
  AI-driven Accessibility Systems
  Multimodal Input Processing
