// ========= CONFIG =========
//pin for anaglog signal
const int eegPin = 34;
//sampling signals at 250hz
const int sampleRate = 250;

//for rms, samples are only 200
const int fastWindow = 200;
//for smoothness
const float slowAlpha = 0.02;

// Y-axis limits (FOR PLOTTER)
const float Y_MIN = 1500;
const float Y_MAX = 2300;

// ========= VARIABLES =========
//stores the last 200 signals for rms
float fastBuf[fastWindow];
int fastIndex = 0;
bool fastFilled = false;


//for dc offsets if any
float dcEstimate = 0;
const float dcAlpha = 0.001;

//RMS values
float fastRMS = 0;
float slowRMS = 0;


//manual time calucations
unsigned long lastSample = 0;
//interval for sampling signals
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
    //to centralize the signal to 2048
    float signal = raw - 2048;

    // DC removal
    dcEstimate = (1 - dcAlpha) * dcEstimate + dcAlpha * signal;
    float hpSignal = signal - dcEstimate;

    // Fast RMS circular buffer
    fastBuf[fastIndex] = hpSignal;
    fastIndex++;
    if (fastIndex >= fastWindow) {
      fastIndex = 0;
      fastFilled = true;
    }
    //runs when the buffer is full with sample the rms is calclulated
    if (fastFilled) {
      float sumSq = 0;
      for (int i = 0; i < fastWindow; i++) {
        sumSq += fastBuf[i] * fastBuf[i];
      }
      
      fastRMS = sqrt(sumSq / fastWindow);
      slowRMS = (1 - slowAlpha) * slowRMS + slowAlpha * fastRMS;

      // ---- Output ----
      Serial.print(raw);
      Serial.print(",");
      Serial.print(0);
      Serial.print(",");
      Serial.println(4095);
    }
  }
}
