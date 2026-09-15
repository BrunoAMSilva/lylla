# Robô da Lara

Lylla é um robô com rodas que Lara está a construir e programar. O mBot2 fica
inteiro e é controlado pelo Raspberry Pi através de USB. O mac mini executa
STT, LLM e TTS. A palavra-chave e o reconhecimento de pessoas ficam no Pi.

> **Começa pelas [`decisões atuais`](docs/decisoes-atuais.md).** O `PLANO.md`
> contém o histórico de alternativas. Quando houver
> conflito, as decisões atuais e a configuração executável têm precedência.
>
> **Para construir por ordem**, segue o [`roteiro ativo`](docs/roteiro.md).
>
> **A ligar a câmara pela primeira vez?**
> [`docs/FASE9-visao.md`](docs/FASE9-visao.md) — do cabo CSI até «Olá, Lara!»,
> passo a passo, com as duas armadilhas que fazem culpar o hardware sem razão.
>
> `ENQUANTO-ESPERAS.md` conserva as atividades da fase anterior. Já não define
> a ordem do projeto.

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

> **O áudio físico ainda está em teste.** A entrega de três microfones, um
> MAX98357A I2S e uma coluna de 3 W está prevista para 5 de setembro. Primeiro registamos os modelos e
> as ligações. Depois escolhemos uma cadeia de entrada e saída. O cancelamento
> durante a fala fica planeado, mas não bloqueia esta etapa.

## O cérebro, no mac mini

O mac mini executa a transcrição, o modelo de linguagem e a síntese de voz. O
Pi executa a palavra-chave, a visão, o reconhecimento de pessoas e o controlo
do corpo. Só o áudio da conversa precisa de fazer a viagem até ao mini.
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

**Não há Whisper nem Ollama dentro do robô.** Com o mini desligado, Lylla não
transcreve frases nem cria respostas novas. Continua a reconhecer pessoas no
Pi. Uma ordem falada, incluindo `pára`, precisa da transcrição do mini. O
timeout atual dos motores ainda não é um watchdog independente. A etapa 3 do
roteiro corrige isso antes dos testes de movimento no chão.

## Autonomia avançada

Seguir pessoas, navegar entre divisões e jogar às escondidas só entram depois
de os testes de bancada, obstáculos e bordas passarem. A simulação pode ser
usada antes disso.

```bash
open docs/escola-de-conducao.html          # planta + treino + campeã, sem instalar nada
ROBO_SIMULAR=1 python scripts/escondidas.py --onde "quarto da Lara"
```

O mapa dá a rota; as redes tratam do saco que hoje está no corredor, do gato e
de quem passa. **A explicação toda — incluindo as três coisas que isto NÃO
resolve — está em [`docs/navegacao.md`](docs/navegacao.md).**

> A navegação real vem desligada (`navegacao.ativo: false`). Ativá-la exige a
> lista de segurança descrita em [`docs/navegacao.md`](docs/navegacao.md).

## Está tudo bem?

```bash
python scripts/check_health.py
```

Mostra o que já está instalado, o que está ausente e o que ainda pertence a uma
etapa futura. **Corre isto sempre que alguma coisa parecer estranha, antes de
mexer em código.**

## Testar cada peça sozinha

Quando alguma coisa falha, a primeira pergunta é sempre *"é o hardware ou é o
código?"*. Estes scripts respondem em 30 segundos:

