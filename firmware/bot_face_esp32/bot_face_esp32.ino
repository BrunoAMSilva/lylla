// ===========================================================================
//  A CARA DO ROBÔ — ESP32 + painel HUB75 64×32 RGB
// ===========================================================================
//
//  Esta placa faz UMA coisa só: desenhar a cara. Recebe o nome de uma
//  expressão pelo cabo USB e trata do resto — a transição suave, o piscar,
//  a respiração, o coração a bater.
//
//  O Raspberry Pi manda 40 bytes e esquece o assunto. Toda a animação
//  acontece aqui, a 60 imagens por segundo, sem roubar nada ao Whisper.
//
//  ---------------------------------------------------------------------
//  COMO INSTALAR
//  ---------------------------------------------------------------------
//  1. Arduino IDE → Gestor de Placas → instalar "esp32" (Espressif)
//  2. Gestor de Bibliotecas → instalar "ESP32 HUB75 LED MATRIX PANEL DMA"
//     (mrcodetastic) — versão 3.0.14 ou mais recente
//  3. Placa: "ESP32 Dev Module" · Porta: a que aparecer ao ligar o USB
//  4. Carregar. Deve aparecer a animação de arranque no painel.
//
//  ---------------------------------------------------------------------
//  LIGAÇÕES  (ESP32 clássico → conector HUB75 de 16 pinos)
//  ---------------------------------------------------------------------
//    R1=25  G1=26  B1=27      R2=14  G2=12  B2=13
//    A=23   B=19   C=5        D=17   E=-1 (não usado num 64×32)
//    CLK=16 LAT=4  OE=15
//    GND → GND  (várias ligações, não só uma)
//
//  ⚠️ ALIMENTAÇÃO: o painel come 0,3-0,6 A no uso normal e até 4 A a branco
//     máximo. NUNCA o alimentes pelo pino 5V do ESP32 — leva um par de fios
//     grossos (18 AWG) direto ao barramento de 5,1 V, com fusível próprio.
//     A massa TEM de ser comum com a do ESP32.
//
//  ---------------------------------------------------------------------
//  PROTOCOLO — texto, uma linha por comando, para se poder depurar à mão
//  ---------------------------------------------------------------------
//    E <nome> <rx> <ry> <abEsq> <abDir> <red> <rot> <arco> <cheio> <ox> <oy> <cor>
//    F <forma> <cor>      formas especiais: coracao, arranque
//    B <0|1>              piscar automático
//    L <0-100>            brilho
//    M <ms>               duração da transição
//    P                    ping → responde OK
// ===========================================================================

#include <ESP32-HUB75-MatrixPanel-I2S-DMA.h>

// --------------------------------------------------------------------------
// Painel
// --------------------------------------------------------------------------
#define LARGURA 64
#define ALTURA  32

#define P_R1 25
#define P_G1 26
#define P_B1 27
#define P_R2 14
#define P_G2 12
#define P_B2 13
#define P_A  23
#define P_B  19
#define P_C   5
#define P_D  17
#define P_E  -1
#define P_LAT 4
#define P_OE 15
#define P_CLK 16

MatrixPanel_I2S_DMA *painel = nullptr;

// --------------------------------------------------------------------------
// Uma cara é este punhado de números. O morph é interpolá-los.
// --------------------------------------------------------------------------
struct Cara {
  float rx = 3.2f;
  float ry = 4.2f;
  float abEsq = 1.0f;
  float abDir = 1.0f;
  float redondeza = 0.55f;
  float rotacao = 0.0f;
  float arco = 0.0f;
  float cheio = 1.0f;
  float olharX = 0.0f;
  float olharY = 0.0f;
  uint8_t r = 0x36, g = 0xE0, b = 0xFF;
};

Cara deOnde;      // de onde vimos
Cara paraOnde;    // para onde vamos
Cara agora;       // o que está no ecrã

uint32_t morphInicio = 0;
uint16_t morphMs = 180;

enum Forma { OLHOS, CORACAO, ARRANQUE };
Forma forma = ARRANQUE;
uint32_t formaInicio = 0;

bool piscarAuto = true;
uint8_t brilho = 40;

