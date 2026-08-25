# Enquanto o Pi não chega

O Raspberry Pi está encomendado. **Cinco destas sete coisas não precisam dele.**

Estão por ordem de valor para a Lara, não por ordem de dificuldade. A primeira
demora meia hora e é a que mais vale a pena — ela ouve a voz do robô antes de o
robô existir.

| | O quê | Quanto tempo | Precisa de quê |
|---|---|---|---|
| 1 | **A voz da Lylla** | 30 min | só o Mac |
| 2 | **O cartão** | uma tarde | tesoura e caixas |
| 3 | **As caras** | sempre que ela quiser | só o Mac |
| 4 | **O cérebro** | uma noite (download) | só o Mac |
| 5 | **O ESP32 que já temos** | 1 h | o ESP32 |
| 6 | **Encomenda 2 — já** | 15 min | ⚠️ é a que tem prazo maior |
| 7 | A palavra-chave | 20 min | um microfone qualquer |

---

## 1 · A voz da Lylla — 30 minutos, e é o melhor primeiro passo

A voz corre no Mac. É lá que ela vive e é de lá que o robô a vai buscar.

**Primeiro, deixa a Lara escolhê-la.** Este comando gera a mesma frase em oito vozes de
português europeu e toca-as por ordem aleatória, sem dizer qual é qual:

```bash
python3 -m venv ~/.venvs/lylla && source ~/.venvs/lylla/bin/activate
pip install phoonnx tugaphone piper-tts

python scripts/testar_vozes.py --cego
```

Ela ouve, escolhe um número, e só no fim é que se revela qual era. Foi assim que saiu a
**Joana** — a voz do próprio macOS — à frente de todos os modelos abertos. Se a escolha
dela for outra, muda o `voz.voz_mac` no `config/robot.yaml`.

> Se alguma voz não aparecer na lista das do Mac: Definições → Acessibilidade →
> Conteúdo falado → Voz do sistema → Português (Portugal) → Gerir vozes.

**Depois, põe a voz de pé.** Este é o serviço que o robô vai chamar pela rede de casa —
e que já podes usar hoje, sem robô nenhum:

```bash
python scripts/servidor_voz.py
```

Noutro terminal:

```bash
curl -s -X POST http://localhost:8420/falar \
  -H "Content-Type: application/json" \
  -d '{"texto": "Olá Lara. Eu sou a Lylla. Ainda não tenho corpo, mas já tenho voz."}' \
  -o ola.wav && afplay ola.wav
```

Deixa-a escrever cinco frases que ela queira que ele diga um dia. Guardem-nas.
São as frases do **modo offline** da fase 14.

---

## 2 · O cartão — uma tarde, e decide o projeto todo

O plano diz **"cartão primeiro, sempre"** (§11.5) e é a sério: nenhuma peça
impressa em 3D, nenhum furo, nenhum corte definitivo antes de existir uma versão
em cartão em tamanho real.

Constrói-se com caixas de cereais e fita-cola. O que interessa decidir:

- **Cabe tudo?** A cabeça tem de levar um painel de 16×8 cm mais o ESP32 atrás.
- **Fica de pé?** A bateria vai na base, o mais baixo possível — é a peça mais
  pesada e é ela que impede o robô de tombar quando os braços se levantam.
- **Chega à mesa?** Escolheste que ele anda na secretária. Faz o teste do
  tombo: empurra-o de lado em cima da mesa e vê se cai.
- **Onde é que a Lara mete a mão** para o ligar e desligar?

A tabela de §11.3 do plano diz onde vive cada peça e porquê. A folha de design
(`docs/design-astrosonda.html`) imprime-se e desenha-se por cima.

⚠️ **Isto é a coisa mais valiosa desta lista** e não precisa de nada que ainda
não tenhas. Uma tarde de cartão poupa três semanas de peças que não encaixam.

---

## 3 · As caras — para ela mexer sempre que quiser

Todo o robô corre no Mac sem hardware nenhum:

```bash
cd ~/Developer/my-robot
python3 -m venv .venv && source .venv/bin/activate
pip install PyYAML numpy requests opencv-python pytest      # o essencial

ROBO_SIMULAR=1 python scripts/test_eyes.py                  # passa pelas 19 caras
ROBO_SIMULAR=1 python -m pytest -q                          # 121 testes, 3 segundos
```

Depois abre `config/expressoes.yaml`. Está tudo em números que ela percebe:

```yaml
  feliz:
    rx: 3.2
    ry: 4.4
    arco: 0.62          # ← é o arco que faz o "sorriso" dos olhos
    redondeza: 0.5
```

Ela muda um número, corre `test_eyes.py`, vê. Se escrever um valor impossível,
o `pytest` diz-lhe qual e porquê — em português, não com um *stack trace*.

**É o ciclo de aprendizagem mais curto do projeto inteiro: mudar um número e ver
o resultado em dois segundos.** Não precisa do Pi, não precisa do painel, não
precisa de ti.

Se ela inventar caras novas, ficam guardadas e aparecem no robô no dia em que o
painel chegar. Sem recompilar nada.