```bash
python scripts/spike_mbot2.py --sem-medir --luzes --sensores  # LEDs e sensores existentes
python scripts/spike_mbot2.py --sem-medir --chao   # mede os 4 canais, sem mover
python scripts/test_motors.py     # rodas, depois de o spike passar
python scripts/test_eyes.py       # futuro ecrã, depois de ser escolhido
python scripts/test_arms.py       # braços futuros
python scripts/test_voz.py        # diz uma frase
python scripts/test_camera.py     # tira uma foto e desenha as caras
python scripts/medir_visao.py     # quanto custa ver, a cada resolução
/usr/bin/python3 scripts/ver_camera.py   # ver pela câmara no browser (telemóvel incluído) — só precisa do apt
python scripts/ver_visao.py       # o mesmo, mas com as caixas, os nomes e os tempos
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
| `config/expressoes.yaml` | Parâmetros das caras usadas pelo protótipo HUB75 |
| `robot/gestures.py` | **Os gestos dos braços.** Poses e sequências |
| `config/personalidade.txt` | **Como o robô fala e pensa.** É o system prompt |
| `meus_comandos.py` | Comandos pessoais que ficam disponíveis por voz |

`config/robot.yaml` também pode ser alterado, mas contém limites de velocidade e
segurança. Lara só o muda com um adulto.

### Exemplo de trabalho nos olhos

Enquanto o ecrã final está por decidir, `olhos("feliz")` usa as animações do
mBot2. O protótipo HUB75 lê as expressões de `config/expressoes.yaml`. O editor
`bot-face` está em `/Users/brunosilva/Developer/bot-filter`.

Os parâmetros do browser e do firmware ainda usam escalas diferentes. Não
ensinar a copiar números entre os dois até essa diferença ser corrigida.

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
│   ├── mbot2.py      CyberPi, rodas e sensores por USB
│   ├── motors.py     controlo das rodas através do mBot2
│   ├── pca9685.py    PWM para braços futuros
│   ├── arms.py       os braços (5 servos via PCA9685 @0x41, 50 Hz)
│   ├── eyes.py       a matriz de LED
│   ├── sensors.py    distância e precipício
│   └── power.py      a bateria (ADS1115 @0x48)
├── perception/   captura, deteção e reconhecimento de pessoas no Pi
├── voice/        captura, reprodução e palavra-chave
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
├── expressions.py                                → adaptador das expressões
├── gestures.py                                   → os gestos (edita a Lara)
└── main.py                                       → o ciclo principal
```

### Endereços I2C

| Chip | Endereço | Para quê |
|---|---|---|
| PCA9685 | por definir | Servos dos braços, se forem instalados |
| VL53L1X | `0x29` | Distância a laser |
| ADS1115 | `0x48` | Tensão da bateria |

Os motores não usam I2C. Ficam ligados ao mBot2 Shield e são comandados por
USB. Não comprar um PCA9685 para as rodas.

## Regras da casa

1. **Cada peça de hardware tem um script de teste isolado.** Sem exceções.
2. **As funções que a Lara usa têm nomes em português** e fazem uma coisa só.
3. **Uma falha deve deixar o robô parado.** O watchdog dos motores tem de correr
   fora do ciclo que espera pelo mini. Essa separação ainda é trabalho da etapa
   3. Uma ordem falada depende da transcrição do mini. Um erro explicado ensina
   mais do que um *stack trace*.

---

## Emergência

```bash
sudo systemctl stop robo     # pede ao mBot2 para parar
python scripts/spike_mbot2.py --sem-medir   # o mBot2 responde por USB?
i2cdetect -y 1               # módulos adicionais ligados ao Pi
arecord -l                    # que entradas de áudio existem?
aplay -l                      # que saídas de áudio existem?
rpicam-hello --list-cameras  # a câmara aparece? (imx708)
vcgencmd get_throttled       # 0x0 = alimentação está bem
python scripts/test_power.py # quanta bateria resta
tailscale status | grep mini           # o mini está na rede?
curl http://mini:8420/v1/saude         # o cérebro está de pé?
curl http://mini:11434/api/tags        # e o Ollama por baixo dele?
```

O corte físico de movimento com o mBot2 intacto ainda não está resolvido. O
rocker e o botão que chegam em 5 de setembro só entram nesse circuito depois de
confirmarmos os contactos e os valores nominais. Até lá, cada teste de movimento
é feito com um adulto junto ao robô e com acesso imediato à alimentação do
mBot2. `systemctl stop` não substitui um corte físico se a ligação USB falhar.
