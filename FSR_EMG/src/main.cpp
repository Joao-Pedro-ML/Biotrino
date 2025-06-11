#include <Arduino.h>

#define EMG1_PIN 34
#define EMG2_PIN 35
#define FSR1_PIN 32
#define FSR2_PIN 33

hw_timer_t* timer = NULL;
portMUX_TYPE timerMux = portMUX_INITIALIZER_UNLOCKED;

volatile bool sampleReady = false;

void IRAM_ATTR onTimer() {
  portENTER_CRITICAL_ISR(&timerMux);
  sampleReady = true;
  portEXIT_CRITICAL_ISR(&timerMux);
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12); // 0–4095


  timer = timerBegin(0, 80, true);
  timerAttachInterrupt(timer, &onTimer, true);
  timerAlarmWrite(timer, 1000, true);  // 1000 us = 1 ms = 1 kHz
  timerAlarmEnable(timer);
}

//volatile unsigned long sampleCount = 0;

void loop() {
  if (sampleReady) {
    portENTER_CRITICAL(&timerMux);
    sampleReady = false;
    portEXIT_CRITICAL(&timerMux);

    int emg1 = analogRead(EMG1_PIN);
    int emg2 = analogRead(EMG2_PIN);
    int fsr1 = analogRead(FSR1_PIN);
    int fsr2 = analogRead(FSR2_PIN);
    //unsigned long timestamp = millis();

    //Serial.printf("%lu,%d,%d,%d,%d\n", timestamp, emg1, emg2, fsr1, fsr2);
    Serial.printf("%d,%d,%d,%d\n", emg1, emg2, fsr1, fsr2);
    //sampleCount++;
  }
}
