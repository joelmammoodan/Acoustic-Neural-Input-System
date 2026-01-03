#define AMP_PIN 34

void setup() {
  // put your setup code here, to run once:
  Serial.begin(115200);
  delay(1000);
}

void loop() {
  // put your main code here, to run repeatedly:
  int signal=analogRead(AMP_PIN);
  Serial.println(signal);
  delay(5);
}
