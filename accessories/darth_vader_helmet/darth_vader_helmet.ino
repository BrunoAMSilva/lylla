#include <Audio.h>

// Teensy 4.0, microfone I2S MSM261S4030H0, amplificador MAX98357A, coluna 3 W 8 ohm.
//
// A identidade do Vader está mais na equalização e na respiração do que na
// descida de tom. O granular do Teensy descarta (1 - velocidade) do sinal, por
// isso descer muito estraga sempre a voz.
//
// PRIMEIRO DE TUDO: põe CALIBRAR a true, grava, abre o monitor série e fala
// como vais falar com o capacete posto. Ele imprime o nível do microfone. Mete
// esse número em NIVEL_FALA, põe CALIBRAR a false e grava outra vez. O
// MSM261S4030H0 dá um sinal fraco e todos os limiares dependem deste valor.
const bool  CALIBRAR   = false;
const float NIVEL_FALA = 0.020;   // RMS do microfone a falar normalmente

// ---------- quem veste ----------
const int PINO_PRESET = 2;        // interruptor para GND. Fechado = criança.

struct Preset {
  float velocidade;               // 0,60 = -8,8 semitons. 0,76 = -4,8 semitons
  float graoMs;                   // abaixo de 38 ms o granular zumbe
  uint16_t piscaMs;               // o LED diz qual dos dois está a correr
};
const Preset CRIANCA = { 0.60f, 42.0f, 200 };
const Preset ADULTO  = { 0.76f, 45.0f, 700 };

// ---------- a voz ----------
const int   CANAL_MIC    = 0;     // se não ouvires nada, o L/R do micro está do outro lado: põe 1
const float CORTE_RUMOR  = 110;   // antes do granular, senão o detetor de
                                  // passagem por zero engasga-se com o offset
const float CORTE_GRAVE  = 170;
const float CORTE_AGUDO  = 2800;  // sibilância apagada. É a marca do capacete.
const float DUREZA       = 3.2;
const float ASSIMETRIA   = 1.35;  // meias-ondas com ganhos diferentes, dá harmónicas pares

// as ressonâncias do capacete. É daqui que vem quase tudo.
const float FORM1_HZ = 520,  FORM1_DB =  12.0, FORM1_Q = 1.2;
const float FORM2_HZ = 1100, FORM2_DB =   9.0, FORM2_Q = 2.6;
const float FORM3_HZ = 2500, FORM3_DB = -10.0, FORM3_Q = 1.4;

// a cauda curta de quem fala dentro de uma caixa
const float ECO1_MS = 11, ECO1_VOL = 0.14;
const float ECO2_MS = 19, ECO2_VOL = 0.08;

// ---------- o compressor ----------
// tudo em unidades de NIVEL_FALA: 1,0 é falar normalmente
const float ALVO_CADEIA = 0.055;  // o corpo soma +12,2 dB, isto deixa margem
const float LIMIAR_COMP = 0.50;
const float RACIO       = 4.0;
const float ATAQUE_MS   = 10;
const float RELAXE_MS   = 300;

// ---------- a porta ----------
const float LIMIAR_ABRE  = 0.30;
const float LIMIAR_FECHA = 0.15;
const int   ESPERA_MS    = 800;
const int   MINIMO_MS    = 350;
const float SUBIDA_MS    = 15;    // com salto seco ouvia-se um clique
const float DESCIDA_MS   = 150;
const float VOLUME       = 0.7;

// ---------- a respiração ----------
// Os envelopes são feitos no loop() e não com AudioEffectEnvelope: as rampas
// lineares do envelope deixavam um canto audível no topo de cada sopro, e o
// varrimento do filtro que lá estava soava a rajada de vento em vez de ar a
// passar por uma máscara. Agora os formantes são fixos, só o brilho é que
// acompanha o caudal, e uma turbulência lenta parte o sopro para não ficar liso.
const uint32_t CICLO_MS     = 4000;
const uint32_t EXPIRA_EM_MS = 2050;
const float    VOL_INSPIRA  = 1.50;
const float    VOL_EXPIRA   = 1.00;
const float    DUCK_FALA    = 0.22;   // quanto fica enquanto se fala
const float    DUCK_MS      = 120;

const uint32_t INSP_DUR_MS = 1250;
const float    INSP_SUBIDA = 0.18, INSP_DESCIDA = 0.45;
const float    INSP_A_HZ = 300,  INSP_A_Q = 4.0, INSP_A_G = 2.6;
const float    INSP_B_HZ = 750,  INSP_B_Q = 3.0, INSP_B_G = 1.8;
const float    INSP_C_HZ = 1700, INSP_C_Q = 2.0, INSP_C_G = 1.2;
const float    INSP_TAMPA_HZ = 2600, INSP_CORTE_HZ = 130;

