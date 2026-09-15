#include <Audio.h>
#include "vader_dsp.h"

// Teensy 4.0, MSM261S4030H0, MAX98357A, coluna de 3 W / 8 ohm.
// Arduino IDE: Teensy 4.0, USB Type = Serial, CPU = 600 MHz, Optimize = Faster.
// Parâmetros de som no início de vader_dsp.h. Monitor série a 115200.
//
// BCLK 21 e LRCLK 20 partilhados pelo microfone e pelo amplificador.
// DOUT do microfone -> 8. DIN do amplificador -> 7. GND comum.
// O microfone usa 3,3 V. Os terminais da coluna ligam apenas a OUT+ e OUT-.
constexpr int CANAL_MIC = 0;  // L/R do microfone em GND. Usar 1 se estiver em 3,3 V.
constexpr int PINO_PRESET = 2; // Interruptor para GND. Fechado = criança.

// O script tools/import_breath.py cria este ficheiro a partir de uma gravação.
// Sem ele, o sintetizador produz o ar, as válvulas e as reflexões do tubo.
#if __has_include("breath_sample.h")
#include "breath_sample.h"
#define VADER_RECORDED_BREATH 1
#else
#define VADER_RECORDED_BREATH 0
#endif

static_assert(AUDIO_SAMPLE_RATE_EXACT == vader::SAMPLE_RATE, "Use 44100 Hz audio");

class AudioVader : public AudioStream {
 public:
  AudioVader() : AudioStream(1, queue_) {}
  vader::Processor processor;
  uint32_t missedBlocks = 0;

 private:
  audio_block_t* queue_[1];

  void update() override {
    audio_block_t* input = receiveReadOnly(0);
    audio_block_t* output = allocate();
    if (output) {
      for (unsigned i = 0; i < AUDIO_BLOCK_SAMPLES; ++i) {
        const float mic = input ? input->data[i] / 32768.0f : 0.0f;
        output->data[i] = static_cast<int16_t>(processor.tick(mic) * 32767.0f);
      }
      transmit(output);
      release(output);
    } else {
      ++missedBlocks;
    }
    if (input) release(input);
  }
};

AudioInputI2S mic;
AudioVader efeito;
AudioOutputI2S saida;
AudioConnection entrada(mic, CANAL_MIC, efeito, 0);
AudioConnection esquerda(efeito, 0, saida, 0);
AudioConnection direita(efeito, 0, saida, 1);

bool crianca = false, candidato = false;
bool led = false, tinhaSerial = false;
uint32_t candidatoDesde = 0, ultimoLed = 0, ultimoRelatorio = 0;

void ajuda() {
  Serial.println("Vader: a=tudo, v=voz, b=respiracao, c=calibrar/silencio, +/-=volume, ?=ajuda");
  Serial.println("c: fala normalmente e usa o RMS em Tuning.referenceRms, no vader_dsp.h.");
  Serial.println("Depois prime a. O volume e o modo voltam aos valores iniciais ao reiniciar.");
  Serial.println(VADER_RECORDED_BREATH ? "Respiracao gravada em flash." : "Respiracao sintetizada.");
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(PINO_PRESET, INPUT_PULLUP);
  crianca = candidato = digitalRead(PINO_PRESET) == LOW;
  AudioMemory(16);
  AudioNoInterrupts();
  efeito.processor.setChild(crianca);
#if VADER_RECORDED_BREATH
  efeito.processor.useBreathSample(VADER_BREATH_PCM, VADER_BREATH_SAMPLES);
#endif
  efeito.missedBlocks = 0;
  AudioInterrupts();
}

void loop() {
  const uint32_t now = millis();
  const bool pedido = digitalRead(PINO_PRESET) == LOW;
  if (pedido != candidato) { candidato = pedido; candidatoDesde = now; }
  if (candidato != crianca && now - candidatoDesde >= 50) {
    crianca = candidato;
    AudioNoInterrupts();
    efeito.processor.setChild(crianca);
    AudioInterrupts();
  }

  if (Serial && !tinhaSerial) ajuda();
  tinhaSerial = static_cast<bool>(Serial);
  while (Serial.available()) {
    const char key = Serial.read();
    AudioNoInterrupts();
    switch (key) {
      case 'a': efeito.processor.setMode(vader::Mode::Full); break;
      case 'v': efeito.processor.setMode(vader::Mode::Voice); break;
      case 'b': efeito.processor.setMode(vader::Mode::Breath); break;
      case 'c': efeito.processor.setMode(vader::Mode::Calibration); break;
      case '+': efeito.processor.setMaster(efeito.processor.master() + 0.05f); break;
      case '-': efeito.processor.setMaster(efeito.processor.master() - 0.05f); break;
    }
    AudioInterrupts();
    if (key == '?') ajuda();
  }

  if (Serial && now - ultimoRelatorio >= 500) {
    ultimoRelatorio = now;
    AudioNoInterrupts();
    const vader::Meters meter = efeito.processor.meters();
    const float volume = efeito.processor.master();
    const uint32_t misses = efeito.missedBlocks;
    efeito.processor.resetPeaks();
    AudioInterrupts();
    Serial.print(crianca ? "crianca " : "adulto ");
    Serial.print("RMS="); Serial.print(meter.inputRms, 4);
    Serial.print(" micPico="); Serial.print(meter.inputPeak, 3);
    Serial.print(" porta="); Serial.print(meter.gateOpen ? "aberta" : "fechada");
    Serial.print(" saida="); Serial.print(meter.outputPeak, 3);
    Serial.print(" limitador="); Serial.print(meter.limiterGain, 2);
    Serial.print(" volume="); Serial.print(volume, 2);
    Serial.print(" CPUmax="); Serial.print(AudioProcessorUsageMax(), 1);
    Serial.print(" memoria="); Serial.print(AudioMemoryUsageMax());
    Serial.print(" falhas="); Serial.println(misses);
  }

  if (now - ultimoLed >= (crianca ? 200u : 700u)) {
    ultimoLed = now;
    led = !led;
    digitalWrite(LED_BUILTIN, led);
  }
}
