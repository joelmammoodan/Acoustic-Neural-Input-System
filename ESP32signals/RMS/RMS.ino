// ========= CONFIG =========
const int eegPin = 34;
const int sampleRate = 250;

const int fastWindow = 200;
const float slowAlpha = 0.02;

// Y-axis limits (FOR PLOTTER)
const float Y_MIN = 1500;
const float Y_MAX = 2300;

// ========= VARIABLES =========
float fastBuf[fastWindow];
int fastIndex = 0;
bool fastFilled = false;

float dcEstimate = 0;
const float dcAlpha = 0.001;

float fastRMS = 0;
float slowRMS = 0;

unsigned long lastSample = 0;
const unsigned long sampleInterval = 1000000 / sampleRate;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("SlowRMS,Ymin,Ymax");
}

void loop() {
  if (micros() - lastSample >= sampleInterval) {
    lastSample = micros();

    int raw = analogRead(eegPin);
    float signal = raw - 2048;

    // DC removal
    dcEstimate = (1 - dcAlpha) * dcEstimate + dcAlpha * signal;
    float hpSignal = signal - dcEstimate;

    // Fast RMS buffer
    fastBuf[fastIndex] = hpSignal;
    fastIndex++;
    if (fastIndex >= fastWindow) {
      fastIndex = 0;
      fastFilled = true;
    }

    if (fastFilled) {
      float sumSq = 0;
      for (int i = 0; i < fastWindow; i++) {
        sumSq += fastBuf[i] * fastBuf[i];
      }

      fastRMS = sqrt(sumSq / fastWindow);
      slowRMS = (1 - slowAlpha) * slowRMS + slowAlpha * fastRMS;

      // ---- Output ----
      Serial.print(slowRMS);
      Serial.print(",");
      Serial.print(Y_MIN);
      Serial.print(",");
      Serial.println(Y_MAX);
    }
  }
}
