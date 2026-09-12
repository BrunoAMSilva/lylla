#include <Audio.h>

// ---------- a voz ----------
const int   CANAL_MIC   = 0;
const float GANHO_MIC   = 2.0;
const float GRAVIDADE   = 0.78;   // 0,70 a 0,85. Abaixo de 0,70 desfaz-se
const float GRAO_MS     = 20;     // 12 a 25. O 40 é que fazia o arrastamento
const float SPLIT_HZ    = 1400;   // abaixo disto baixa de tom, acima passa intacto
const float AGUDOS      = 0.4;    // quanto dos agudos originais volta à mistura
const float CORTE_GRAVE = 120;
const float CORTE_AGUDO = 4000;   // aberto, para as consoantes respirarem
const float DUREZA      = 1.2;    // baixo: o granular já degrada que chegue

// ---------- a porta ----------
const float LIMIAR_ABRE  = 0.05;
const float LIMIAR_FECHA = 0.03;
const int   ESPERA_MS    = 800;
const int   MINIMO_MS    = 350;
const float VOLUME       = 0.7;

// ---------- a respiração ----------
const float    VOL_RESPIRA      = 0.35;
const float    VOL_RESPIRA_FALA = 0.10;
const uint32_t CICLO_MS         = 4800;
const uint32_t EXPIRA_EM_MS     = 2100;

// ---------- a cadeia ----------
AudioInputI2S          micIn;
AudioAnalyzeRMS        nivel;
AudioAmplifier         preAmp;

AudioFilterBiquad      soGraves;
AudioEffectGranular    grave;
AudioFilterBiquad      soAgudos;
AudioMixer4            misturaVoz;

AudioFilterBiquad      banda;
AudioEffectWaveshaper  saturacao;
AudioAmplifier         porta;

AudioSynthNoiseWhite   ruidoInsp;
AudioSynthNoisePink    ruidoExp;
AudioFilterBiquad      filtroInsp;
AudioFilterBiquad      filtroExp;
AudioEffectEnvelope    envInsp;
AudioEffectEnvelope    envExp;

AudioMixer4            misturaFinal;
AudioOutputI2S         saida;

AudioConnection c1(micIn, CANAL_MIC, nivel, 0);
AudioConnection c2(micIn, CANAL_MIC, preAmp, 0);

AudioConnection c3(preAmp, 0, soGraves, 0);
AudioConnection c4(soGraves, 0, grave, 0);
AudioConnection c5(grave, 0, misturaVoz, 0);

AudioConnection c6(preAmp, 0, soAgudos, 0);
AudioConnection c7(soAgudos, 0, misturaVoz, 1);

AudioConnection c8(misturaVoz, 0, banda, 0);
AudioConnection c9(banda, 0, saturacao, 0);
AudioConnection c10(saturacao, 0, porta, 0);
AudioConnection c11(porta, 0, misturaFinal, 0);

AudioConnection c12(ruidoInsp, 0, filtroInsp, 0);
AudioConnection c13(filtroInsp, 0, envInsp, 0);
AudioConnection c14(envInsp, 0, misturaFinal, 2);

AudioConnection c15(ruidoExp, 0, filtroExp, 0);
AudioConnection c16(filtroExp, 0, envExp, 0);
AudioConnection c17(envExp, 0, misturaFinal, 3);

AudioConnection c18(misturaFinal, 0, saida, 0);
AudioConnection c19(misturaFinal, 0, saida, 1);

#define MEM_GRAOS 12800
int16_t memoriaGraos[MEM_GRAOS];

float    curva[65];
bool     aberto = false;
uint32_t ultimaVoz = 0, abriuEm = 0, ultimoPisca = 0;
bool     aceso = false;

uint32_t cicloComecou = 0;
bool     inspirou = false, expirou = false;

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  AudioMemory(80);

  grave.begin(memoriaGraos, MEM_GRAOS);
  grave.beginPitchShift(GRAO_MS);
  grave.setSpeed(GRAVIDADE);

  // o corte em dois: só o corpo da voz é que desce
  soGraves.setLowpass (0, SPLIT_HZ, 0.707);
  soGraves.setLowpass (1, SPLIT_HZ, 0.707);
  soAgudos.setHighpass(0, SPLIT_HZ, 0.707);
  soAgudos.setHighpass(1, SPLIT_HZ, 0.707);

  misturaVoz.gain(0, 1.0);        // graves baixados de tom
  misturaVoz.gain(1, AGUDOS);     // consoantes originais

  for (int i = 0; i < 65; i++) {
    float x = (i - 32) / 32.0f;
    curva[i] = tanhf(x * DUREZA) / tanhf(DUREZA);
  }
  saturacao.shape(curva, 65);

  banda.setHighpass(0, CORTE_GRAVE, 0.707);
  banda.setLowpass (1, CORTE_AGUDO, 0.707);

  preAmp.gain(GANHO_MIC);
  porta.gain(0.0);

  // inspiração: áspera e mais aguda, com ressonância de tubo (Q alto)
  ruidoInsp.amplitude(0.9);
  filtroInsp.setBandpass(0, 1500, 3.0);
  filtroInsp.setBandpass(1, 2600, 2.5);

  // expiração: ruído rosa, mais escura e mais encorpada
  ruidoExp.amplitude(0.9);
  filtroExp.setBandpass(0, 600, 2.5);
  filtroExp.setBandpass(1, 1100, 2.0);

  envInsp.attack(300);  envInsp.hold(450);  envInsp.decay(600);
  envInsp.sustain(0.0); envInsp.release(150);

  envExp.attack(350);   envExp.hold(800);   envExp.decay(1000);
  envExp.sustain(0.0);  envExp.release(250);

  misturaFinal.gain(0, VOLUME);
  misturaFinal.gain(1, 0.0);
  misturaFinal.gain(2, VOL_RESPIRA);
  misturaFinal.gain(3, VOL_RESPIRA);

  cicloComecou = millis();
}

void loop() {
  if (nivel.available()) {
    float p = nivel.read();

    if (!aberto && p > LIMIAR_ABRE) {
      aberto = true;
      abriuEm = millis();
      ultimaVoz = millis();
      porta.gain(1.0);
      misturaFinal.gain(2, VOL_RESPIRA_FALA);
      misturaFinal.gain(3, VOL_RESPIRA_FALA);
    }
    if (aberto && p > LIMIAR_FECHA) ultimaVoz = millis();
  }

  if (aberto
      && millis() - abriuEm   > (uint32_t)MINIMO_MS
      && millis() - ultimaVoz > (uint32_t)ESPERA_MS) {
    aberto = false;
    porta.gain(0.0);
    misturaFinal.gain(2, VOL_RESPIRA);
    misturaFinal.gain(3, VOL_RESPIRA);
  }

  uint32_t t = millis() - cicloComecou;
  if (!inspirou)                     { envInsp.noteOn(); inspirou = true; }
  if (!expirou && t >= EXPIRA_EM_MS) { envExp.noteOn();  expirou  = true; }
  if (t >= CICLO_MS) { cicloComecou = millis(); inspirou = false; expirou = false; }

  if (millis() - ultimoPisca > 500) {
    ultimoPisca = millis();
    aceso = !aceso;
    digitalWrite(LED_BUILTIN, aceso);
  }
}