const uint32_t EXP_DUR_MS = 1150;
const float    EXP_SUBIDA = 0.16, EXP_DESCIDA = 0.50;
const float    EXP_A_HZ = 220, EXP_A_Q = 3.0, EXP_A_G = 1.1;
const float    EXP_B_HZ = 520, EXP_B_Q = 2.4, EXP_B_G = 0.8;
const float    EXP_TAMPA_HZ = 1500;

const float TURB_HZ   = 12;       // ar turbulento, não um sopro liso
const float TURB_INSP = 0.22;
const float TURB_EXP  = 0.18;

// ---------- a cadeia ----------
AudioInputI2S            micIn;
AudioAnalyzeRMS          nivel;

AudioFilterBiquad        entrada;
AudioAmplifier           nivelador;
AudioEffectGranular      grave;
AudioAmplifier           porta;
AudioFilterBiquad        corpo;
AudioEffectWaveshaper    saturacao;
AudioFilterBiquad        boca;
AudioEffectDelay         capacete;
AudioMixer4              misturaVoz;

AudioSynthNoiseWhite     ruidoInsp;
AudioFilterBiquad        formInspA;
AudioFilterBiquad        formInspB;
AudioFilterBiquad        formInspC;
AudioMixer4              misturaInsp;
AudioFilterBiquad        tampaInsp;

AudioSynthNoisePink      ruidoExp;
AudioFilterBiquad        formExpA;
AudioFilterBiquad        formExpB;
AudioMixer4              misturaExp;
AudioFilterBiquad        tampaExp;

AudioMixer4              misturaFinal;
AudioOutputI2S           saida;

AudioConnection c1 (micIn, CANAL_MIC, nivel, 0);
AudioConnection c2 (micIn, CANAL_MIC, entrada, 0);
AudioConnection c3 (entrada, 0, nivelador, 0);
AudioConnection c4 (nivelador, 0, grave, 0);
AudioConnection c5 (grave, 0, porta, 0);
AudioConnection c6 (porta, 0, corpo, 0);
AudioConnection c7 (corpo, 0, saturacao, 0);
AudioConnection c8 (saturacao, 0, boca, 0);
AudioConnection c9 (boca, 0, misturaVoz, 0);
AudioConnection c10(boca, 0, capacete, 0);
AudioConnection c11(capacete, 0, misturaVoz, 1);
AudioConnection c12(capacete, 1, misturaVoz, 2);
AudioConnection c13(misturaVoz, 0, misturaFinal, 0);

AudioConnection c14(ruidoInsp, 0, formInspA, 0);
AudioConnection c15(ruidoInsp, 0, formInspB, 0);
AudioConnection c16(ruidoInsp, 0, formInspC, 0);
AudioConnection c17(formInspA, 0, misturaInsp, 0);
AudioConnection c18(formInspB, 0, misturaInsp, 1);
AudioConnection c19(formInspC, 0, misturaInsp, 2);
AudioConnection c20(misturaInsp, 0, tampaInsp, 0);
AudioConnection c21(tampaInsp, 0, misturaFinal, 2);

AudioConnection c22(ruidoExp, 0, formExpA, 0);
AudioConnection c23(ruidoExp, 0, formExpB, 0);
AudioConnection c24(formExpA, 0, misturaExp, 0);
AudioConnection c25(formExpB, 0, misturaExp, 1);
AudioConnection c26(misturaExp, 0, tampaExp, 0);
AudioConnection c27(tampaExp, 0, misturaFinal, 3);

AudioConnection c28(misturaFinal, 0, saida, 0);
AudioConnection c29(misturaFinal, 0, saida, 1);

#define MEM_GRAOS 12800
int16_t memoriaGraos[MEM_GRAOS];

#define PONTOS_CURVA 257
float curva[PONTOS_CURVA];

const float BLOCO_MS = 1000.0f * AUDIO_BLOCK_SAMPLES / AUDIO_SAMPLE_RATE_EXACT;

Preset preset = ADULTO;
bool     presetCrianca = false;
uint32_t mudouPresetEm = 0;

float coefAtaque, coefRelaxe, coefSubida, coefDescida, coefDuck, coefTurb;
float ganhoComp = 1.0f, ganhoPorta = 0.0f, fatorRespira = 1.0f;
float turbInsp = 0.0f, turbExp = 0.0f;

bool     aberto = false;
uint32_t ultimaVoz = 0, abriuEm = 0, ultimoPisca = 0;
bool     aceso = false;

