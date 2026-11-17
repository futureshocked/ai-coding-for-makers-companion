/**
 * @file serial_port_sim.ino
 * @brief Simulated sensor output for Arduino Uno R4 Minima.
 *
 * Generates synthetic readings for three sensors and outputs them as CSV
 * over USB serial at 9600 baud, one line per second. Designed for testing
 * the Arduino Sensor Visualiser web application without physical sensors.
 *
 * Output format (CSV, positional schema):
 *   timestamp_ms,temperature_c,humidity_pct,lux
 *
 * Example:
 *   4823,23.4,65.1,412
 *
 * Sensor simulation models:
 *   - Temperature: random walk ±0.3°C per step, bounded 18-30°C
 *   - Humidity: inverse correlation to temperature + noise, bounded 40-80%
 *   - Lux: sine-wave approximation (period ~120 samples) + random spikes,
 *          bounded 0-2000
 *
 * Hardware: Arduino Uno R4 Minima (or any Arduino with USB serial support).
 * Baud rate: 9600
 * Sample rate: 1 Hz (1 second between readings)
 *
 * @note Column order IS the schema. Reordering columns will cause parsing
 *       failures on the server side. Do not change column order without
 *       updating the server parser accordingly.
 */

// State variables
unsigned long callCount = 0;
float temperature = 23.0;

void setup() {
  Serial.begin(9600);
  // Wait for serial port to establish (native USB boards)
  while (!Serial) {
    ;
  }
  pinMode(LED_BUILTIN, OUTPUT);
  // Send CSV header
  Serial.println("timestamp_ms,temperature_c,humidity_pct,lux");
}

void loop() {
  unsigned long ts_ms = millis();

  // Temperature: random walk +/- 0.3C per step, bounded 18-30C
  float delta = (random(0, 1000) / 1000.0 - 0.5) * 0.6; // -0.3 to +0.3
  temperature = constrain(temperature + delta, 18.0, 30.0);

  // Humidity: inverse correlation to temperature, range 40-80%
  float baseHum = 60.0 - (temperature - 23.0) * 5.0;
  float humNoise = (random(0, 1000) / 1000.0 - 0.5) * 6.0; // -3 to +3
  float humidity = constrain(baseHum + humNoise, 40.0, 80.0);

  // Lux: sine-wave approximation + random component
  // Use a slow counter for sine approximation (period ~120 samples)
  float phase = (float)(callCount % 120) / 120.0 * 2.0 * 3.14159;
  float sineVal = sin(phase);
  float sineBase = 800.0 + 600.0 * sineVal;
  float spike = (random(0, 100) < 10) ? random(0, 400) : 0;
  float noise = (random(0, 1000) / 1000.0 - 0.5) * 200.0;
  float luxVal = constrain(sineBase + spike + noise, 0.0, 2000.0);

  // Output CSV line
  Serial.print(ts_ms);
  Serial.print(",");
  Serial.print(temperature, 1);
  Serial.print(",");
  Serial.print(humidity, 1);
  Serial.print(",");
  Serial.println((int)round(luxVal));

  // Flash LED on each reading
  digitalWrite(LED_BUILTIN, HIGH);
  delay(50);
  digitalWrite(LED_BUILTIN, LOW);

  callCount++;
  delay(1000); // 1Hz
}