---

## 4 · O cérebro — uma noite, sobretudo de download

A fase 11 do plano é toda no Mac. Pode ser feita já.

```bash
brew install ollama
ollama serve &
ollama pull gemma4:12b          # 7,6 GB — deixa a descarregar
```

⚠️ **Confirma a memória primeiro:**

```bash
sysctl hw.memsize | awk '{print $2/1073741824 " GB"}'
```

O `gemma4:12b` são 7,6 GB de pesos e quer **16 GB de RAM** para correr com
folga. Se o Mac tiver 8 GB, usa `gemma4:4b` — é pior a escolher ferramentas, mas
funciona, e trocar depois é uma linha no `config/robot.yaml`.

Para o robô lhe chegar pela rede, o Ollama tem de ouvir em todos os interfaces e
não só em `localhost`:

```bash
launchctl setenv OLLAMA_HOST 0.0.0.0:11434
# e reiniciar o ollama
```

Testar de outro computador da casa:

```bash
curl http://mac.local:11434/api/tags
```

E depois — a parte boa — **fala com o robô sem robô nenhum**:

```bash
ROBO_SIMULAR=1 python -m robot.main
```

Tudo sai no terminal: os olhos, os motores, os braços, a voz. Ela escreve, ele
responde e "faz" coisas. É o robô todo, sem corpo.

---

## 5 · O ESP32 que já temos — 1 hora, e tira o risco da fase 3

O painel HUB75 ainda não chegou, mas o ESP32 já cá está. Vale a pena confirmar
hoje que a cadeia de compilação funciona, porque é a parte da fase 3 onde é mais
provável perder-se uma tarde.

1. Arduino IDE → *Preferences* → *Additional Boards Manager URLs*:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
2. *Boards Manager* → instalar **esp32** (Espressif Systems)
3. *Library Manager* → instalar **ESP32 HUB75 LED MATRIX PANEL DMA Display**
4. Abrir `firmware/bot_face_esp32/bot_face_esp32.ino` e carregar em **Verify**

Se compilar, está tudo bem. Se carregares no ESP32 sem o painel ligado, ele
arranca à mesma e responde ao `P` (ping) na porta série a 115200 — dá para ver
com o *Serial Monitor* que o protocolo funciona antes de existir painel.

---

## 6 · Encomenda 2 — esta encomenda-se JÁ, não daqui a um mês

⚠️ **É a única coisa desta lista com urgência real.**

O pack **LiFePO4 4S com BMS** apareceu em falta em várias lojas maker
portuguesas durante a pesquisa, e vem quase sempre da Alemanha ou da China.
Se for encomendado só quando a fase 5 chegar, o projeto pára à espera dele.

**Ao encomendar, exige duas coisas:**

- **BMS de porta comum** (*common port*), não de porta separada. Na secretária o
  robô fica ligado à ficha, e um BMS de porta separada **não deixa carregar e
  descarregar ao mesmo tempo**.
- **LiFePO4 (LFP), não Li-ion nem LiPo.** Foi escolhida por segurança: não tem
  fuga térmica auto-alimentada. Está num quarto de criança.

O resto da encomenda 2 (painel HUB75, reguladores Pololu, carregador) pode
seguir junto — são €300 e são precisos nas fases 3 a 5.

---

## 7 · A palavra-chave — 20 minutos com ela

O `openWakeWord` treina-se com amostras da voz de quem vai usar o robô. Gravar
as amostras não precisa do Pi: chega o microfone do Mac e o Photo Booth ou o
QuickTime.

Grava-a a dizer **"Olá robô"** umas 30 vezes, com variações: perto, longe, a
rir, com a televisão ligada, de manhã com a voz de sono. As gravações más são as
mais importantes — são elas que ensinam o modelo a não acordar sozinho.

Guarda em `data/wakeword/` (essa pasta não vai para o Git). O treino em si fica
para a fase 10.

---

## O que NÃO dá para fazer ainda

Para ser honesto, e para não se perder tempo a tentar:

| | Porquê |
|---|---|
| Reconhecer caras | Precisa da câmara **e** do Pi. O `opencv` corre no Mac, mas registar caras com a webcam do Mac dá assinaturas que não servem no Pi — lente e iluminação diferentes |
| Testar os motores | Precisa dos PCA9685 e da fonte (encomenda 3) |
| Soldar | A bancada (€147) ainda não foi encomendada. Ver §10.5 e fase 0.5 |
| Medir quanto custa "olhar" | `scripts/test_companion.py --custo` só dá números a sério no Pi |

---

## Ordem sugerida

**Este fim-de-semana:** a voz (1) e o cartão (2). São as duas com ela, e são as
que fazem o projeto parecer real.

**Durante a semana, sozinho:** a encomenda 2 (6) na segunda-feira — é a que tem
prazo. Depois o Ollama a descarregar (4) e o ESP32 (5) numa noite.

**Quando ela quiser:** as caras (3). Não tem fim e não precisa de ninguém.