uint32_t cicloComecou = 0;
float    picoCalibra = 0.0f;
uint32_t imprimiuEm = 0;

// o biquad do Teensy não traz sino paramétrico, e é dele que vem o capacete
void sino(AudioFilterBiquad &f, uint32_t andar, float freq, float db, float q) {
  double a     = pow(10.0, db / 40.0);
  double w0    = freq * (2.0 * 3.141592654 / AUDIO_SAMPLE_RATE_EXACT);
  double alpha = sin(w0) / (2.0 * q);
  double cosW0 = cos(w0);
  double a0    = 1.0 + alpha / a;
  double coef[5] = {
    (1.0 + alpha * a) / a0,
    (-2.0 * cosW0)    / a0,
    (1.0 - alpha * a) / a0,
    (-2.0 * cosW0)    / a0,
    (1.0 - alpha / a) / a0
  };
  f.setCoefficients(andar, coef);
}

// arranca e pára sem canto nenhum, que era o que dava o soluço
float suave(float fase, float subida, float descida) {
  if (fase <= 0.0f || fase >= 1.0f) return 0.0f;
  if (fase < subida)         { float x = fase / subida;       return x * x * (3.0f - 2.0f * x); }
  if (fase > 1.0f - descida) { float x = (1.0f - fase) / descida; return x * x * (3.0f - 2.0f * x); }
  return 1.0f;
}

float porBloco(float ms) { return 1.0f - expf(-BLOCO_MS / ms); }
float aleatorio()        { return random(-1000, 1001) / 1000.0f; }

void aplicaPreset(const Preset &p) {
  grave.beginPitchShift(p.graoMs);
  grave.setSpeed(p.velocidade);
}

void setup() {
  if (CALIBRAR) Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(PINO_PRESET, INPUT_PULLUP);
  AudioMemory(120);

  presetCrianca = (digitalRead(PINO_PRESET) == LOW);
  preset = presetCrianca ? CRIANCA : ADULTO;

  grave.begin(memoriaGraos, MEM_GRAOS);
  aplicaPreset(preset);

  entrada.setHighpass(0, CORTE_RUMOR, 0.707);
  entrada.setHighpass(1, CORTE_RUMOR, 0.707);

  corpo.setHighpass(0, CORTE_GRAVE, 0.707);
  sino(corpo, 1, FORM1_HZ, FORM1_DB, FORM1_Q);
  sino(corpo, 2, FORM2_HZ, FORM2_DB, FORM2_Q);
  sino(corpo, 3, FORM3_HZ, FORM3_DB, FORM3_Q);

  for (int i = 0; i < PONTOS_CURVA; i++) {
    float x = (i - (PONTOS_CURVA - 1) / 2.0f) / ((PONTOS_CURVA - 1) / 2.0f);
    float d = (x >= 0) ? DUREZA : DUREZA * ASSIMETRIA;
    curva[i] = tanhf(x * d) / tanhf(d);
  }
  saturacao.shape(curva, PONTOS_CURVA);

  boca.setHighpass(0, CORTE_GRAVE, 0.707);   // apanha o offset que a assimetria cria
  boca.setLowpass (1, CORTE_AGUDO, 0.707);
  boca.setLowpass (2, CORTE_AGUDO, 0.707);

  capacete.delay(0, ECO1_MS);
  capacete.delay(1, ECO2_MS);
  misturaVoz.gain(0, 1.0);
  misturaVoz.gain(1, ECO1_VOL);
  misturaVoz.gain(2, ECO2_VOL);
  misturaVoz.gain(3, 0.0);

  porta.gain(0.0);
  nivelador.gain(ALVO_CADEIA / NIVEL_FALA);

  // inspiração: três formantes fixos, do grave ao áspero
  ruidoInsp.amplitude(0.45);
  formInspA.setBandpass(0, INSP_A_HZ, INSP_A_Q);
  formInspB.setBandpass(0, INSP_B_HZ, INSP_B_Q);
  formInspC.setBandpass(0, INSP_C_HZ, INSP_C_Q);
  tampaInsp.setHighpass(0, INSP_CORTE_HZ, 0.707);
  tampaInsp.setLowpass (1, INSP_TAMPA_HZ, 0.707);
  tampaInsp.setLowpass (2, INSP_TAMPA_HZ, 0.707);

  // expiração: rosa, mais escura e mais curta que a inspiração
  ruidoExp.amplitude(0.9);
  formExpA.setBandpass(0, EXP_A_HZ, EXP_A_Q);
  formExpB.setBandpass(0, EXP_B_HZ, EXP_B_Q);
  tampaExp.setLowpass(0, EXP_TAMPA_HZ, 0.707);

  misturaFinal.gain(0, VOLUME);
  misturaFinal.gain(1, 0.0);
  misturaFinal.gain(2, VOL_INSPIRA);
  misturaFinal.gain(3, VOL_EXPIRA);

  coefAtaque  = porBloco(ATAQUE_MS);
  coefRelaxe  = porBloco(RELAXE_MS);
  coefSubida  = porBloco(SUBIDA_MS);
  coefDescida = porBloco(DESCIDA_MS);
  coefDuck    = porBloco(DUCK_MS);
  coefTurb    = 1.0f - expf(-BLOCO_MS * 0.001f * 2.0f * 3.141592654f * TURB_HZ);

  cicloComecou = millis();
}

