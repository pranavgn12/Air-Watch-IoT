#include <WiFi.h>
#include <HTTPClient.h>
#include "DHT.h"

// -------------------- DHT setup --------------------
#define DHTPIN 4
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

// -------------------- MQ-135 analog pin --------------------
#define MQ135_PIN 34

// -------------------- GP2Y1010AU0F Dust Sensor pins --------------------
#define DUST_MEASURE_PIN 35
#define DUST_LED_PIN 32

// -------------------- Buzzer pin --------------------
// Use an output-capable GPIO like 27
#define BUZZER_PIN 27

// -------------------- WiFi credentials --------------------
const char* ssid = "Redmi Note 12 5G";
const char* password = "12345678";

// -------------------- Server IP --------------------
const char* server = "http://10.28.229.167:5000/update";

// -------------------- Thresholds from your dashboard image --------------------
const float TEMP_MAX_DISPLAY = 50;
const float HUM_MAX_DISPLAY   = 80;
const float DUST_MAX_DISPLAY  = 300;
const float AIRQ_MAX_DISPLAY  = 150;

const float TEMP_LIMIT = TEMP_MAX_DISPLAY * 0.80;   // 27.28
const float HUM_LIMIT   = HUM_MAX_DISPLAY * 0.80;    // 25.52
const float DUST_LIMIT  = DUST_MAX_DISPLAY * 0.80;   // 0.88
const float AIRQ_LIMIT  = AIRQ_MAX_DISPLAY * 0.80;   // 66.4

void beepBuzzer(int durationMs) {
  digitalWrite(BUZZER_PIN, HIGH);
  delay(durationMs);
  digitalWrite(BUZZER_PIN, LOW);
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\nBooting...");

  // Initialize sensors
  dht.begin();
  pinMode(MQ135_PIN, INPUT);

  // Dust sensor LED pin
  pinMode(DUST_LED_PIN, OUTPUT);
  digitalWrite(DUST_LED_PIN, HIGH); // LED OFF (active LOW)

  // Buzzer pin
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // Connect WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
    attempts++;
    if (attempts > 20) {
      Serial.println("\n❌ WiFi FAILED");
      return;
    }
  }

  Serial.println("\n✅ WiFi Connected!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  Serial.println("\nReading sensors...");

  // 1. Read DHT22 & MQ135
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();
  int mqValue = analogRead(MQ135_PIN);

  // Check DHT sensor error
  if (isnan(temp) || isnan(hum)) {
    Serial.println("❌ DHT read failed!");
    digitalWrite(BUZZER_PIN, LOW);
    delay(2000);
    return;
  }

  // 2. Read GP2Y1010AU0F Dust Sensor
  digitalWrite(DUST_LED_PIN, LOW);   // Power on LED
  delayMicroseconds(280);            // Wait 280us
  int voMeasured = analogRead(DUST_MEASURE_PIN);
  delayMicroseconds(40);             // Wait 40us
  digitalWrite(DUST_LED_PIN, HIGH);  // Turn LED off
  delayMicroseconds(9680);           // Rest of 10ms cycle

  // Convert analog reading (0-4095) to voltage (0-3.3V)
  float calcVoltage = voMeasured * (3.3 / 4095.0);

  // Convert voltage to dust density
  float dustDensity = (170.0 * calcVoltage) - 100.0;
  if (dustDensity < 0) {
    dustDensity = 0.0;
  }

  // 3. Decide whether alarm should sound
  // AirQ is your raw MQ135 score shown on dashboard, so 80% of 83 = 66.4
  bool alarm = false;

  if (temp >= TEMP_LIMIT) alarm = true;
  if (hum >= HUM_LIMIT) alarm = true;
  if (dustDensity >= DUST_LIMIT) alarm = true;
  if (mqValue >= AIRQ_LIMIT) alarm = true;

  // 4. Buzzer beep if any value crosses threshold
  if (alarm) {
    Serial.println("⚠️ ALARM: One or more values crossed 80% threshold!");
    beepBuzzer(120);  // short beep
  } else {
    digitalWrite(BUZZER_PIN, LOW);
  }

  // 5. Print values to Serial
  Serial.print("Temp: ");
  Serial.print(temp);
  Serial.print(" °C  | Humidity: ");
  Serial.print(hum);
  Serial.print(" %  | MQ135: ");
  Serial.print(mqValue);
  Serial.print("  | Dust: ");
  Serial.print(dustDensity);
  Serial.println(" µg/m³");

  Serial.print("Thresholds -> Temp: ");
  Serial.print(TEMP_LIMIT);
  Serial.print("  Hum: ");
  Serial.print(HUM_LIMIT);
  Serial.print("  Dust: ");
  Serial.print(DUST_LIMIT);
  Serial.print("  AirQ: ");
  Serial.println(AIRQ_LIMIT);

  // 6. Send data to server
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;

    String url = String(server) +
                 "?temp=" + String(temp, 2) +
                 "&hum=" + String(hum, 2) +
                 "&mq135=" + String(mqValue) +
                 "&dust=" + String(dustDensity, 2);

    Serial.println("📡 Sending:");
    Serial.println(url);

    http.begin(url);
    int response = http.GET();

    Serial.print("📨 Server Response: ");
    Serial.println(response);

    http.end();
  } else {
    Serial.println("❌ WiFi disconnected!");
  }

  delay(500);
}