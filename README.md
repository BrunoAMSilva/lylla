# 🤖 Robô da Lara

Um robô grande, com rodas e braços, que reconhece caras, ouve mesmo enquanto
fala, e pensa com um LLM que corre no Mac lá de casa.

> **O plano completo está em [`PLANO.md`](PLANO.md).** Este ficheiro é só para
> pôr as coisas a andar.
>
> **A ligar a câmara pela primeira vez?**
> [`docs/FASE9-visao.md`](docs/FASE9-visao.md) — do cabo CSI até «Olá, Lara!»,
> passo a passo, com as duas armadilhas que fazem culpar o hardware sem razão.
>
> **Ainda à espera das peças?** [`ENQUANTO-ESPERAS.md`](ENQUANTO-ESPERAS.md) —
> cinco das sete coisas que dá para fazer hoje não precisam do Raspberry Pi.
> Começa pela voz: são 30 minutos e ela ouve o robô falar antes de ele existir.
> Para ver o que já está pronto: `python scripts/check_mac.py`

---

## Começar (5 minutos)

```bash
git clone <este-repo> ~/my-robot
cd ~/my-robot
python3 -m venv --system-site-packages .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install --no-deps "openwakeword>=0.6.0"     # porquê --no-deps: está no requirements.txt
python scripts/check_health.py
```

> ⚠️ **No Raspberry Pi, o `--system-site-packages` não é opcional.** A câmara
> (`picamera2`) só se instala pelo `apt` — `sudo apt install --no-install-recommends
> python3-picamera2` — e um venv normal não a vê. A instalação completa do Pi
> está no Apêndice B do `PLANO.md`. No Mac tanto faz: lá corre tudo em simulação.

> 🔊 **A coluna liga-se ao reSpeaker, não ao Pi.** O reSpeaker XVF3800 é a placa
> de som do robô (microfones **e** coluna, por USB) — é a única maneira de o
> cancelamento de eco funcionar. Não há amplificador I2S nem `hifiberry` no
> `config.txt`; há duas linhas em `/etc/asound.conf` (Apêndice B).

## O cérebro, no mac mini

Os modelos de IA — ouvir, pensar e falar — correm todos no mac mini, não no
robô. O Pi manda o áudio **enquanto a Lara ainda está a falar**, e recebe de
volta a resposta já em som, frase a frase.
**A explicação toda está em [`docs/AI-config.md`](docs/AI-config.md).**

```bash
# no mini, uma vez
./cerebro/instalar.sh --servico

# testar sem microfone nenhum (dá para fazer hoje)
python scripts/test_cerebro.py "segue-me!"

# escolher os modelos com números em vez de opiniões
python -m cerebro.medir
```

No robô, o `config/robot.yaml` só precisa de saber o endereço:

```yaml
cerebro:
  url: "http://mini:8420"
```

(É o Tailscale que resolve o nome `mini`, portanto funciona em casa ou fora
dela.)

**Não há Whisper nem Ollama dentro do robô.** Com o mini desligado ele não
percebe o que lhe dizem — e diz isso, com a voz que tem em cache — mas continua
a andar, a ver, a reconhecer caras e a obedecer ao «pára».

## Andar pela casa — «Lylla, vai à cozinha»

Desenha-se a planta da casa numa página, treina-se um cérebro a conduzir lá
dentro **por evolução** (centenas de robôs por geração, os melhores têm
filhos), e o ficheiro que sai daí é o que o Pi lê.

```bash
open docs/escola-de-conducao.html          # planta + treino + campeã, sem instalar nada
ROBO_SIMULAR=1 python scripts/escondidas.py --onde "quarto da Lara"
```

O mapa dá a rota; as redes tratam do saco que hoje está no corredor, do gato e
de quem passa. **A explicação toda — incluindo as três coisas que isto NÃO
resolve — está em [`docs/navegacao.md`](docs/navegacao.md).**

> ⚠️ Vem desligado no robô a sério (`navegacao.ativo: false`). Em
> `ROBO_SIMULAR=1` anda sempre.

## Está tudo bem?

```bash
python scripts/check_health.py
```