void loop() {
  bool querCrianca = (digitalRead(PINO_PRESET) == LOW);
  if (querCrianca != presetCrianca) {
    if (mudouPresetEm == 0) mudouPresetEm = millis();
    if (millis() - mudouPresetEm > 50) {
      presetCrianca = querCrianca;
      preset = presetCrianca ? CRIANCA : ADULTO;
      aplicaPreset(preset);
      mudouPresetEm = 0;
    }
  } else {
    mudouPresetEm = 0;
  }

  uint32_t t = millis() - cicloComecou;

  if (nivel.available()) {
    float rms = nivel.read();
    float p = rms / NIVEL_FALA;        // 1,0 = falar normalmente

    if (CALIBRAR) {
      if (rms > picoCalibra) picoCalibra = rms;
      if (millis() - imprimiuEm > 250) {
        imprimiuEm = millis();
        Serial.print("nivel do micro: ");
        Serial.println(picoCalibra, 4);
        picoCalibra = 0.0f;
      }
    }

    if (!aberto && p > LIMIAR_ABRE) {
      aberto = true;
      abriuEm = millis();
      ultimaVoz = millis();
    }
    if (aberto && p > LIMIAR_FECHA) ultimaVoz = millis();

    if (aberto
        && millis() - abriuEm   > (uint32_t)MINIMO_MS
        && millis() - ultimaVoz > (uint32_t)ESPERA_MS) {
      aberto = false;
    }

    float alvoComp = ALVO_CADEIA / NIVEL_FALA;
    if (p > LIMIAR_COMP) alvoComp *= powf(LIMIAR_COMP / p, 1.0f - 1.0f / RACIO);
    ganhoComp += (alvoComp - ganhoComp) * ((alvoComp < ganhoComp) ? coefAtaque : coefRelaxe);
    nivelador.gain(ganhoComp);

    ganhoPorta += ((aberto ? 1.0f : 0.0f) - ganhoPorta)
                * (aberto ? coefSubida : coefDescida);
    porta.gain(ganhoPorta);

    // a respiração é ruído, um salto de ganho ouve-se como um estalo
    fatorRespira += ((aberto ? DUCK_FALA : 1.0f) - fatorRespira) * coefDuck;
    misturaFinal.gain(2, VOL_INSPIRA * fatorRespira);
    misturaFinal.gain(3, VOL_EXPIRA  * fatorRespira);

    // inspiração: o brilho segue o caudal, os formantes não se mexem
    turbInsp += (aleatorio() - turbInsp) * coefTurb;
    float envI = suave((float)t / INSP_DUR_MS, INSP_SUBIDA, INSP_DESCIDA);
    float briI = envI;
    float gI = envI * (1.0f + TURB_INSP * turbInsp * 3.0f);
    if (gI < 0.0f) gI = 0.0f;
    misturaInsp.gain(0, INSP_A_G * gI);
    misturaInsp.gain(1, INSP_B_G * gI * briI);
    misturaInsp.gain(2, INSP_C_G * gI * briI * briI);

    turbExp += (aleatorio() - turbExp) * coefTurb;
    float faseE = (t >= EXPIRA_EM_MS) ? (float)(t - EXPIRA_EM_MS) / EXP_DUR_MS : 0.0f;
    float envE = suave(faseE, EXP_SUBIDA, EXP_DESCIDA);
    float gE = envE * (1.0f + TURB_EXP * turbExp * 3.0f);
    if (gE < 0.0f) gE = 0.0f;
    misturaExp.gain(0, EXP_A_G * gE);
    misturaExp.gain(1, EXP_B_G * gE * envE);
  }

  if (t >= CICLO_MS) cicloComecou = millis();

  if (millis() - ultimoPisca > preset.piscaMs) {
    ultimoPisca = millis();
    aceso = !aceso;
    digitalWrite(LED_BUILTIN, aceso);
  }
}
