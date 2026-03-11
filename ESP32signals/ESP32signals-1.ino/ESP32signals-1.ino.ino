#define HOR_AMP_PIN 34
#define VER_AMP_PIN 39

#define SMOOTH_ALPHA 0.1 //to make it smoother
#define DRIFT_ALPHA 0.001 //for removing small impedences
#define MAX_EXPECTED 700 //to control the scaling values

void setup() {
  Serial.begin(115200);
  delay(1000);
}

void loop() {

  int horizontal_raw = analogRead(HOR_AMP_PIN);
  int vertical_raw   = analogRead(VER_AMP_PIN);

  float hor_normalized = filter(horizontal_raw, 0);
  float ver_normalized = filter(vertical_raw, 1);
  Serial.print(hor_normalized);
  Serial.print(",");
  Serial.println(ver_normalized);

  delay(5);
}


// Separate memory for each axis
float smoothSignal[2] = {0, 0};
float drift[2] = {0, 0};

float filter(int raw, int axis) {

  float centered = raw - 2000.0;
  //to get the signal to smoothen out 
  smoothSignal[axis] =
      SMOOTH_ALPHA * centered +
      (1 - SMOOTH_ALPHA) * smoothSignal[axis];

  drift[axis] =
      DRIFT_ALPHA * smoothSignal[axis] +
      (1 - DRIFT_ALPHA) * drift[axis];

  float stabilized = smoothSignal[axis] - drift[axis];

  //to normalize the values between 1 and -1
  float normalized = stabilized / MAX_EXPECTED;

  //ceiling limit
  if (normalized > 1.0) normalized = 1.0;
  if (normalized < -1.0) normalized = -1.0;

  return normalized;
}
