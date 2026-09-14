#include <Arduino.h>
#include <esp_timer.h>

#define EMG1_PIN 34
#define EMG2_PIN 35
#define FSR1_PIN 32
#define FSR2_PIN 33

hw_timer_t* timer = NULL;
portMUX_TYPE timerMux = portMUX_INITIALIZER_UNLOCKED;

volatile bool sampleReady = false;
volatile uint32_t sampleNumber = 0;

void IRAM_ATTR onTimer() {
  portENTER_CRITICAL_ISR(&timerMux);
  sampleNumber++;
  sampleReady = true;
  portEXIT_CRITICAL_ISR(&timerMux);
}

void setup() {
  Serial.begin(921600);
  analogReadResolution(12); // 0–4095


#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  // Arduino-ESP32 3.x: timerBegin recebe a frequencia do contador.
  timer = timerBegin(1000000);  // 1 MHz: cada tick corresponde a 1 us
  timerAttachInterrupt(timer, &onTimer);
  timerAlarm(timer, 1000, true, 0);  // 1000 us = 1 ms = 1 kHz
#else
  // Arduino-ESP32 2.x e anteriores.
  timer = timerBegin(0, 80, true);
  timerAttachInterrupt(timer, &onTimer, true);
  timerAlarmWrite(timer, 1000, true);  // 1000 us = 1 ms = 1 kHz
  timerAlarmEnable(timer);
#endif

  // Identifica a placa e informa: versao do protocolo, taxa e canais.
  Serial.println("#BIOTRINO,1,1000,4");
}

//volatile unsigned long sampleCount = 0;

void loop() {
  if (sampleReady) {
    uint32_t currentSampleNumber;

    portENTER_CRITICAL(&timerMux);
    currentSampleNumber = sampleNumber;
    sampleReady = false;
    portEXIT_CRITICAL(&timerMux);

    int emg1 = analogRead(EMG1_PIN);
    int emg2 = analogRead(EMG2_PIN);
    int fsr1 = analogRead(FSR1_PIN);
    int fsr2 = analogRead(FSR2_PIN);
    uint64_t timestampUs = esp_timer_get_time();

    // O numero da amostra permite detectar ciclos perdidos na interface.
    Serial.printf("%lu,%llu,%d,%d,%d,%d\n",
                  static_cast<unsigned long>(currentSampleNumber),
                  static_cast<unsigned long long>(timestampUs),
                  emg1, emg2, fsr1, fsr2);
  }
}