Mostra uma lista com ✅ e ❌ de cada peça: motores, olhos, câmara, microfone,
coluna, sensores e o LLM no Mac. **Corre isto sempre que alguma coisa parecer
estranha, antes de mexer em código.**

## Testar cada peça sozinha

Quando alguma coisa falha, a primeira pergunta é sempre *"é o hardware ou é o
código?"*. Estes scripts respondem em 30 segundos:

```bash
python scripts/test_eyes.py       # mostra as 9 expressões, uma a uma
python scripts/test_motors.py     # roda cada motor isoladamente
python scripts/test_arms.py       # passa por todas as poses e gestos
python scripts/test_voz.py        # diz uma frase
python scripts/test_camera.py     # tira uma foto e desenha as caras
python scripts/medir_visao.py     # quanto custa ver, a cada resolução
/usr/bin/python3 scripts/ver_camera.py   # ver pela câmara no browser (telemóvel incluído) — só precisa do apt
python scripts/ver_visao.py       # o mesmo, mas com as caixas, os nomes e os tempos
python scripts/test_sensores.py   # imprime as distâncias em tempo real
python scripts/test_power.py      # tensão e percentagem da bateria
python scripts/vigiar_energia.py --forcar 90   # a fonte aguenta o CPU em carga?
python scripts/test_cerebro.py    # conversa com o mac mini, escrita
python scripts/test_cerebro.py --escutar frase.wav   # o áudio em contínuo
```

⚠️ **Antes de mexer nos braços pela primeira vez**, corre
`python scripts/test_arms.py --juntas` com os servos montados mas **sem os
braços colados**. Confirma que cada canal corresponde à junta certa — um horn
na posição errada bate no corpo logo à primeira.

## Ligar o robô

```bash
python -m robot.main
```

Ou, se já estiver instalado como serviço, ele arranca sozinho quando se liga
a bateria:

```bash
sudo systemctl start robo
sudo systemctl status robo
journalctl -u robo -f          # ver o que está a acontecer
```

## Ensinar uma cara nova

A melhor maneira é pelo browser — a pose aparece ao lado do vídeo e a pessoa
vê a própria cara com a caixa à volta enquanto posa:

```bash
python scripts/ver_visao.py              # e abre http://<pi>.local:8001
```

Pelo terminal também dá, quando não há mais nada à mão:

```bash
python scripts/enrol_face.py Lara        # 8 fotos, uma por Enter
python scripts/enrol_face.py --listar    # quem é que ele conhece?
python scripts/enrol_face.py --apagar Lara
```

> 🔒 As assinaturas ficam em `data/faces/` e **nunca** vão para o Git. Não são
> fotografias — são 128 números por pessoa. E qualquer pessoa pode pedir para
> ser apagada.

---

## Modo simulação — programar sem o robô

**Todos os módulos funcionam sem hardware nenhum.** Se o Pi não estiver por
perto, ou as peças ainda não tiverem chegado, o código corre à mesma no Mac e
escreve no terminal o que faria:

```bash
ROBO_SIMULAR=1 python -m robot.main
```

```
[SIM] olhos → feliz
[SIM] motores → esq=+0.50 dir=+0.50
[SIM] servo ombro_dir → 140°
[SIM] falar → "Olá, Lara!"
```

Isto quer dizer que se pode escrever e testar comportamentos enquanto se
espera pelas encomendas.

---

## O que a Lara pode mudar sozinha

| Ficheiro | O que muda |
|---|---|
| `robot/expressions.py` | **As caras do robô.** Grelhas 8×8 de `#` e `.` |
| `robot/gestures.py` | **Os gestos dos braços.** Poses e sequências |
| `config/personalidade.txt` | **Como o robô fala e pensa.** É o system prompt |
| `config/robot.yaml` | Nome, velocidades, limites dos servos, segurança |

Mudar qualquer um destes quatro **não parte nada**. Se puseres um ângulo fora
dos limites, o robô corrige-o sozinho e avisa-te. Experimenta à vontade.

### Exemplo: inventar uma cara nova

São **dois passos** — desenhar, e depois dizer ao robô que ela existe.

**1.** Abre `robot/expressions.py` e desenha:

```python
CONFUSO = [
    "........",
    "..#..#..",
    ".#.##.#.",
    "........",
    "...##...",
    "..#..#..",
    "...##...",
    "........",
]
```

**2.** No mesmo ficheiro, mais abaixo, acrescenta uma linha ao dicionário
`EXPRESSOES` (senão o robô não sabe que ela existe):

```python
EXPRESSOES = {
    ...
    "confuso": (CONFUSO, CONFUSO),   # ← esta linha
}
```

Depois `python scripts/test_eyes.py confuso` e vê o resultado.

---

## Estrutura

```
cerebro/          O QUE CORRE NO MAC MINI (não no robô)
├── servidor.py   a API :8420 (+ o WebSocket /v1/escutar)
├── ouvir.py      Parakeet TDT      → texto, à medida que o áudio chega
├── pensar.py     LLM               → cara + fala + ações
├── falar.py      Piper             → áudio
└── medir.py      qual dos modelos serve

robot/
├── hardware/
│   ├── pca9685.py    driver partilhado de PWM por I2C
│   ├── motors.py     as rodas (TB6612 via PCA9685 @0x40, 1 kHz)
│   ├── arms.py       os braços (5 servos via PCA9685 @0x41, 50 Hz)
│   ├── eyes.py       a matriz de LED
│   ├── sensors.py    distância e precipício
│   └── power.py      a bateria (ADS1115 @0x48)
├── perception/   câmara, reconhecer caras        → os sentidos
├── voice/        falar, ouvir, palavra-chave     → a boca e os ouvidos
├── brain/
│   ├── acoes.py      O CONTRATO — lido também pelo mini
│   ├── cerebro.py    o cliente do mini
│   ├── contexto.py   o que o robô sabe agora
│   └── …             ferramentas, estados, seguir
├── navigation/   ATRAVESSAR A CASA               → ver docs/navegacao.md
│   ├── casa.py       a planta e o campo de distância (igual ao do browser)
│   ├── piloto.py     as três redes treinadas, em numpy
│   ├── pose.py       onde ela julga estar — e o quanto pode estar enganada
│   ├── ir_para.py    conduzir, com os sensores por cima da rede
│   └── procurar.py   às escondidas
├── expressions.py                                → as caras (edita a Lara)
├── gestures.py                                   → os gestos (edita a Lara)
└── main.py                                       → o ciclo principal
```

### Endereços I2C

| Chip | Endereço | Para quê |
|---|---|---|
| PCA9685 #1 | `0x40` | Motores, a 1 kHz |
| PCA9685 #2 | `0x41` | Servos, a 50 Hz |
| VL53L1X | `0x29` | Distância a laser |
| ADS1115 | `0x48` | Tensão da bateria |

São **dois** PCA9685 porque o chip só tem uma frequência para os 16 canais:
servos querem 50 Hz, motores a 50 Hz rosnam.

## Regras da casa

1. **Cada peça de hardware tem um script de teste isolado.** Sem exceções.
2. **As funções que a Lara usa têm nomes em português** e fazem uma coisa só.
3. **Nada rebenta.** Sem Wi-Fi, sem câmara, sem Mac — o robô continua a andar
   e diz o que se passa. Um *stack trace* à frente de uma criança mata o
   projeto.

---

## Emergência

```bash
sudo systemctl stop robo     # PARA TUDO
i2cdetect -y 1               # 0x40 motores · 0x41 servos · 0x29 ToF · 0x48 bateria
aplay -l                     # o reSpeaker aparece? (é a coluna E os microfones)
rpicam-hello --list-cameras  # a câmara aparece? (imx708)
vcgencmd get_throttled       # 0x0 = alimentação está bem
python scripts/test_power.py # quanta bateria resta
tailscale status | grep mini           # o mini está na rede?
curl http://mini:8420/v1/saude         # o cérebro está de pé?
curl http://mini:11434/api/tags        # e o Ollama por baixo dele?
```

**E o botão vermelho.** Corta a corrente aos servos e aos motores sem desligar
o Pi — o robô para de se mexer instantaneamente e continua a explicar o que
aconteceu.
