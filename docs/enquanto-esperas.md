# Arquivo das atividades enquanto o Pi não chegava

> **Este calendário já terminou.** O Pi chegou e a lista de encomendas abaixo
> foi substituída. Não comprar nem montar a partir deste ficheiro. Usar
> [`docs/componentes.md`](docs/componentes.md) para o inventário e
> [`docs/roteiro.md`](docs/roteiro.md) para as próximas experiências.

As atividades abaixo ficam como registo. Algumas ainda servem isoladamente,
mas a sua ordem e os seus pressupostos de hardware são antigos.

Estão por ordem de valor para a Lara, não por ordem de dificuldade. A primeira
demora meia hora e é a que mais vale a pena — ela ouve a voz do robô antes de o
robô existir.

| | O quê | Quanto tempo | Precisa de quê |
|---|---|---|---|
| 1 | **A voz da Lylla** | 30 min | só o Mac |
| 2 | **O cartão** | uma tarde | tesoura e caixas |
| 3 | **As expressões dos olhos** | sempre que ela quiser | só o Mac |
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

**Depois, põe o cérebro de pé.** É o serviço que o robô vai chamar pela rede de casa —
e que já podes usar hoje, sem robô nenhum:

```bash
./cerebro/instalar.sh          # no mac mini, uma vez
python -m cerebro.servidor
```

Noutro terminal:

```bash
curl -s -X POST http://localhost:8420/v1/falar \
  -H "Content-Type: application/json" \
  -d '{"texto": "Olá Lara. Eu sou a Lylla. Ainda não tenho corpo, mas já tenho voz."}' \
  -o ola.wav && afplay ola.wav
```

Deixa-a escrever cinco frases que ela queira que ele diga um dia. Guardem-nas.
São as frases do **modo offline** da fase 14.

### E já dá para CONVERSAR com ela

Sem microfone, sem coluna, sem robô — a escrever:

```bash
python scripts/test_cerebro.py
```

```
👤 Lylla, segue-me até à cozinha!
   [  26 ms] 👀 feliz
   [ 900 ms] 🤖 «Claro! Vou atrás de ti.»  (48 KB)
   ⚙️  seguir({'acao': 'comecar'})   (não executada — usa --executar)
```

A cara, a fala e a ação vêm as três na mesma resposta. Com `--tocar`, ouve-se.

E se gravares uma frase (com o telemóvel serve), dá para ver o áudio a ir para
o mini **enquanto ela fala**, que é como o robô vai funcionar:

```bash
python scripts/test_cerebro.py --escutar frase.wav
```

Deixa a Lara falar com ela e apontar o que soa mal — é assim que se afina o
`config/personalidade.txt`, que é o ficheiro dela. Ver
[`docs/AI-config.md`](docs/AI-config.md).

---

## 2 · O cartão — uma tarde, e decide o projeto todo

Esta atividade continua útil apenas como estudo de volume. A cara ainda pode
usar HUB75 ou OLED. Façam uma caixa ajustável e não abram furos nem cortem a
peça final para um ecrã específico.

O plano diz **"cartão primeiro, sempre"** (§11.5) e é a sério: nenhuma peça
impressa em 3D, nenhum furo, nenhum corte definitivo antes de existir uma versão
em cartão em tamanho real.

Constrói-se com caixas de cereais e fita-cola. O que interessa decidir:

- **Cabe tudo?** Reservem volume para as duas opções de ecrã e para o
  controlador que cada uma exigir.
- **Fica de pé?** A bateria vai na base, o mais baixo possível — é a peça mais
  pesada e é ela que impede o robô de tombar quando os braços se levantam.
- **Fica estável?** Testem a base no chão, sem alimentação e longe de qualquer
  borda. Não façam testes de queda numa mesa.
- **Onde é que a Lara mete a mão** para o ligar e desligar?

A tabela de §11.3 do plano diz onde vive cada peça e porquê. A folha de design
(`docs/design-astrosonda.html`) imprime-se e desenha-se por cima.

⚠️ **Isto é a coisa mais valiosa desta lista** e não precisa de nada que ainda
não tenhas. Uma tarde de cartão poupa três semanas de peças que não encaixam.

---

## 3 · As expressões dos olhos

As expressões YAML e o backend HUB75 continuam a servir como protótipo. Não
provam a escolha do ecrã. O POC `bot-face`, em
`/Users/brunosilva/Developer/bot-filter`, também entra na comparação com um
OLED concreto.

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

Este teste só confirma que o protótipo HUB75 ainda compila. Não escolhe o
ecrã nem justifica uma compra. A placa encontrada é de cerca de 2017, tem
Micro-USB e ainda precisa de ser identificada.

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

## 6 · A encomenda antiga

Esta recomendação foi retirada. Não comprar o pack, os reguladores nem o
painel a partir desta lista. O mBot2 permanece inteiro, por isso o antigo
barramento para motores deixou de fazer sentido. A cara continua por decidir.

As peças que chegam em 5 de setembro devem ser identificadas e testadas uma a
uma. A lista está em [`docs/componentes.md`](docs/componentes.md). Uma fonte ou
bateria para o conjunto só é escolhida depois de medir o mBot2 intacto, o Pi e
os periféricos realmente usados.

---

## 7 · A palavra-chave — 20 minutos com ela

A palavra-chave continua no Pi. Antes de gravar ou treinar, identifica os três
microfones que chegam e mede qual deles funciona melhor a várias distâncias e
com ruído. Só depois se fixa a frase de ativação e o conjunto de amostras.

Qualquer gravação de voz fica em `data/wakeword/`, fora do Git, e requer o
consentimento de quem fala.

---

## Estado das antigas limitações

| | Porquê |
|---|---|
| Reconhecer pessoas | YuNet, SFace e as assinaturas ficam no Pi. Falta validar o fluxo completo no hardware montado |
| Testar os motores | Já se pode testar o mBot2 inteiro por USB, primeiro com as rodas no ar |
| Soldar | O ferro e os materiais já chegaram. A primeira sessão é numa placa de prática |
| Medir quanto custa reconhecer | Falta medir no Pi o caminho completo desde a câmara até ao nome reconhecido |

---

## Ordem sugerida

A ordem desta página foi encerrada. O trabalho começa pelo mBot2 intacto e
pelos sensores que já traz. Depois inventariam-se as peças novas. A sequência
e os critérios estão em [`docs/roteiro.md`](docs/roteiro.md).