// --------------------------------------------------------------------------
// Auxiliares
// --------------------------------------------------------------------------
static inline float lerp(float a, float b, float k) { return a + (b - a) * k; }

// Aceleração e desaceleração — um morph linear parece mecânico.
static inline float suavizar(float t) { return t * t * (3.0f - 2.0f * t); }

static inline float clampf(float v, float lo, float hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

Cara misturar(const Cara &a, const Cara &b, float k) {
  Cara c;
  c.rx        = lerp(a.rx, b.rx, k);
  c.ry        = lerp(a.ry, b.ry, k);
  c.abEsq     = lerp(a.abEsq, b.abEsq, k);
  c.abDir     = lerp(a.abDir, b.abDir, k);
  c.redondeza = lerp(a.redondeza, b.redondeza, k);
  c.rotacao   = lerp(a.rotacao, b.rotacao, k);
  c.arco      = lerp(a.arco, b.arco, k);
  c.cheio     = lerp(a.cheio, b.cheio, k);
  c.olharX    = lerp(a.olharX, b.olharX, k);
  c.olharY    = lerp(a.olharY, b.olharY, k);
  c.r = (uint8_t)lerp(a.r, b.r, k);
  c.g = (uint8_t)lerp(a.g, b.g, k);
  c.b = (uint8_t)lerp(a.b, b.b, k);
  return c;
}

// --------------------------------------------------------------------------
// A forma de um olho, como distância a uma superfície (SDF).
//
// Devolve <0 dentro do olho, >0 fora. É a mesma ideia do shader do bot-face:
// descrever a forma com uma fórmula em vez de uma lista de pixéis. É o que
// torna o morph trivial — interpolam-se os números, não as imagens.
// --------------------------------------------------------------------------
float sdfOlho(float px, float py, float cx, float cy,
              float rx, float ry, float abertura, float redondeza,
              float rotacao, float arco) {
  float dx = px - cx;
  float dy = py - cy;

  // rodar (é isto que faz a sobrancelha do "zangado")
  float s = sinf(rotacao), c = cosf(rotacao);
  float rxp = dx * c - dy * s;
  float ryp = dx * s + dy * c;

  // fechar o olho comprime-o na vertical
  float ryEfetivo = fmaxf(ry * abertura, 0.35f);

  // curvar (é isto que faz o "sorriso" dos olhos)
  if (arco != 0.0f) {
    float t = clampf(rxp / fmaxf(rx, 0.001f), -1.0f, 1.0f);
    ryp += arco * ryEfetivo * (1.0f - t * t);
  }

  float nx = rxp / fmaxf(rx, 0.001f);
  float ny = ryp / ryEfetivo;

  // redondeza mistura quadrado (norma infinita) com elipse (norma 2)
  float elipse = sqrtf(nx * nx + ny * ny);
  float caixa  = fmaxf(fabsf(nx), fabsf(ny));
  float d = lerp(caixa, elipse, clampf(redondeza, 0.0f, 1.0f));
  return d - 1.0f;
}

// Coração — a forma que o Astro mostra quando está mesmo contente.
float sdfCoracao(float px, float py, float cx, float cy, float escala) {
  float x = (px - cx) / escala;
  float y = -(py - cy) / escala;
  x = fabsf(x);
  if (y + x > 1.0f) {
    return sqrtf((x - 0.25f) * (x - 0.25f) + (y - 0.75f) * (y - 0.75f))
           - sqrtf(2.0f) / 4.0f;
  }
  float a = (x + y) * 0.5f;
  float d1 = sqrtf((x - a) * (x - a) + (y - a) * (y - a));
  float d2 = sqrtf((x - 0.5f) * (x - 0.5f) + y * y) * 0.7071f;
  return fminf(d1, d2) * ((x > y) ? 1.0f : -1.0f);
}

// --------------------------------------------------------------------------
// Desenhar uma imagem
// --------------------------------------------------------------------------
const float SEPARACAO = LARGURA * 0.19f;   // igual ao demo do browser
const float SUAVIDADE = 0.62f;             // largura da borda, em células

void desenhar(uint32_t t) {
  painel->clearScreen();

  float cy = ALTURA * 0.5f;

  // "respiração": o robô oscila muito ao de leve, sempre. Sem isto parece
  // uma imagem congelada; com isto parece vivo mesmo parado.
  float resp = sinf(t * 0.0016f) * 0.25f;

  if (forma == CORACAO) {
    // batida dupla, como um coração a sério
    float fase = fmodf(t * 0.0011f, 1.0f);
    float bat = 1.0f + 0.16f * (expf(-fase * 14.0f) + 0.6f * expf(-fabsf(fase - 0.22f) * 14.0f));
    for (int y = 0; y < ALTURA; y++) {
      for (int x = 0; x < LARGURA; x++) {
        float px = x + 0.5f, py = y + 0.5f;
        float d = fminf(
            sdfCoracao(px, py, LARGURA * 0.5f - SEPARACAO, cy + resp, 5.0f * bat),
            sdfCoracao(px, py, LARGURA * 0.5f + SEPARACAO, cy + resp, 5.0f * bat));
        float i = clampf(0.5f - d / SUAVIDADE, 0.0f, 1.0f);
        if (i > 0.02f) {
          painel->drawPixelRGB888(x, y, agora.r * i, agora.g * i, agora.b * i);
        }
      }
    }
    return;
  }

  if (forma == ARRANQUE) {
    // uma linha que abre, como um aparelho a ligar-se
    float k = clampf((t - formaInicio) / 900.0f, 0.0f, 1.0f);
    float meia = suavizar(k) * LARGURA * 0.42f;
    for (int x = 0; x < LARGURA; x++) {
      float d = fabsf(x + 0.5f - LARGURA * 0.5f) - meia;
      float i = clampf(0.5f - d / 1.2f, 0.0f, 1.0f);
      if (i > 0.02f) {
        for (int y = (int)cy - 1; y <= (int)cy; y++) {
          painel->drawPixelRGB888(x, y, agora.r * i, agora.g * i, agora.b * i);
        }
      }
    }
    if (k >= 1.0f) forma = OLHOS;
    return;
  }

  float ox = agora.olharX * 2.2f;
  float oy = agora.olharY * 1.6f + resp;

  for (int y = 0; y < ALTURA; y++) {
    for (int x = 0; x < LARGURA; x++) {
      float px = x + 0.5f, py = y + 0.5f;

      float dEsq = sdfOlho(px, py, LARGURA * 0.5f - SEPARACAO + ox, cy + oy,
                           agora.rx, agora.ry, agora.abEsq, agora.redondeza,
                           agora.rotacao, agora.arco);
      float dDir = sdfOlho(px, py, LARGURA * 0.5f + SEPARACAO + ox, cy + oy,
                           agora.rx, agora.ry, agora.abDir, agora.redondeza,
                           -agora.rotacao, agora.arco);
      float d = fminf(dEsq, dDir);

      // contorno em vez de maciço, quando cheio < 1
      if (agora.cheio < 0.5f) d = fabsf(d) - 0.22f;

      float i = clampf(0.5f - d / (SUAVIDADE / fmaxf(agora.rx, 1.0f)), 0.0f, 1.0f);
      if (i > 0.02f) {
        painel->drawPixelRGB888(x, y, agora.r * i, agora.g * i, agora.b * i);
      }
    }
  }
}

// --------------------------------------------------------------------------
// Piscar sozinho — irregular de propósito
// --------------------------------------------------------------------------
uint32_t proximoPiscar = 3000;
bool aPiscar = false;
uint32_t piscarInicio = 0;

void tratarPiscar(uint32_t t) {
  if (!piscarAuto || forma != OLHOS) return;

  if (!aPiscar && t > proximoPiscar) {
    aPiscar = true;
    piscarInicio = t;
  }
  if (aPiscar) {
    uint32_t decorrido = t - piscarInicio;
    const uint32_t DURACAO = 140;
    if (decorrido >= DURACAO) {
      aPiscar = false;
      // intervalo irregular: um piscar a compasso certo parece um metrónomo
      proximoPiscar = t + 2600 + (esp_random() % 4200);
    } else {
      float k = (float)decorrido / DURACAO;
      float fecho = sinf(k * PI);        // fecha e volta a abrir
      agora.abEsq *= (1.0f - fecho * 0.94f);
      agora.abDir *= (1.0f - fecho * 0.94f);
    }
  }
}

// --------------------------------------------------------------------------
// Ler comandos da porta série
// --------------------------------------------------------------------------
char buffer[256];
uint8_t nBuffer = 0;

void corDeHex(const char *hex, Cara &c) {
  long v = strtol(hex, nullptr, 16);
  c.r = (v >> 16) & 0xFF;
  c.g = (v >> 8) & 0xFF;
  c.b = v & 0xFF;
}

void aplicar(const Cara &nova, Forma novaForma) {
  deOnde = agora;
  paraOnde = nova;
  morphInicio = millis();
  if (novaForma != forma) {
    forma = novaForma;
    formaInicio = millis();
  }
}

void tratarLinha(char *linha) {
  char cmd = linha[0];

  if (cmd == 'P') {
    Serial.println("OK");
    return;
  }
  if (cmd == 'B') {
    piscarAuto = atoi(linha + 2) != 0;
    Serial.println("OK");
    return;
  }
  if (cmd == 'L') {
    brilho = constrain(atoi(linha + 2), 0, 100);
    painel->setBrightness8(map(brilho, 0, 100, 0, 200));
    Serial.println("OK");
    return;
  }
  if (cmd == 'M') {
    morphMs = constrain(atoi(linha + 2), 0, 3000);
    Serial.println("OK");
    return;
  }
  if (cmd == 'F') {
    char nomeForma[24] = {0};
    char hex[10] = {0};
    if (sscanf(linha + 2, "%23s %9s", nomeForma, hex) >= 1) {
      Cara nova = paraOnde;
      if (hex[0]) corDeHex(hex, nova);
      Forma f = OLHOS;
      if (!strcmp(nomeForma, "coracao")) f = CORACAO;
      else if (!strcmp(nomeForma, "arranque")) f = ARRANQUE;
      aplicar(nova, f);
      Serial.println("OK");
    }
    return;
  }
  if (cmd == 'E') {
    char nome[32] = {0}, hex[10] = {0};
    Cara n;
    int lidos = sscanf(linha + 2,
        "%31s %f %f %f %f %f %f %f %f %f %f %9s",
        nome, &n.rx, &n.ry, &n.abEsq, &n.abDir, &n.redondeza,
        &n.rotacao, &n.arco, &n.cheio, &n.olharX, &n.olharY, hex);
    if (lidos >= 11) {
      if (hex[0]) corDeHex(hex, n);
      aplicar(n, OLHOS);
      Serial.println("OK");
    } else {
      Serial.println("ERRO parametros");
    }
    return;
  }
  Serial.println("ERRO comando");
}

void lerSerie() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (nBuffer) {
        buffer[nBuffer] = 0;
        tratarLinha(buffer);
        nBuffer = 0;
      }
    } else if (nBuffer < sizeof(buffer) - 1) {
      buffer[nBuffer++] = c;
    }
  }
}

// --------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);

  HUB75_I2S_CFG::i2s_pins pinos = {
      P_R1, P_G1, P_B1, P_R2, P_G2, P_B2,
      P_A, P_B, P_C, P_D, P_E, P_LAT, P_OE, P_CLK};
  HUB75_I2S_CFG cfg(LARGURA, ALTURA, 1, pinos);
  cfg.double_buff = true;

  painel = new MatrixPanel_I2S_DMA(cfg);
  painel->begin();
  painel->setBrightness8(map(brilho, 0, 100, 0, 200));
  painel->clearScreen();

  forma = ARRANQUE;
  formaInicio = millis();
  Serial.println("PRONTO bot-face");
}

void loop() {
  lerSerie();

  uint32_t t = millis();

  // transição suave entre a cara antiga e a nova
  float k = (morphMs == 0) ? 1.0f
            : clampf((float)(t - morphInicio) / morphMs, 0.0f, 1.0f);
  agora = misturar(deOnde, paraOnde, suavizar(k));

  tratarPiscar(t);
  desenhar(t);
  painel->flipDMABuffer();

  delay(16);   // ~60 imagens por segundo
}
