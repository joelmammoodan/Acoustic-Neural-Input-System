#define AMP_PIN 34
#define WINDOW_SIZE 10   // smoothing window

int samples[WINDOW_SIZE];
int sampleIndex = 0;
long sum = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);

  for (int i = 0; i < WINDOW_SIZE; i++) {
    samples[i] = 0;
  }
}

void loop() {
  int newSample = analogRead(AMP_PIN);

  // Remove oldest sample
  sum -= samples[sampleIndex];

  // Store new sample
  samples[sampleIndex] = newSample;
  sum += newSample;

  // Advance index safely
  sampleIndex = (sampleIndex + 1) % WINDOW_SIZE;

  // Smoothed output
  int smoothSignal = sum / WINDOW_SIZE;

  Serial.println(smoothSignal);
  Serial.print(",Min:0,Max:4095\n");
  delay(5);
}
