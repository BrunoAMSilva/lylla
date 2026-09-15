# Projeto robô, investigação e plano histórico

**Para Lara, com um adulto. Atualizado em setembro de 2026.**

> Este documento conserva investigação, cálculos e fases de versões anteriores.
> Não o seguir como roteiro de montagem. A arquitetura válida está em
> [`docs/decisoes-atuais.md`](docs/decisoes-atuais.md) e a sequência executável
> está em [`docs/roteiro.md`](docs/roteiro.md).

---

## Índice

1. [Como usar este plano](#1-como-usar-este-plano)
2. [Especificação — o que o robô vai fazer](#2-especificação--o-que-o-robô-vai-fazer)
3. [Arquitetura do sistema](#3-arquitetura-do-sistema)
4. [Decisões técnicas e porquês](#4-decisões-técnicas-e-porquês)
5. [Lista de peças (resumo)](#5-lista-de-peças-resumo)
6. [Alimentação e ligações elétricas](#6-alimentação-e-ligações-elétricas)
7. [Fases históricas](#7-fases-históricas)
8. [Arquitetura do software](#8-arquitetura-do-software)
9. [O que a Lara aprende em cada fase](#9-o-que-a-lara-aprende-em-cada-fase)
10. [Segurança](#10-segurança)
11. [O aspeto — AstroSonda](#11-o-aspeto--astrosonda)
12. [Riscos e planos B](#12-riscos-e-planos-b)
13. [A impressora 3D — investimento futuro](#13-a-impressora-3d--investimento-futuro)
14. [Depois de acabar](#14-depois-de-acabar)

---

## 1. Como usar este plano

Cada fase deve acabar com uma coisa observável a funcionar. A duração depende
dos testes e da chegada das peças. As fases avançam por critérios de pronto, não
por uma contagem fixa de fins de semana.

Cada fase tem esta forma:

| Campo | O que é |
|---|---|
| **Objetivo** | Uma frase. O que existe no fim que não existia no início. |
| **Momento "uau"** | A coisa concreta que a Lara vai querer mostrar a alguém. |
| **A Lara faz** | O que ela executa com as próprias mãos. |
| **O pai faz** | Soldadura, alimentação, decisões de arquitetura, debugging chato. |
| **Critério de pronto** | Um teste objetivo. Passa ou não passa. |

Usamos primeiro o hardware que já existe. Cada peça nova é identificada e
testada sozinha antes de entrar no robô. O inventário mantido está em
[`docs/componentes.md`](docs/componentes.md).

### O que já temos e vamos usar

| Já temos | Onde entra |
|---|---|
| **mBot2 inteiro** | Rodas, encoders, giroscópio, ultrassons, sensor RGB quádruplo e cara temporária |
| **Raspberry Pi 5, câmara e dissipador** | Palavra-chave, controlo do corpo e ligação ao mac mini |
| **Feather M4 CAN Express**, **RP2040 CAN Feather** | Guardados até existir uma necessidade que o mBot2 não cubra |
| **mac mini** | Transcrição, modelo de linguagem e síntese de voz |
| **ESP32 antigo com Micro-USB** | Encontrado. Falta identificar a placa e testar o firmware. Só entra se a experiência escolher HUB75 |

---

## 2. Especificação — o que o robô vai fazer

### 2.1 Requisitos funcionais

| # | Requisito | Como se verifica |
|---|---|---|
| RF1 | **Mover-se** com as duas rodas motorizadas do mBot2 | Anda 1 m, roda 90°, recua |
| RF2 | **Não bater** em obstáculos nem cair da mesa | A 25 cm de uma parede, para sozinho |
| RF3 | **Olhos expressivos** num ecrã | Mostra as 9 expressões escolhidas por Lara |
| RF4 | **Braços** — dois, com ombro e cotovelo, e uma garra | Acena, aponta, pega num lápis |
| RF5 | **Falar** em português de Portugal | Diz uma frase escrita em menos de 1 s |
| RF6 | **Ouvir** — acorda com uma palavra-chave | Diz-se "Olá robô" e os olhos acendem |
| RF7 | **Ser interrompido a meio de uma frase**, numa etapa futura | Fala-se por cima dele e ele para e escuta |
| RF8 | **Transcrever** o que se lhe diz | Diz-se uma frase, aparece escrita |
| RF9 | **Reconhecer caras** e associar a pessoas | Vê a Lara → diz "Olá, Lara!" |
| RF10 | **Conversar** com sentido, usando o LLM na rede local | Responde de forma coerente |
| RF11 | **Obedecer a ordens faladas**, incluindo com os braços | "Acena à avó" → ele acena |
| RF12 | **Saber quanta bateria tem** e avisar | Abaixo de 20%, diz que tem fome |
| **RF13** | **Viver na secretária da Lara** — repara em quem chega, segue com os olhos, entretém-se sozinho | Fica uma hora na mesa sem ninguém lhe tocar e continua a parecer vivo |
| **RF14** | **Nunca falar primeiro** | Uma hora ao lado dela a estudar, zero interrupções |
| **RF15** | **Parar de olhar quando lhe pedirem** | Diz-se "para de olhar" e a câmara desliga-se — sem passar pelo LLM |

O RF7 continua no produto final. Não bloqueia a etapa atual. Primeiro fazemos
uma conversa completa com turnos alternados. Depois medimos eco, leitura
concorrente e cancelamento da reprodução antes de prometer interrupção.

O **RF13** e o **RF14** andam juntos e são o que separa este robô de um brinquedo de
demonstração. Um robô que só reage quando o mandam é um objeto desligado; um que comenta
sozinho de cinco em cinco minutos é uma interrupção ao lado de quem está a estudar. A
regra é: **reage sempre com a cara, fala só quando chamado.** Ver D16.

### 2.2 Requisitos não-funcionais

| # | Requisito | Alvo |
|---|---|---|
| RNF1 | **Privacidade** — nenhum áudio ou imagem sai de casa | 0 pedidos à Internet |
| RNF2 | **Autonomia** de bateria | ≥ 3 horas de brincadeira |
| RNF3 | **Uma só bateria**, um só carregador, um só interruptor | Verdadeiro |
| RNF4 | **Latência** de resposta falada | ≤ 8 s (a transcrição é o gargalo — §3.2) |
| RNF5 | **Segurança elétrica** | Química LiFePO4, fusíveis, botão de emergência |
| RNF6 | **Arranque automático** | Liga-se o interruptor → funciona sem teclado |
| RNF7 | **A Lara consegue mudar coisas sozinha** | Muda uma frase, expressão ou gesto |
| RNF8 | **Tamanho** — grande o suficiente para tudo caber com folga | ~35–40 cm de altura |

### 2.3 O que este robô **não** vai fazer (âmbito fechado)

- Não sobe escadas nem anda na rua.
- Usa os encoders e o giroscópio que já existem no mBot2.
- Seguir pessoas, mapear a casa e jogar às escondidas são trabalho avançado.
- Os braços não levantam nada acima de cerca de 150 g.

---

## 3. Arquitetura do sistema

```
┌───────────────────────────────────────────────────────────────────────┐
│                        REDE WI-FI DE CASA                             │
│  ┌──────────────────┐              ┌───────────────────────────────┐  │
│  │  mac mini        │              │  ROBÔ, Raspberry Pi 5         │  │
│  │  ──────────────  │◄────────────►│  ───────────────────────      │  │
│  │  transcrição     │ áudio e      │  wakeword · câmara e caras    │  │
│  │  LLM · voz       │ comandos     │  sensores · comandos locais   │  │
│  │                  │              │  mBot2 intacto por USB        │  │
│  └──────────────────┘              └───────────────────────────────┘  │
│                          ↑                                            │
│              Nada disto sai para a Internet                           │
└───────────────────────────────────────────────────────────────────────┘

                    DENTRO DO ROBÔ
   ┌──────────────────────────────────────────────────────────┐
   │  LiFePO4 4S 12,8 V ──► fusível ──► interruptor           │
   │        │                                                 │
   │        ├──► 5 V ──► Raspberry Pi 5                       │
   │        ├──► alimentação dos braços, se forem instalados   │
   │        └──► alimentação do mBot2 intacto                  │
   │                                                          │
   │  Pi ──USB──► CyberPi + mBot2 Shield                       │
   │      │        ├──► motores e encoders                     │
   │      │        ├──► giroscópio e ultrassons                │
   │      │        └──► sensor RGB quádruplo                   │
   │      ├──► entrada e saída de áudio, por decidir           │
   │      ├──► ecrã HUB75 ou OLED, por decidir                 │
   │      ──CSI──► Camera Module 3                            │
   └──────────────────────────────────────────────────────────┘
```

Três microfones, um MAX98357A e uma coluna chegam em 5 de setembro. A cadeia de
áudio só é escolhida depois de identificar e medir essas peças.

### 3.1 Porquê esta divisão

O Pi trata de I/O e das decisões que não podem depender da rede. Também executa
a palavra-chave, YuNet e SFace. O mac mini executa a transcrição, o modelo de
linguagem e a síntese de voz.

- Olhos, rodas, braços e sensores correm no Pi. O watchdog dos motores deve ser
  separado do ciclo que espera pela rede na etapa 3 do roteiro ativo.
- `Pára` e `não olhes para mim` não passam pelo LLM, mas uma ordem falada
  precisa da transcrição do mini.
- Áudio e imagem ficam na rede de casa.
- Se o mac mini estiver desligado, o robô não transcreve nem responde com o
  modelo. Continua a reconhecer pessoas. A paragem independente ainda precisa
  do watchdog e do controlo físico previstos no roteiro ativo.

### 3.2 O ciclo de vida de uma interação

```
1. O Pi deteta "Olá Lylla" com openWakeWord.
2. O Pi abre o turno e envia o pré-rolo e o áudio ao mac mini.
3. O mac mini transcreve com Parakeet.
4. O Pi deteta e reconhece as pessoas que vê.
5. O modelo produz a resposta e as ações permitidas.
6. O mac mini sintetiza a voz e devolve áudio, expressão e ações.
7. O Pi reproduz o áudio e executa as ações locais.
```

Primeiro medimos este turno sem interrupção. O RF7 precisa de captura durante a
reprodução, tratamento de eco e uma forma de cancelar o áudio que está a tocar.

---

## 4. Decisões técnicas e porquês

### D1 · Papel do Raspberry Pi

O Raspberry Pi 5 controla o corpo, captura áudio e imagem e executa a
palavra-chave. YuNet e SFace também correm no Pi. O mac mini executa a
transcrição, o modelo de linguagem e a síntese de voz.

### D2 · A cara continua por decidir

Há duas opções reais. O HUB75 64x32 usa o ESP32, o firmware e o protocolo que
já existem neste repositório. Um OLED pode mostrar formas mais suaves, texto e
gráficos com mais detalhe.

O POC `bot-face` está em `/Users/brunosilva/Developer/bot-filter`. Produz uma
grelha lógica e apresenta-a com WebGL. Num OLED HDMI ou DSI pode correr num
browser em modo quiosque. Num OLED SPI ou I2C precisa de outro renderizador e de
um controlador para o ecrã escolhido.

A escolha depende do OLED concreto. Precisamos do tamanho, resolução, interface,
cor, brilho, consumo e preço. Também é preciso medir o custo de um ambiente
gráfico no Pi enquanto o openWakeWord corre.

Até essa experiência terminar:

- os LEDs do mBot2 são a cara temporária
- o backend HUB75 continua como protótipo funcional
- nenhum recorte do corpo depende do tamanho do ecrã
- a API `expressao()`, `olhar_para()` e `animar()` permanece estável

Os parâmetros do `bot-face` e do firmware HUB75 ainda usam escalas diferentes.
Copiar valores diretamente entre os dois não é uma instrução válida. A
experiência e os critérios de escolha estão em `docs/decisoes-atuais.md`.

### D14 · Soldadura

O ferro e os materiais já chegaram. A primeira sessão serve para identificar o
equipamento, ventilar a bancada e praticar numa placa sem ligação ao robô.

O MAX98357A e o pente de 40 pinos podem exigir soldadura. Isso só se confirma
quando as peças forem abertas. O mBot2 não exige qualquer corte ou alteração.

O percurso de potência só é montado depois de confirmar a tensão e a corrente
nominais dos interruptores, dos cabos e de cada carga. O inventário está em
`docs/componentes.md`.

### D3 · Motores através do mBot2 intacto

O POC confirmou que o Raspberry Pi consegue controlar o CyberPi e o mBot2
Shield por USB. O mBot2 fica montado. Não se cortam cabos e não se substitui o
controlador dos motores.

Esta opção conserva capacidades que já estão pagas e testadas:

- controlo conjunto das duas rodas
- velocidade em malha fechada no shield
- encoders contados pelo próprio hardware
- giroscópio do CyberPi
- sensor ultrassónico
- sensor RGB quádruplo virado para o chão.

O driver em `robot/hardware/mbot2.py` subscreve os valores que mudam muitas
vezes. As medições do POC mostraram que o envio de comandos é suficientemente
rápido para esta fase.

Uma paragem de emergência não deve depender apenas desta ligação USB. A forma
de cortar o movimento com o mBot2 intacto ainda precisa de um teste elétrico
com os interruptores que chegam em 5 de setembro.

O TB6612 e o PCA9685 de motores deixam de fazer parte da construção. Um
PCA9685 pode ser usado mais tarde para os servos dos braços.

### D4 · Reconhecimento de pessoas no Raspberry Pi

YuNet encontra os rostos e SFace produz a assinatura usada para reconhecer uma
pessoa. Os dois modelos correm no Pi. As imagens e assinaturas não precisam de
ser enviadas ao mac mini.

O limiar oficial do OpenCV é 0,363 de **semelhança de cosseno**; subimos para **0,45**,
porque num robô de família é muito pior chamar "Lara" a uma visita do que dizer "não te
conheço" à Lara.

### D4b · Câmara: **Camera Module 3, e porquê não a de infravermelhos**

Existe uma alternativa tentadora: uma OV5647 de 5 MP com foco ajustável e dois
iluminadores IR, por **€21,90** em vez de €32,80. Faz visão noturna. Para este robô é
pior, e vale a pena perceber porquê — a razão é bonita.

**1 · Para os infravermelhos servirem, o sensor tem de deixar entrar infravermelhos.**
As câmaras normais têm um filtro de corte de IR colado à frente do sensor, precisamente
para que a luz que os nossos olhos não veem não estrague as cores. Uma câmara de visão
noturna não tem esse filtro (é o que se chama *NoIR*). O preço paga-se de dia: o sol e as
lâmpadas incandescentes emitem muito IR, esse IR entra nos três canais do sensor, e a pele
fica cerosa, o verde das plantas fica esbranquiçado, o azul-escuro fica arroxeado. O
balanço de brancos automático não corrige isto, porque não é um problema de temperatura de
cor — é uma **quarta banda espetral a somar-se às três**.

**2 · O SFace nunca viu uma cara iluminada a infravermelhos.** O modelo que escolhemos
(D4) foi treinado com fotografias de luz visível. Uma cara iluminada só por IR produz uma
assinatura de 128 números que cai noutra zona do espaço — é o problema **NIR-VIS** da
literatura de reconhecimento facial, tão real que existem conjuntos de dados dedicados
(CASIA NIR-VIS 2.0) e modelos dedicados só para ele. Na prática: a Lara registava-se de
dia, e à noite o robô deixava de a reconhecer. Registar as duas versões dá o dobro do
trabalho e um resultado mais ruidoso.

**3 · Foco manual.** Aperta-se um parafuso e fica assim. Com f/1.8 e 3,6 mm a
profundidade de campo é grande — fixando na hiperfocal, de ~1,2 m até ao infinito fica
nítido — por isso a 1–3 m aguenta-se. Perde-se é o caso em que uma criança se encosta ao
robô a 40 cm para falar com ele, que é exatamente o caso que mais acontece. O autofoco da
Camera Module 3 refoca sozinho, imagem a imagem.

**4 · Os LED de 850 nm brilham vermelho.** Não é IR puro: vê-se um ponto vermelho-escuro.
Dois pontos vermelhos permanentemente acesos no faceplate preto de um robô branco e azul —
e no vocabulário visual do Astro, vermelho é inimigo (§11.2). Podem-se deixar as placas de
LED por ligar, mas aí paga-se o sensor sem filtro e não se leva a visão noturna.

**O que fazemos.** Camera Module 3 agora. E fica registado que o **Pi 5 tem duas entradas
CSI**: se um dia a Lara quiser "modo noturno", a câmara IR entra na segunda entrada como
segunda câmara, sem substituir nada e sem estragar o reconhecimento de dia. Está na
secção 14.

#### Três alternativas da Amazon, avaliadas

| Módulo | Preço | Entrega em PT | Veredicto |
|---|---|---|---|
| **Camera Module 3 76°** (Botnroll) | €32,80 + €4,50 cabo | ✅ imediata | **É esta.** Oficial, autofoco PDAF, tuning da Raspberry Pi |
| InnoMaker IMX415 4K STARVIS | €31,00 (2 cabos incluídos) | ✅ | **Plano B.** Melhor sensor de pouca luz, mas **sem autofoco** |
| Arducam "Camera Module 3" B0312 | €33,52 | ❌ | Não é o módulo oficial, apesar do nome. Mais caro que o oficial |
| InnoMaker IMX708 autofoco | €48,36 | ❌ | Mesmo sensor, €15 mais caro, 29% de avaliações de 1–2 estrelas |

Duas das três nem sequer entregam em Portugal — são vendidas pela Amazon do Reino Unido e
dos EUA. Fica a terceira, a IMX415, e essa merece uma linha honesta: **é um sensor melhor
do que o nosso**. É um Sony STARVIS retroiluminado, chega a 0,01 lux, traz os dois cabos e
custa menos €6 no total. Se o robô vivesse numa sala mal iluminada, seria a escolha certa.

Não é, por três razões. **Não tem autofoco** — foca-se uma vez com um parafuso, e a
distância que mais interessa é a criança encostada ao robô. O sensor da Camera Module 3 é
igualmente retroiluminado e até **maior** (7,4 mm de diagonal contra 6,4 mm), com píxeis do
mesmo tamanho — a vantagem real de pouca luz é bem menor do que a folha de especificações
sugere. E num Raspberry Pi o **ficheiro de tuning** conta tanto como o sensor: exposição
automática, balanço de brancos e redução de ruído da Camera Module 3 foram afinados pela
própria equipa da Raspberry Pi, e isso vê-se mais do que 0,01 lux numa tabela.

Fica como plano B a sério: se o Botnroll ficar sem stock, a IMX415 resolve, custa menos, e
só é preciso acrescentar `dtoverlay=imx415` ao `config.txt`.


### D5 · Falar: **a voz Joana, do macOS, servida pelo Mac**

*Revisto em agosto de 2026, depois de a Lara ouvir. A decisão anterior — Piper com a voz
`pt_PT-tugão-medium`, no Pi — está errada e fica aqui registada por baixo.*

**O que se ouviu.** A `tugão` percebe-se mal e diz palavras que não estão escritas. Não é
configuração: o cartão do modelo diz que foi **afinada a partir da voz inglesa `lessac`** e
treinada com **~1,5 h** de um só falante, gravadas *pelo browser* em WEBM, e — textualmente
— *"no post-processing or validation applied to text or audio"*. São duas avarias
diferentes: o som pastoso é falta de dados; as palavras trocadas são o fonemizador (o
espeak-ng tem um G2P fraco para pt-PT) mais a ausência de normalização de texto.

**O teste.** `scripts/testar_vozes.py` gera a mesma frase — com números lá dentro, de
propósito — em oito vozes e toca-as **por ordem aleatória, sem dizer qual é qual**. A Lara
ouviu as cinco vozes pt-PT dos modelos abertos (`tugão`, e as `miro`/`dii` do OpenVoiceOS,
estas já com o fonemizador **`tugaphone`**, feito de propósito para português) e as três do
macOS. Escolheu a **Joana**, e não foi por pouco. *Quem manda são os ouvidos dela.*

**A consequência.** A Joana não é um ficheiro que se copie: é uma voz do sistema, só existe
no macOS. Logo a síntese muda-se para o Mac (`scripts/servidor_voz.py`, HTTP, biblioteca
padrão do Python, sem dependências) e o Pi só pede o WAV e toca-o — **pelo reSpeaker**,
que é a placa de som do robô (ver D6: é o que faz o cancelamento de eco funcionar).

**Isto não custa independência ao robô, e é o ponto todo:** o cérebro grande já vive no Mac
(D8). Sem Mac não há frases *novas* para dizer. E as frases que o robô diz por iniciativa
própria — bateria fraca, "não te percebi", a saudação, o modo offline da fase 14 — são um
conjunto **fechado**, que fica em cache no disco do Pi (`data/voz/`) depois de sair uma
vez. Com o Mac desligado, o robô continua a falar com a voz da Joana. A cache é consultada
**antes** da rede, e é isso que os testes em `tests/test_voz_mac.py` protegem.

**O motor é substituível de propósito.** O serviço recebe texto e devolve um WAV; trocar a
Joana por um modelo neuronal no Mac é acrescentar uma função ao dicionário `MOTORES`. O Pi
não precisa de saber. O candidato à espera é a **Chatterbox Multilingual v3** (junho 2026),
que tem um modelo `pt-pt` dedicado e licença MIT — mas são 2 GB e a latência em Apple
Silicon ainda não está medida.

**Rejeitados:** `tugão`/Piper (acima — fica como recurso opcional, `voz.modelo_tts`, vazio
por omissão); eSpeak-NG (som robótico — último recurso); **Kokoro** (só português do
Brasil, e o `misaki` nem tem módulo de português: cai para o espeak `pt-br`); XTTS-v2 (o
único fine-tune pt-PT que existe reduz de propósito o peso do alinhamento de texto — é
exatamente a avaria que estamos a fugir); vozes da Siri (não são acessíveis a programas).

Um robô com sotaque brasileiro a falar com uma criança portuguesa continua a ser engraçado
durante dez minutos — esse critério não mudou, só a resposta.

### D6 · Ouvir: **reSpeaker XVF3800 — 4 microfones com DSP em hardware**

> **Investigação histórica.** O reSpeaker não é a escolha atual. Chegam três
> microfones, um MAX98357A e uma coluna de 3 W em 5 de setembro. Primeiro
> identificamos essas peças e fazemos um turno de áudio alternado. A
> interrupção durante a fala fica para uma etapa posterior.

Esta foi a pergunta mais afiada da revisão, e a resposta mudou o desenho.

**Vários microfones só ajudam se alguma coisa fizer *beamforming*.** E o ganho é modesto:
um *delay-and-sum* dá no máximo 10·log₁₀(N) dB — **2 mics ≈ 3 dB, 4 ≈ 6 dB**. Dois
microfones espetados no Pi sem DSP são *piores* do que um microfone bom.

**Mas para um robô que fala, o que interessa não é o beamforming — é o AEC**
(cancelamento de eco acústico). E aqui está o ponto que muita gente confunde: **o AEC não
precisa de vários microfones.** Precisa do sinal de referência (o que o altifalante está a
tocar). É matematicamente um problema mono.

Fazer AEC em software no Pi não funciona bem: o WebRTC AEC falha a SNR alto, o Speex dá
"atenuação, não cancelamento", e o *clock drift* entre a placa de saída I2S e a de entrada
USB arruína qualquer algoritmo. Em hardware, o XMOS dá cancelamento quase perfeito.

**Escolha: reSpeaker XVF3800, ~€60.** Quatro microfones, e no próprio chip: AEC,
beamforming, deteção de direção, supressão de ruído e AGC. Aparece no Linux como **áudio
USB standard (UAC 2.0) — zero drivers**. É o mesmo silício que a Pollen Robotics validou
em produção no Reachy Mini.

**A coluna liga-se ao reSpeaker, não ao Pi — e isto decide a compra.** *(Correção de 25
de agosto de 2026; a versão anterior deste plano punha um amplificador I2S MAX98357A no
Pi, e estava errada.)* O parágrafo acima diz que o AEC precisa do sinal de referência. A
documentação da XMOS diz de onde ele vem em modo USB: *"the USB host provides the
reference signal"* — o Pi manda o áudio **para o reSpeaker por USB**, o chip usa-o como
referência e é ele que o toca. Um amplificador pendurado no I2S do Pi tocaria *ao lado* do
XVF3800, o chip ficaria sem referência, e os €60 que justificámos pelo AEC não serviam
para nada.

Na prática fica mais simples, não mais complicado:

- A placa tem uma **saída de coluna amplificada, ficha JST PH 2.0** (até 5 W) e um jack de
  3,5 mm. A coluna da Botnroll (DFRobot, 3 W, 8 Ω, caixa fechada, cabo de 42 cm com ficha
  JST PH 2.0, €4,95) encaixa diretamente.
- **Sem soldar nada** na fase 2, sem `dtparam=i2s`, sem `dtoverlay=hifiberry-dac`. O Pi
  vê o reSpeaker como uma placa de som USB vulgar: `aplay -l` mostra
  `card N: Array [reSpeaker XVF3800 4-Mic Array]`. Duas linhas em `/etc/asound.conf`
  (Apêndice B) tornam-no a placa por omissão, e o `aplay` do `speak.py` e o
  `sounddevice` do `listen.py` passam a usá-lo sem tocar no código.
- Os GPIO 18, 19 e 21 (que eram o I2S) ficam **livres**.
- O reSpeaker passa da encomenda 4 para a **encomenda 1** — são os mesmos €60, gastos
  antes. Não existe em loja portuguesa; ver *Onde comprar*.

⚠️ **A sua alimentação vem da porta USB do Pi**, com o amplificador da coluna e os 12
LEDs RGB incluídos. Com a fonte oficial não há problema; na bateria (fase 5) é mais uma
razão para o `usb_max_current_enable=1` de §6.2 — e para manter os LEDs do reSpeaker
fracos ou apagados.

**Rejeitados, e porquê:**

- **ReSpeaker 2/4/6-Mic Pi HAT** — é o que aparece em todos os tutoriais, mas o driver
  `seeed-voicecard` lista Pi 3, Pi 4 e Zero; **o Pi 5 não aparece**. A imagem
  pré-construída é de 2021 e há uma issue aberta desde 2022 por falha de compilação em
  kernels ≥5.15. Projeto abandonado.
- **Microfones MEMS I2S soltos** (INMP441, SPH0645) — o Pi 5 mudou o I2S para o RP1 e há
  problemas abertos. E mesmo funcionando, ficam 2 microfones crus sem AEC nenhum: o pior
  dos dois mundos por €15.
- **Speakerphone USB de conferência** — tem AEC e, tal como o reSpeaker, obriga a passar
  todo o áudio do robô por ele. A diferença é que o altifalante está *dentro* da caixa —
  não se escolhe onde fica nem qual é. No reSpeaker a coluna vem por um cabo de 42 cm e
  monta-se onde o design acústico mandar.

**Plano B a €25:** reSpeaker Lite (2 mics, XU316). Tem AEC — que é o que importa — mas não
tem beamforming nem DOA.

⚠️ **O ruído dos motores não é resolvido por nada disto.** Não há sinal de referência
(logo, o AEC não se aplica) e estão em campo próximo (logo, o beamformer não os anula). A
solução é **mecânica**: montar o microfone no topo, longe dos motores, e **não andar
enquanto ouve**. Isto está no código.

### D7 · Palavra-chave no Pi, transcrição no mac mini

O openWakeWord corre no Pi e está sempre à espera de "Olá Lylla". O áudio só é
enviado para transcrição depois dessa deteção. O pré-rolo evita perder o início
da frase.

O mac mini transcreve com Parakeet. Não se instala Whisper no Pi. A comparação
entre modelos e as medições vivem em `docs/AI-config.md`.

Nesta etapa, Lylla ouve depois de acabar de falar. A interrupção durante a
reprodução continua planeada e terá uma experiência própria de eco, captura
concorrente e cancelamento do áudio.

### D8 · Cérebro grande: **Ollama no Mac com `gemma4:12b`**

**Modelo escolhido pelo *tool calling*, não pelo português.** Para o robô obedecer a
"acena à avó", o modelo tem de devolver uma chamada de função em JSON bem formado, de
forma fiável. Medições de 2026 dão ao Gemma 4 cerca de **90%**, contra ~30% do Mistral
Nemo e ~40% do Phi-4. Um robô que obedece a 3 em cada 10 ordens é um brinquedo partido.

**Menção honrosa: AMÁLIA.** Existe desde julho de 2026 um LLM aberto **feito para
português europeu** — `amalia-llm/AMALIA-9B-0626-DPO`, Apache 2.0, treinado com o
Arquivo.pt, de um consórcio nacional. Bate o Llama 3.1-8B e o Gemma 3-12B nos exames em
português. **Mas o model card não documenta tool calling** — fica como opção para o modo
conversa puro.

Ferramentas expostas (poucas, com opções fechadas — acima de 6–8 os modelos pequenos
baralham-se): ver `robot/brain/tools.py`.

### D8b · Acelerador de IA (TPU/NPU): **não, e a razão não é o preço**

> **Investigação histórica.** As estimativas abaixo avaliam aceleradores para o
> Pi. O destino atual mantém YuNet e SFace no Pi. STT, LLM e TTS correm no mac
> mini.
> O Pi fica com a palavra-chave, captura, encaminhamento e controlo local.

A pergunta certa é *que problema é que isto resolve*. No nosso robô, nenhum dos dois que
existem.

**Para reconhecer caras não é preciso.** O YuNet demora 2–3 ms e o SFace 25–35 ms por
imagem no CPU do Pi 5 — 15 a 25 imagens por segundo com 4 a 6 caras conhecidas. O robô
precisa de 2 a 5 por segundo para dizer *"Olá, Lara!"* sem parecer lento. Já estamos cinco
vezes acima do necessário. Um acelerador levava os 30 ms a 5 ms, e ninguém notava. Pior:
os modelos teriam de ser recompilados para o formato HEF da Hailo, o que significa refazer
a perceção toda no SDK deles em vez de duas linhas de OpenCV.

**Para voz, depende de qual.** E aqui vale a pena separar, porque são coisas diferentes
com o mesmo nome:

| | Memória própria | O que corre | Preço |
|---|---|---|---|
| Coral USB (Edge TPU) | 8 MB SRAM | Só visão int8. **Projeto morto** — Google arquivou o repo em abril/2026 | — |
| AI HAT+ 13/26 TOPS (Hailo-8L/8) | nenhuma | Só visão. A própria Raspberry Pi diz que **não** faz IA generativa | €130 |
| **AI HAT+ 2 · 40 TOPS (Hailo-10H)** | **8 GB LPDDR4X** | LLM, VLM e Whisper no próprio Pi | ~€220 |

Só o terceiro responde à pergunta. E responde mal, por três razões:

**1 · Só cabe um modelo de cada vez.** É a limitação que decide tudo. No fórum da Hailo:
*"you can't have 2 models running at the same time you have to switch between the two"*.
Ou seja: descarregar o Whisper → carregar o LLM → responder → descarregar → recarregar o
Whisper, a cada frase. Num robô que conversa, é exatamente a forma errada.

**2 · O CPU do Pi 5 é mais rápido a gerar texto.** O Jeff Geerling mediu os dois e
escreveu que o CPU do Pi *"trounces"* o Hailo-10H, com o veredicto *"a solution in search
of a problem"*. Desistiu do exemplo de visão e LLM ao mesmo tempo porque rebentava com
*segmentation fault*.

**3 · Os modelos são pequenos.** 1 a 1,5 mil milhões de parâmetros (Llama3.2, Qwen2.5,
DeepSeek-R1-Distill) contra os 12 mil milhões do `gemma4:12b` que corre no Mac. Escolhemos
esse pela fiabilidade a chamar ferramentas (~90%); um modelo oito vezes mais pequeno, em
português europeu, a decidir quando andar e quando levantar o braço, não é aposta para um
projeto de uma criança. E tool calling nem sequer está documentado na stack da Hailo.

**O Pi não precisa de um acelerador para a conversa.** A transcrição, o modelo
de linguagem e a síntese de voz correm no mac mini. O Pi envia o áudio e
reproduz o WAV devolvido, com frases frequentes guardadas em cache. YuNet e
SFace já cabem no CPU do Pi. Um acelerador acrescentaria custo sem retirar do
Pi uma carga que pertença à arquitetura atual.

**Quando reabrir isto:** no dia em que o robô tiver de funcionar longe de casa — levá-lo à
escola, mostrá-lo a um amigo. Aí a alternativa mais barata e mais simples é a que o próprio
Geerling aponta: um Pi 5 de 16 GB, sem placa nenhuma. Está na secção 14.

#### E a energia? A pergunta certa, e a resposta que surpreende

Um acelerador gasta **muito menos energia por inferência** que um CPU. Isso é verdade e é
a verdadeira razão de existirem. A conta, com números grosseiros mas honestos:

- um modelo que demora **500 ms** no CPU, com o CPU a puxar +7 W acima do repouso → **3,5 J**
- o mesmo modelo em **50 ms** no Hailo, a 2,5 W → **0,125 J**

Vinte e oito vezes menos energia para o mesmo trabalho. Num datacenter, ou numa câmara
alimentada a solar que analisa vídeo o dia todo, isso decide tudo.

**No nosso robô a conta inverte-se, e por um motivo só: o acelerador também gasta quando
não está a fazer nada.** O Hailo-8 fica em ~2,5 W em repouso. E o nosso robô é alimentado
a bateria.

| | |
|---|---|
| Bateria LiFePO4 4S ~6 Ah | **76,8 Wh** |
| Consumo médio estimado do robô | ~14 W |
| Autonomia | **~5 horas** |
| Com o acelerador (+2,5 W sempre) | ~4,2 horas — **menos 50 minutos** |

E o que é que se poupava? O SFace demora ~30 ms. A cinco reconhecimentos por segundo são
150 ms de um núcleo por segundo, ou seja **15% de um núcleo**. Um núcleo A76 a 100% custa
cerca de 1,75 W no Pi 5. Portanto o reconhecimento de caras custa-nos, em média,
**~0,25 W**.

> Pagar **2,5 W sempre** para poupar **0,25 W às vezes**. Dez vezes pior.

Ligado à ficha seria indiferente. A bateria, é perda direta. E há ainda um detalhe que
raramente aparece nos vídeos: o acelerador **não elimina o trabalho do CPU**, só a parte da
rede neuronal. A captura da imagem, a conversão de cor, o recorte e o pós-processamento
continuam no CPU.

#### Porque é que os vídeos mostram 2 FPS

Porque medem **outro modelo**, muito mais pesado. O `face_recognition` (dlib), que é o que
aparece em todos os tutoriais e que nós rejeitámos no D4, corre a **~0,6 FPS** num
Raspberry Pi. Um YOLOv8n a 640×640 tem **3,2 milhões de parâmetros**. O YuNet tem
**75 856** — quarenta e duas vezes menos, e o artigo dele chama-lhe literalmente *"a tiny
millisecond-level face detector"*.

Nos testes oficiais do OpenCV, num Raspberry Pi **4B** (o Pi 5 é 2 a 3 vezes mais rápido):

| Modelo | Resolução | Pi 4B | Pi 5 (estimado) |
|---|---|---|---|
| YuNet — encontrar caras | 160×120 | 6,23 ms | ~2–3 ms |
| SFace — identificar quem é | 150×150 | 68,82 ms | ~25–35 ms |

O acelerador dá um ganho de ~10× no modelo pesado. Nós ganhámos 50 a 100× ao **escolher o
modelo certo** — de graça, e sem placa nenhuma. É a mesma lição da secção D2b: o truque
quase nunca é pôr mais hardware, é pôr o trabalho no sítio certo.

⚠️ Uma honestidade: estes números são a 160×120 e 150×150. Nós processamos a 640×480, e o
YuNet cresce mais ou menos com o número de píxeis. **Medir isto é uma tarefa da fase 9** —
e é uma boa experiência para a Lara fazer: correr o detetor a três resoluções, cronometrar,
e desenhar o gráfico. Se ficar lento, a resposta certa continua a não ser comprar uma
placa: é detetar em 320×240 e recortar a cara da imagem grande.

#### ⚠️ Correção: a visão passou mesmo a ser contínua

A primeira versão desta secção acabava a dizer que o robô "olha para uma cara durante um
segundo quando alguém entra na sala". Deixou de ser verdade: o robô vive na secretária da
Lara e olha o tempo todo (D16). Vale a pena refazer a conta em vez de a apagar, porque o
resultado é interessante.

| | Fatia de um núcleo |
|---|---|
| Detetar caras (YuNet), 320×240, 10x/s | ~10% |
| Reconhecer (SFace), só quando muda ou de 4 em 4 s | ~1% |
| Captura da imagem e conversão de cor | ~10-15% |
| **Total** | **~25% de UM núcleo de quatro** ≈ **0,45 W** |

Ou seja: **contínuo, e mesmo assim cinco vezes menos do que os 2,5 W que um Hailo gasta
parado.** A conclusão não se inverte.

A razão é a que abre este plano todo: **as duas perguntas têm preços diferentes.**
"Está aqui alguém, e onde?" custa 2-3 ms e é a que precisa de correr 10 vezes por segundo,
porque é ela que faz os olhos seguirem a pessoa. "Quem é?" custa 30 ms e só precisa de
correr quando alguém chega, ou de 4 em 4 segundos para confirmar. Fazer as duas a 10 fps
custaria ~35% de um núcleo; fazendo assim, fica em ~12% mais a captura.

Isso não é uma otimização esperta — é a diferença entre perceber o problema e não perceber.
E é exatamente o que os vídeos de aceleradores não fazem, porque o objetivo deles é mostrar
o antes e o depois com o mesmo modelo.

**Quando é que eu mudaria mesmo de ideias:** se o robô precisasse de perceber a *cena* e
não só as caras — descrever o que vê, encontrar objetos, seguir a Lara pela casa a
desviar-se de coisas. Aí seria um detetor a sério (YOLO ou um VLM) em todas as imagens, o
CPU ficava preso, e a conta invertia-se de vez. Não é o que o RF13 pede.

Medir isto no robô real: `python scripts/test_companion.py --custo`, que dá o resultado
em watts e o compara com os 2,5 W da placa.


### D16 · Modo secretária: **é aqui que o robô vive**

O robô não é uma demonstração que se liga ao fim-de-semana. Fica em cima da secretária da
Lara, ligado, enquanto ela estuda. Isso muda coisas concretas.

**As referências são o EMO, o Eilik e o Looi.** Vale a pena olhar para o que cada um faz:

| | Câmara | Reconhece caras | Fala primeiro | Bateria |
|---|---|---|---|---|
| **EMO** (living.ai) | sim, grande angular | sim, até 10 pessoas | não — precisa da palavra "EMO" | base de carga sem fios, volta lá sozinho |
| **Eilik** (Energize Lab) | **nenhuma** | não | não | 1,5 h |
| **O nosso** | Camera Module 3 | sim, 4-6 pessoas | não | ~5 h, ou ligado à ficha |

O **Eilik não tem câmara nenhuma** — e é o que as pessoas descrevem como mais vivo dos
três. Tem três sensores de toque, expressões, e coisas que faz sozinho quando ninguém lhe
liga: lê, pesca, faz exercício. A conclusão é desconfortável e importante: **a sensação de
estar vivo não vem de reconhecer caras. Vem de reagir sempre e de ter que fazer.** O
reconhecimento é o que torna a reação *pessoal* — é o bónus, não a base.

Também vale a pena reparar que o **EMO exige a palavra "EMO"** antes de responder. O robô
de secretária mais bem resolvido do mercado não escuta em contínuo.

**As quatro regras.**

**1 · Reage sempre, fala só quando chamado.** Quando alguém aparece, os olhos seguem-no.
Se for a Lara, faz o coração e acena. Mas não diz nada. Falar exige "Olá robô". Vive na
mesa onde ela estuda; um robô que comenta sozinho deixa de ser companhia e passa a ser
interrupção. E cumprimentar tem 15 minutos de arrefecimento — levantar-se para ir buscar
água não devia dar um "olá" novo.

**2 · Ao fim de 90 s sozinho, arranja que fazer.** Boceja, espreita à volta, espreguiça-se,
distrai-se, dá uma voltinha. É a parte do Eilik, e é a que faz a diferença entre um robô e
um enfeite. Vive em `robot/brain/companion.py`, na tupla `ATIVIDADES` — a Lara acrescenta
as dela lá.

**3 · Na secretária anda a 25%, e o limite vive no sítio certo.** Uma secretária tem 75 cm
de altura e arestas a menos de meio metro em qualquer direção. A velocidade normal do chão
atravessa uma mesa em menos de dois segundos, e os sensores de precipício, a 10 leituras
por segundo, não travam a tempo.

> O teto não está na função que anda. Está no `_limitar()` dos motores, por onde passa
> **obrigatoriamente** todo o movimento — incluindo o que o LLM mandar fazer.
> `motors.modo("secretaria")` é chamado no arranque, antes de qualquer movimento ser
> possível. E as atividades ociosas **só rodam no sítio**, nunca andam em frente: rodar
> não pode cair de lado nenhum.

**4 · O pedido para desligar a câmara não passa pelo LLM.** A frase *"para de
olhar"* é comparada no Pi, em `robot/brain/comandos_diretos.py`, antes de o
modelo a receber. O mesmo acontece com `pára`. Isto evita depender da escolha
de ferramenta do LLM. Não evita a dependência da transcrição no mini. Com a
rede em baixo, estas frases não são entendidas e a paragem tem de vir do
timeout ou de um controlo local.

#### O que isto custa em CPU

Este é o número que decide se faz sentido um acelerador (D8b), agora que a visão passou a
ser contínua:

| | |
|---|---|
| Detetar caras (YuNet), 320×240, 10x/s | ~10% de um núcleo |
| Reconhecer (SFace), só quando muda ou de 4 em 4 s | ~1% de um núcleo |
| Captura e conversão de cor | ~10-15% de um núcleo |
| **Total** | **~25% de UM núcleo de quatro** ≈ **0,45 W** |

Continua a ser cinco vezes menos do que os 2,5 W que um Hailo gasta **parado**. A conta do
D8b não se inverte com a visão contínua, e a razão é que a pergunta cara ("quem é?") não
precisa de correr a 10 fps — só a barata ("está aqui alguém, e onde?").

O `python scripts/test_companion.py --custo` mede isto no robô real e diz o resultado em
watts. É uma boa experiência para fazer com a Lara depois da fase 9.

#### O que muda no hardware

- **Sensores de precipício passam de "bom ter" a críticos.** Já estão no plano (GPIO 17,
  22, 27). Passam a ser a primeira coisa a testar em cada sessão, e há um teste que se
  recusa a dar luz verde se o `verificar_precipicio` estiver desligado.
- **Três sensores de toque (~€6).** É a peça com melhor relação entre custo e efeito de
  todo o projeto — o Eilik constrói a personalidade toda em cima de três. Módulos TTP223
  já com pinos soldados, em GPIO 4, 16 e 26 (livres). Cabeça, costas e frente.
- **Ficha na mesa.** Em modo secretária o robô está ligado à corrente; a bateria é para
  quando desce ao chão. ⚠️ Isto exige um **BMS de porta comum** no pack LiFePO4 — um BMS
  de porta separada não deixa carregar e descarregar ao mesmo tempo. Confirmar antes de
  comprar.
- **Ruído da ventoinha.** Um Pi 5 a fazer visão contínua ao lado de quem estuda. Os 10 fps
  a 320×240 foram escolhidos também por isto. Medir com `vcgencmd measure_temp` na fase 9:
  se ficar abaixo dos 60 °C, a ventoinha quase não acelera.

### D17 · Seguir a Lara pela casa: **o controlador é fácil, o problema são as escadas**

A Lara pediu que o robô a siga pela casa. É um pedido simples de dizer e caro de fazer, e
vale a pena separar as três dificuldades, porque só uma delas é a que parece.

**1 · Não é seguir uma cara. É seguir umas costas.** O YuNet encontra caras. Assim que a
Lara se vira para andar, o detetor deixa de a ver — e um robô que persegue vê sempre
costas, nunca caras. A solução não é um modelo maior: é apanhar a cara **uma vez**, passar
a caixa a um *tracker* do OpenCV (o KCF ou o CSRT seguem um retalho qualquer de imagem, não
só caras, e custam poucos milissegundos), e voltar a detetar de vez em quando para
reconfirmar que ainda é ela. Detetar uma vez, seguir muitas — a mesma ideia do D16.

**2 · A velocidade.** O motor do mBot2 dá **350 RPM em vazio e 178 RPM com carga**, com
redução de 39,6:1. Com as rodas do mBot2 isso são grosso modo **70-90 cm/s** no máximo,
antes do limite de segurança. Uma criança a andar pela casa faz 100-120 cm/s. **O robô não
consegue acompanhar-lhe o passo** — vai ficar para trás e apanhá-la quando ela parar.

> Isto não é um defeito a corrigir. Um robô que trota atrás de nós e nos alcança quando
> paramos é mais simpático do que um que nos cola aos calcanhares. É assim que se comporta
> um cão pequeno, e ninguém acha que o cão está avariado.

**3 · As escadas. E aqui está o número que decide tudo.**

Um sensor de precipício não é mágico: vê o degrau, o robô demora a reagir, e depois demora
a travar. A conta é esta:

```
margem = velocidade × tempo_de_reação  +  velocidade² / (2 × travagem)
         └─ enquanto não sabe ─┘          └────── enquanto trava ─────┘
```

Com o ciclo a 10 Hz e um robô de 2 kg a travar a ~1,5 m/s²:

| Onde está o sensor | Vê o degrau a | Velocidade segura |
|---|---|---|
| **TCRT5000 no para-choques** (o que temos) | ~5 cm à frente das rodas | **~27 cm/s** |
| **ToF apontado ao chão à frente** | ~30 cm à frente | **~81 cm/s** |

E aqui está a coisa que eu tinha dito mal: **os TCRT5000 servem para não cair da
secretária, e servem bem — a 25 cm/s a margem é de sobra.** O que eles não dão é margem
para seguir alguém a passo de casa. Um sensor que vê o degrau praticamente onde ele está só
funciona à velocidade da mesa.

> **Para andar atrás de alguém numa casa com escadas é preciso um sensor que olhe PARA A
> FRENTE, não um que olhe para baixo.**

Isso é um **VL53L1X apontado obliquamente ao chão, 30 cm à frente**: mede a distância ao
soalho, e quando essa distância salta de repente, há um degrau. €16,95, e o robô já leva um
igual a olhar em frente. ⚠️ Os dois ficam no mesmo endereço I2C (0x29) — é preciso um pino
XSHUT por sensor para os arrancar um de cada vez e mudar o endereço de um deles em código.
Isso é fase 16, não agora.

**Enquanto isso não existir:** o `seguir.velocidade_max` está em 0,35 e há um teste
(`test_a_velocidade_configurada_esta_dentro_do_que_e_seguro`) que compara a velocidade
configurada com a velocidade que os sensores conseguem travar e **falha** se alguém subir o
número no YAML. Assim que a velocidade real for medida na fase 6, esse teste passa a dizer
a verdade sozinho.

⚠️ **E uma regra que não é software:** enquanto o modo seguir estiver ligado, as escadas
levam uma barreira física. A conta acima diz que é seguro; uma criança a correr, um tapete
que escorrega e uma leitura falhada dizem que não vale a pena apostar nisso.

**O que já está feito:** `robot/brain/follow.py` — o controlador todo, com 19 testes. O
precipício veta tudo o resto, o robô abranda ao aproximar-se em vez de travar de repente,
tem zona morta para não tremer, e quando perde o alvo **para** em vez de continuar às cegas
na última direção. Falta a perceção, que precisa do robô real.

### D9 · Alimentação: **uma bateria LiFePO4, três barramentos**

> **Desenho histórico. Não construir a partir desta secção.** O barramento de
> motores abaixo pressupõe motores retirados do mBot2. O mBot2 permanece
> inteiro. A alimentação conjunta e o corte físico de movimento ainda precisam
> de uma experiência própria.

Era o pedido: uma só bateria para todo o sistema. A tentação é usar uma power bank USB-C
com duas saídas — e é uma armadilha por duas razões concretas:

1. **Quase nenhuma power bank de consumo negoceia o perfil PD de 5 V/5 A.** Sem isso o
   Pi 5 limita **todas** as portas USB a **600 mA no total** — o que mata o array de
   microfones.
2. Muitas desligam-se sozinhas com correntes baixas.

**A solução correta é um pack + reguladores dedicados:**

```
LiFePO4 4S (12,8 V) ──► fusível 10 A ──► interruptor principal
       │
       ├──► buck 5,1 V / 5 A ──► Raspberry Pi 5
       ├──► buck 5,7 V / 6 A ──► 5 servos
       └──► buck 7,4 V / 5 A ──► TB6612 ──► 2 motores
```

Continua a ser **uma bateria, um carregador, um interruptor** — e cada consumidor tem o
seu regulador, o que é precisamente o que impede os motores de reiniciarem o Pi.

**Porquê LiFePO4 e não Li-ion/LiPo:** a química LFP tem uma temperatura de início de fuga
térmica muito superior e **não liberta oxigénio** como a NMC/LCO — ou seja, não
auto-alimenta a combustão. Paga-se em peso (~90–120 Wh/kg contra 200–260), mas num robô
grande isso nem é defeito: baixa o centro de gravidade. **Com uma criança de 11 anos a
parafusar coisas por perto, esta troca é fácil de fazer.**

⚠️ Confirmem o stock: packs pequenos de LiFePO4 (12,8 V, 4–7 Ah) são escassos nas lojas
maker portuguesas — o mercado europeu é dominado por baterias de 12 V de lazer/solar.

**Autonomia:** consumo médio realista ~15 W (Pi ~6 W, motores ~4 W, servos ~2 W, resto
~3 W). Um pack de 12,8 V × 6 Ah = **77 Wh** dá mais de 4 horas. Com 4 Ah ainda dá 3.

### D10 · Braços: **PCA9685 + 2 DoF por braço + garra**

Cinco servos: **ombro** (DS3218 digital, ~20 kg·cm) e **cotovelo** (MG90S) em cada braço,
e uma **garra** (MG90S) no braço direito.

**Cálculo do binário:** braço de 15 cm com ~80 g na ponta ≈ 1,2 kg·cm, mais o momento do
próprio braço ≈ 2–3 kg·cm; com fator de segurança 3 → **6–9 kg·cm no ombro**. Um MG996R
(9,4 kg·cm) chegava, mas os clones baratos são inconsistentes e barulhentos. Com o
orçamento a permitir, um digital DS3218 é bastante melhor.

⚠️ **Nunca alimentar servos a partir dos pinos de 5 V do Raspberry Pi.** Esses pinos vêm
do rail de entrada, a jusante do PMIC que monitoriza brownout; as pistas do header são
finas; e o inrush e a back-EMF dos servos criam quedas que reiniciam o SoC ou corrompem o
cartão SD. Servos têm barramento próprio — só a **massa** é partilhada.

**2 DoF é o ponto certo.** Com 3+ DoF e servos deste preço, a folga mecânica torna a
cinemática inversa inútil.

⚠️ **A tensão do barramento é 5,7 V e não 6,0 V.** O MG90S está especificado para
4,8–6,0 V — a 6,0 V ficaria no topo absoluto, sem margem para tolerâncias do regulador.
A 5,7 V o DS3218 ainda dá cerca de **16 kg·cm**, muito acima dos 6–9 exigidos.

⚠️ **E a corrente de pico não cabe num regulador de 5 A.** Somando os *stalls*:
2× DS3218 (~3 A cada) + 3× MG90S (~0,7 A) ≈ **8,4 A**. E os 2200 µF de bulk só cobrem
cerca de um milissegundo. A resposta tem duas partes:

1. **Regulador de 6 A** em vez de 5 A (é a linha da folha de compras).
2. **Escalonar o arranque no software.** O `arms.pose()` move as juntas uma a uma, com
   80 ms entre elas, e os ombros nunca arrancam ao mesmo tempo. Está em
   `bracos.intervalo_s` no `robot.yaml` — não é estética, é elétrica.

Mesmo assim, um *stall* simultâneo é possível se um braço ficar preso. É por isso que
existe o botão de emergência, e por isso que este barramento tem fusível próprio.

### D11 · Porque **não** trocamos o Pi por um Arduino ou Pi Zero

A pergunta era boa e a resposta tem números.

**Um Arduino não corre isto.** Não é "mais lento" — é impossível: Whisper, OpenCV com
SFace e Piper precisam de centenas de MB de RAM e de instruções SIMD. Um Pi Zero 2W
correria, mas com reconhecimento de caras a 1–2 FPS e Whisper bem abaixo do tempo real.

**E a poupança seria pequena:** o Pi 5 consome ~3 W em repouso e ~8,8 W com os 4 cores a
100%. Tirar trabalho de tempo real do Pi para um microcontrolador poupa talvez **10–20%
do consumo do sistema, não 50%** — porque é o Whisper e o OpenCV que gastam. Com o pack
LiFePO4 especificado, **a autonomia já é de 3+ horas.**

**A bateria é barata; o cérebro não.** A resposta certa a "quanto tempo dura" é uma
bateria maior, não um cérebro menor.

**O que o microcontrolador dá mesmo é fiabilidade**, e isso fica para a v2: um ciclo
determinístico a 1 kHz, motores que param sozinhos se o Pi bloquear, e um robô que não
"foge" durante um arranque. Quando chegar essa altura, o **ESP32** é o vencedor claro do
que já temos: tem **8 unidades PCNT em hardware** para contar quadratura (o SAME51 do
Feather M4 tem só uma, e o CircuitPython nem sequer a usa; o RP2040 CAN perde 9 pinos
para o MCP2515).

**CAN bus:** over-engineering para 20 cm entre duas placas. O valor do CAN é multi-nó,
cablagens longas e ambiente eletromagneticamente hostil. Fica guardado como lição da v2 —
"a linguagem que os carros falam" é um tema excelente aos 12–13 anos, mas não é por onde
se começa.

### D13 · A rede de segurança que não depende de software

> **Desenho histórico.** O circuito OE descrito abaixo pertence aos drivers
> separados da versão anterior. Não é uma solução de paragem para o mBot2
> intacto.

O PCA9685 é *latching*: uma vez escrito um valor, o chip continua a gerar aquele PWM
**para sempre**, mesmo que o Raspberry Pi morra. Um `kill -9`, um kernel panic ou um
cartão SD corrompido deixariam os motores a rodar até a bateria acabar — com o robô a
atravessar a casa e ninguém a poder pará-lo pelo software.

A defesa é o pino **OE (Output Enable)** dos dois PCA9685, ligado ao **GPIO 25** com uma
resistência de pull-up de 10 kΩ para 3,3 V:

| Estado do Pi | GPIO 25 | Saídas dos PCA9685 |
|---|---|---|
| Vivo e a correr | LOW (o código põe-no assim) | ligadas |
| Morto, em reboot, ou a arrancar | alta impedância → o pull-up puxa para HIGH | **desligadas** |

Repare-se na direção: **a falha segura é o estado natural.** Não depende de nenhum
`atexit`, de nenhum `try/finally`, de nenhuma linha de Python chegar a correr. É a mesma
lógica do travão de mola de um elevador.

É diferente do botão de emergência, e os dois coexistem: o OE protege contra o software
falhar; o botão protege contra o robô fazer algo indesejado com o software a funcionar
perfeitamente.

### D12 · Reutilizar o mBot2 inteiro

O POC resolveu esta decisão. O Raspberry Pi controla o CyberPi e o mBot2 Shield
por USB. Conservamos o chassis, os motores, os encoders, o giroscópio, os
ultrassons, o sensor RGB e as luzes.

O ensaio está em `scripts/spike_mbot2.py`. O driver de produção está em
`robot/hardware/mbot2.py`. A configuração usa `motores.ligacao: mbot2`.

Não se desmonta o mBot2, não se mede a pinagem dos motores e não se cortam os
cabos. A questão que fica aberta é a paragem física de emergência e a
alimentação conjunta do mBot2 e do Pi.

---

## 5. Lista de peças (resumo)

> **Arquivo de compras. Não encomendar a partir desta secção nem da folha de
> cálculo antiga.** Esta lista ainda inclui o reSpeaker, um TB6612, sensores
> duplicados e um HUB75 já escolhido. O inventário atual está em
> [`docs/componentes.md`](docs/componentes.md). A cara continua por decidir.

O conteúdo abaixo explica opções consideradas numa versão anterior.

### Encomenda 0 — "A bancada" (€147) · **antes de tudo o resto**

Ferramentas, não peças. Duram uma vida e servem para tudo — por isso estão **fora** do
total do robô, tal como a impressora 3D.

| Item | Preço |
|---|---|
| Estação de soldar com base pesada (936 / Yihua) | €30,00 |
| **Solda SEM CHUMBO** 0,7 mm, 100 g ⚠️ | €14,00 |
| Fluxo em caneta, no-clean | €8,00 |
| Lã de latão (melhor que a esponja molhada) | €6,00 |
| Ponta **chisel** 2,4 mm de reserva ⚠️ | €5,00 |
| Malha dessoldadora + bomba | €10,00 |
| Terceira mão | €8,00 |
| Alicate de corte flush + descarnador | €18,00 |
| Óculos de proteção (2 pares) | €8,00 |
| **Kit de prática** (Whadda WSI102 ou similar) ⚠️ | €15,00 |
| Multímetro — se não tiverem | €25,00 |

⚠️ **Com uma criança por perto, o suporte pesado importa mais que o ferro.** Uma estação
de €30 com base estável é mais segura que um ferro portátil pousado na mesa. O ponto de
retorno decrescente é aos ~€40: um Hakko de €120 não ensina melhor.

⚠️ **Ponta chisel, não de agulha.** A de agulha é a que toda a gente experimenta primeiro
e é a pior — a chisel transfere muito mais calor.

⚠️ **O kit de prática não é opcional.** São €15 contra o risco de destruir um Pi de €96.

*Recomendado a mais: uma ventoinha USB pequena (€12) — ver §10.5.*

### Encomenda 1 — "O cérebro e a voz" (€245,25) · fases 1–3

| Peça | Fase | Preço |
|---|---|---|
| Raspberry Pi 5 · 4 GB | 1 | €95,90 |
| Fonte oficial USB-C 27 W (bancada) | 1 | €13,90 |
| Cartão microSD 64 GB A2 | 1 | €14,00 |
| Active Cooler oficial | 1 | €5,50 |
| Jumpers, breadboard, parafusos M2.5/M3 | 1 | €17,00 |
| **reSpeaker XVF3800** USB — 4 mics com AEC, **e a placa de som** ⚠️ | **2** | €60,00 |
| **Coluna DFRobot 3 W / 8 Ω, ficha JST PH 2.0** (Botnroll "Coluna stereo - 3W") | **2** | €4,95 |
| Camera Module 3 (76°, autofoco) | 9 | €32,80 |
| **Cabo CSI oficial 22→15 pinos, 200 mm** ⚠️ | 9 | €1,20 |

⚠️ **O reSpeaker vem já na encomenda 1 porque é por ele que sai o som** (D6). Antes
estava aqui um amplificador I2S MAX98357A a €8 — retirado: tocava ao lado do reSpeaker e
deixava-o sem referência para o cancelamento de eco. A coluna encaixa diretamente na
ficha JST PH 2.0 da placa; apesar do nome na loja, é **uma** coluna, não um par.

💡 O reSpeaker **não existe em loja portuguesa** e o stock na Europa anda apertado
(Gotronic €59,90 com reposições, Kiwi esgotada, Botland, ou a Seeed direta a $60,99).
Encomendar no mesmo dia que o resto. Se atrasar, a fase 2 faz-se com um micro-HDMI do
Pi à televisão — a voz sai pelas colunas da TV e as fases 3 e 4 não dependem do som.

⚠️ O Pi 5 mudou para conectores CSI de 22 pinos e **todas** as câmaras Raspberry Pi vêm
com o cabo antigo de 15. Sem o adaptador a câmara não liga — é o erro mais comum de quem
vem do Pi 4. O adaptador é preciso com qualquer câmara, nova ou velha; não é uma
desvantagem de nenhum modelo em particular. É o cabo **oficial** da Raspberry Pi
(SC1128 na Botnroll, SC1892 na Mauser) e custa pouco mais de um euro — não vale a pena
procurar alternativas.

💡 **A câmara é €2,81 mais barata na Mauser** (€29,99, 80 em stock) e o cabo €1,17. Vale a
pena se fores levantar a uma das sete lojas — o levantamento é grátis. Se a encomenda for
toda pelo correio, não compensa: a Botnroll já leva o Pi, e um segundo envio come a
diferença. Ver *Onde comprar*.

**Porque não a câmara com iluminadores IR (€21,90).** Ver secção D4b.

### Encomenda 2 — "A cara e a energia" (€300,00) · fases 3–5

| Peça | Fase | Preço |
|---|---|---|
| **Painel HUB75 64×32 RGB (P2.5)** — a cara | **3** | €20,00 |
| Cablagem HUB75 ↔ ESP32 + shield/protoboard | **3** | €12,00 |
| Pack **LiFePO4 4S 12,8 V ~6 Ah** com BMS | 5 | €60,00 |
| Carregador LiFePO4 14,6 V | 5 | €22,00 |
| Regulador 5 V / 5 A (Pololu D24V50F5) → Pi | 5 | €35,00 |
| Regulador 5,7 V / **6 A** → servos ⚠️ | 5 | €42,00 |
| Regulador 7,4 V / 5 A → motores | 5 | €35,00 |
| Fusíveis, interruptor, **botão de emergência (DPST)** ⚠️ | 5 | €24,00 |
| **Conectores WAGO 221-413** (pack 20) — potência sem soldar | 5 | €12,00 |
| **XT60 pigtails** (já com fio) + fio 18 AWG e 22 AWG | 5 | €20,00 |
| Condensadores bulk (2× 2200 µF, 2× 1000 µF, cerâmicos 100 nF) | 5 | €10,00 |
| Protoboard tamanho HAT + barras de pinos | 5 | €8,00 |


### Encomenda 3 — "Movimento, braços e sentidos" (€142,80) · fases 6–8

| Peça | Fase | Preço |
|---|---|---|
| 2× PCA9685 16 canais — **clones já soldados** ⚠️ | 6 | €16,00 |
| TB6612FNG — SparkFun **"with Headers"** ⚠️ | 6 | €14,00 |
| Sensor ultrassónico HC-SR04**P** (3,3 V) ⚠️ | 7 | €4,90 |
| Sensor ToF VL53L1X (4 m, I2C) | 7 | €16,95 |
| Sensor de precipício TCRT5000 3 canais | 7 | €7,95 |
| ADS1115 — mede a tensão da bateria | 7 | €8,00 |
| 2× servo digital DS3218 (~20 kg·cm) — ombros | 8 | €36,00 |
| 3× servo MG90S — cotovelos e garra | 8 | €18,00 |
| Horns, braçadeiras e parafusos para servos | 8 | €15,00 |
| ⭐ **3× sensor de toque TTP223** (com pinos soldados) | **14** | €6,00 |

⚠️ **Tem de ser o HC-SR04P.** O modelo normal devolve 5 V no pino Echo e **destrói** o
GPIO de 3,3 V do Pi. São €1,30 de diferença.

⭐ **Os €6 mais bem gastos do projeto.** O Eilik — o robô de secretária que as pessoas
descrevem como mais vivo dos três de referência — **não tem câmara nenhuma**. Constrói a
personalidade toda em cima de três sensores de toque e de coisas que faz sozinho. Cabeça,
costas e frente, em GPIO 4, 16 e 26 (livres). Ver D16.

### Encomenda 4 — "O aspeto" (€169,00) · fase 13

*(O reSpeaker, que era a peça dos "ouvidos" desta encomenda, passou para a encomenda 1 —
é também a placa de som, e o som é preciso na fase 2. A fase 10 já não precisa de comprar
nada.)*

| Peça | Fase | Preço |
|---|---|---|
| **Acrílico preto de difusão 2–3 mm** (~170×90 mm) ⚠️ | 13 | €14,00 |
| **LEDs azuis (20×) + resistências 120 Ω** — propulsores e peito | 13 | €6,00 |
| **Vinil espelhado / tinta cromada** — a calote do topo | 13 | €9,00 |
| **Filamento PLA branco + PLA azul + PETG** | 13 | €45,00 |
| Contraplacado 3 mm / acrílico, cartão, tintas, cola quente | 13 | €35,00 |
| Parafusos, espaçadores M3, cantoneiras para a estrutura | 13 | €20,00 |
| Impressão 3D por serviço — **se ainda não houver impressora** | 13 | €40,00 |

⚠️ O acrílico preto de difusão é a peça mais barata com maior efeito de toda a lista.
Sem ele veem-se 128 LEDs numa placa verde; com ele, veem-se dois olhos a brilhar num
visor escuro.

### Sobressalentes (€25,00) — recomendado num projeto de 4 meses

Um MG90S extra, um TB6612 extra, fusíveis e cabos. **Coisas partem-se**, e esperar uma
semana por uma peça de €5 mata o ritmo.

### Total do robô: **€882,05** — dentro dos €1000, com ~€118 de folga

*(A bancada, €147, e a impressora 3D, €424, são ferramentas — contam à parte.)*

*(A impressora 3D é à parte — ver §13. Não é preciso para começar.)*

| Upgrade opcional | Preço | Vale a pena? |
|---|---|---|
| Pi 5 8 GB em vez de 4 GB | +€93 | Só se quiserem correr um LLM local também |
| 2× ecrã redondo GC9A01 (olhos a cores) | +€31 | **Não** — ver D2: atrás do acrílico ficam ilegíveis, e o HUB75 já é a cores |
| AI HAT+ 26 TOPS (Hailo-8) | +€130 | **Não.** O CPU do Pi 5 chega para 6 caras, e este não faz IA generativa |
| AI HAT+ 2 · 40 TOPS (Hailo-10H) | +€220 | **Não por agora.** Ver D8b — só corre um modelo de cada vez |
| Coral USB Accelerator | — | **Não comprar.** Google arquivou o repo em abril/2026 |

### Onde comprar

| Loja | País | Notas |
|---|---|---|
| **Botnroll** | 🇵🇹 | Melhor preço no Pi 5 (€95,90). Primeira paragem. Tem a coluna certa ("Coluna stereo - 3W", €4,95) — mas **não** tem o reSpeaker nem amplificadores I2S |
| **Mauser** | 🇵🇹 | **A melhor para a câmara**: Module 3 a €29,99 e cabo oficial a €1,17, ambos com stock alto. **Sete lojas com levantamento grátis** (Porto, Lisboa, Leiria, Corroios, Portela, Freixeira, Funchal). ⚠️ Não comprar aqui o Pi 5: €119,88 e esgotado |
| **PTRobotics** | 🇵🇹 | Bom catálogo, mas €131,98 pelo *mesmo* Pi 5 — diferença de €36 |
| **BerryBase / Welectron** | 🇩🇪 | Módulos pequenos e reguladores |
| **The Pi Hut / Pimoroni** | 🇬🇧 | reSpeaker e Adafruit. Atenção a taxas alfandegárias |
| **Botland** | 🇵🇱 | Tem o XVF3800 e os reguladores Pololu dentro da UE |
| **Gotronic** | 🇫🇷 | reSpeaker XVF3800 a €59,90 (dentro da UE, sem alfândega). Esgota com frequência — ver a data de reposição na página |
| **Kiwi Electronics** | 🇳🇱 | reSpeaker XVF3800 a €48,99 + IVA quando há stock |

---

## 6. Alimentação e ligações elétricas

> **Esquema inválido para a construção atual. Não ligar componentes a partir
> desta secção.** O diagrama pressupõe motores separados, reSpeaker e HUB75.
> Hoje o mBot2 fica inteiro, o áudio ainda está em teste e a escolha do ecrã
> está aberta. A alimentação e a paragem física precisam de novo esquema depois
> das medições.

### 6.1 Diagrama de energia

```
            ┌─────────────────────────────────────────────┐
            │  LiFePO4 4S · 12,8 V · ~6 Ah · com BMS      │
            │  (conector XT60, carregado FORA do robô)    │
            └──────────────────┬──────────────────────────┘
                               │
                        [FUSÍVEL 10 A]      ← principal, antes de tudo
                               │
                     [INTERRUPTOR PRINCIPAL]
                               │
        ┌──────────────────────┼──────────────────────┐   ← estrela, a partir
        │                      │                      │     dos terminais
   [fusível 3 A]          [fusível 5 A]          [fusível 5 A]
        │                      │                      │
  ┌─────┴──────┐        ┌──────┴──────┐        ┌──────┴──────┐
  │ buck 5,1 V │        │ buck 5,7 V  │        │ buck 7,4 V  │
  │    5 A     │        │     5 A     │        │     5 A     │
  └─────┬──────┘        └──────┬──────┘        └──────┬──────┘
        │                      │                      │
   ┌────┴─────┐         [BOTÃO EMERGÊNCIA]─────┬──────┘
   │  Pi 5    │                 │              │
   │ XVF3800  │            2200 µF         1000 µF
   │ + coluna │                 │              │
   │ ESP32 +  │            5 servos        TB6612 ──► 2 motores
   │  HUB75   │
   │ Câmara   │
   └──────────┘

        ═══════ MASSA COMUM A TUDO (star ground) ═══════
```

**O botão de emergência corta a potência dos servos e motores, mas não a do Pi.** Isto é
deliberado: o robô para de se mexer instantaneamente, mas continua a falar e a explicar o
que aconteceu. Um botão que desliga tudo assusta; este ensina.

⚠️ **Tem de ser um botão de dois polos (DPST).** Com um polo só, os dois barramentos
ficariam ligados um ao outro através do botão — cada linha precisa do seu contacto.

### 6.2 Regras que fazem isto funcionar

| Regra | Valor concreto | Porquê |
|---|---|---|
| **Topologia em estrela** | Cada buck com o seu par de fios até ao pack | Em cadeia, a queda de um afeta os outros |
| **Condensadores de bulk** | 2200 µF low-ESR (≥25 V) nos servos; 1000 µF nos motores; 100 nF cerâmico em paralelo em cada | Cobrem os picos de arranque |
| **Condensadores nos motores** | 100 nF nos terminais de cada motor DC | Contra o ruído das escovas |
| **Secção de fio** | **18 AWG** (0,82 mm²) na potência; 22–24 AWG só para sinal | 5 A em 24 AWG aquece e cai tensão |
| **Massa comum** | Obrigatória entre todos os barramentos | Sem ela o I2C não comunica de forma fiável |
| **Fusível principal** | 10 A rápido, no positivo, antes de tudo | €0,50 de seguro |
| **Fusível por ramal** | 3 A Pi · 5 A servos · 5 A motores | Isola a falha |
| **Conectores** | XT30/XT60, nunca fios nus | Não se inverte a polaridade por acidente |

⚠️ **A alimentação do Pi tem um pormenor:** o regulador entrega 5 V mas não faz negociação
USB-PD, por isso o Pi assume 3 A e limita as portas USB a 600 mA no total — insuficiente
com o reSpeaker (que além dos microfones alimenta o amplificador da coluna e 12 LEDs RGB)
mais o ESP32. A correção é uma linha no `/boot/firmware/config.txt`:

```
usb_max_current_enable=1
```

Isto diz ao Pi "confia em mim, a minha fonte aguenta", e sobe o limite para 1,6 A. **Só é
seguro porque o regulador dá mesmo 5 A.** Verificar depois com `vcgencmd get_throttled` —
tem de dar `0x0`.

### 6.3 Atribuição de pinos GPIO

| Pino BCM | Pino físico | Ligado a | Função |
|---|---|---|---|
| GPIO 2 | 3 | PCA9685 ×2, ADS1115, VL53L1X | I2C SDA |
| GPIO 25 | 22 | **OE dos dois PCA9685** (pull-up 10 kΩ) | Paragem por hardware — ver D13 |
| GPIO 3 | 5 | idem | I2C SCL |
| GPIO 8, 10, 11 | 24, 19, 23 | — | SPI0 **livre** (era o MAX7219; a cara passou para o ESP32 por USB) |
| GPIO 17 | 11 | TCRT5000 canal 1 | Precipício esquerda |
| GPIO 18, 19, 21 | 12, 35, 40 | — | I2S **livre** (era o MAX98357A; o som sai pelo reSpeaker por USB — D6) |
| GPIO 22 | 15 | TCRT5000 canal 3 | Precipício direita |
| GPIO 23 | 16 | HC-SR04P | Trigger |
| GPIO 24 | 18 | HC-SR04P | Echo |
| GPIO 27 | 13 | TCRT5000 canal 2 | Precipício centro |
| GPIO 5 | 29 | Encoder motor esq. canal A | *ligado, à espera da v2* |
| GPIO 6 | 31 | Encoder motor esq. canal B | *ligado, à espera da v2* |
| GPIO 12 | 32 | Encoder motor dir. canal A | *ligado, à espera da v2* |
| GPIO 13 | 33 | Encoder motor dir. canal B | *ligado, à espera da v2* |
| — | CSI | Camera Module 3 | Via cabo adaptador 22→15 |
| — | USB | reSpeaker XVF3800 | Porta USB 2.0 — microfones **e** coluna (JST PH 2.0 na placa) |
| — | USB | ESP32 (a cara) | Porta USB 2.0 — só série |

### 6.4 Endereços I2C

| Dispositivo | Endereço |
|---|---|
| PCA9685 #1 — motores (1 kHz) | `0x40` |
| PCA9685 #2 — servos (50 Hz) | `0x41` (soldar jumper A0) |
| VL53L1X — distância | `0x29` |
| ADS1115 — tensão da bateria | `0x48` |

Teste: `i2cdetect -y 1` tem de mostrar os quatro.

---

## 7. Fases históricas

> Estas fases conservam o raciocínio e algumas experiências úteis. A ordem
> ativa, os responsáveis e os critérios de pronto estão em
> [`docs/roteiro.md`](docs/roteiro.md).

---

### FASE 0 · O caderno e o inventário

> 📄 **Enquanto as peças não chegam:** o `ENQUANTO-ESPERAS.md` no repositório tem
> sete coisas por ordem de valor, cinco delas sem precisar do Raspberry Pi. A
> primeira — pôr a voz do robô a funcionar no Mac — demora 30 minutos e é a que
> torna o projeto real para a Lara. `python scripts/check_mac.py` diz o que já
> está pronto.

**Antes de comprar seja o que for · 1–2 horas**

**Objetivo:** Uma ideia partilhada do que se vai construir, e saber exatamente o que já
temos.

**A Lara faz:**
- Escolhe o **nome** do robô. *(Não avancem sem isto. Uma coisa com nome merece atenção;
  um "projeto" não.)*
- **Desenha a variante dela do Astro.** Imprimam a `design-astrosonda.html`, e ela
  desenha por cima ou de raiz: que forma tem a base? Onde ficam os painéis azuis?
  Quantas antenas? Há um emblema de missão? *O fato de sonda espacial ainda não existe
  no jogo — só vai existir depois de ela o inventar.*
- **Desenha as caras dele** — pelo menos nove. Contente, triste, surpreso, a dormir,
  zangado, a pensar… e as que ela inventar. Sem grelha: são desenhos livres da *forma*
  dos olhos, porque o Astro não tem boca e é a forma que diz tudo.
  Na fase 3 estes desenhos viram números — e ela vai perceber que uma forma se pode
  descrever com cinco valores.
- Escreve na primeira página: *"O meu robô vai conseguir ____"* (cinco coisas).
- Faz o **inventário**: mBot2, ESP32, as duas placas CAN. Fotografa tudo e cola no caderno.

**O pai faz:** Revê a lista da Lara contra a §2 e negoceia o que fica de fora (§2.3).
Faz a encomenda 1.

**Critério de pronto:** O robô tem nome, existe um desenho da variante AstroSonda dela,
9 grelhas de olhos desenhadas, o inventário no caderno, e a encomenda 1 feita.

> 💡 O caderno em papel é intencional. Ao longo de 4 meses vão esquecer-se de porque
> escolheram cada coisa. E daqui a 10 anos o caderno vale mais que o robô.

---

### FASE 0.5 · Aprender a soldar
**Antes de o Pi chegar · 2 horas · a sessão mais barata do projeto**

**Objetivo:** Fazer ~100 juntas de solda numa placa que não vale nada, para que a
primeira junta a sério não seja numa placa de €96.

**Momento "uau":** Uma junta boa. É uma coisa concreta e visível — brilhante, com forma
de cone vulcânico, agarrada ao pino *e* à placa. E a partir daí vê-se logo a diferença
para uma junta má.

**O pai faz:**
1. Monta a bancada num sítio **com janela**. Ferro no suporte, ventoinha a **puxar** o ar
   para longe das caras.
2. Vê dois ou três vídeos de "how to solder through-hole" antes de ligar o ferro.
   Ferro a 350 °C com solda sem chumbo.
3. **Estanha a ponta** (uma gota de solda) antes de a pousar, sempre. É o que a faz durar.
4. Faz o kit de prática do princípio ao fim. Depois desfaz metade das juntas com a malha
   dessoldadora — desfazer é metade da competência.

**A regra das juntas boas**, que se aprende em cinco minutos e demora uma hora a dominar:

> Aquece-se o **pino e a placa ao mesmo tempo** com a ponta, conta-se até dois, e só
> então se toca com a solda **no pino, não na ponta do ferro**. A solda corre para o
> sítio quente. Tira-se a solda, depois o ferro. Um segundo depois está sólida.

Se a solda ficar em bola e não agarrar, o metal estava frio — não é falta de solda.

**A Lara faz:**
- Vê as primeiras dez juntas, e explica em voz alta o que está a acontecer.
- **Depois experimenta ela**, na placa de prática, com o pai ao lado a cada junta.
- Vai buscar os componentes, endireita os terminais, corta o que sobra com o alicate.

**Quando é que ela pode soldar sozinha?** A idade não é o melhor critério — o manual de
segurança da FIRST Robotics normaliza 10–13 anos com supervisão de um-para-um. O critério
prático é melhor:

> **Ela pode soldar quando puser o ferro no suporte de forma fiável entre juntas, sem ter
> de se lembrar.** Testa-se isso na placa de prática, que não tem nada a perder.

**Critério de pronto:** Existe uma placa de prática cheia de juntas, e as últimas vinte
são visivelmente melhores que as primeiras vinte. Ninguém se queimou.

> 💡 O único trabalho de soldadura a sério do projeto são **18 juntas nos três
> reguladores**, na fase 5. Tudo o resto foi comprado já soldado. Depois de 100 juntas de
> treino, essas 18 vão parecer fáceis — que é exatamente a ideia.

---

### FASE 1 · O cérebro acorda
**Semana 1 · 2–3 horas**

**Objetivo:** Um Raspberry Pi a arrancar, na rede, acessível por SSH do Mac, sem teclado
nem ecrã.

**Momento "uau":** Escrever um comando no Mac e ver o LED do Pi a piscar do outro lado da
mesa. *"Estou a mandar no computador dali."*

**A Lara faz:**
1. Grava o microSD com o **Raspberry Pi Imager**. Sistema: **Raspberry Pi OS Lite 64-bit**
   (sem ambiente gráfico — é um robô, não um PC).
2. Nas definições avançadas: nome `robo`, utilizador, palavra-passe, Wi-Fi, **SSH ativado**.
3. Monta o dissipador, mete o cartão, liga a corrente.
4. No Mac: `ssh lara@robo.local` — e está lá dentro.
5. Primeiro programa: `echo 'print("Olá, eu sou o [nome]!")' > ola.py && python3 ola.py`

**O pai faz:** a instalação de raiz do Apêndice B — resumida:
```bash
sudo apt update && sudo apt full-upgrade -y
sudo raspi-config    # Interface Options → I2C ✓ SPI ✓ (a câmara é detetada sozinha)
sudo apt install -y git python3-venv python3-pip i2c-tools avahi-daemon libnss-mdns \
     python3-lgpio python3-gpiozero
sudo apt install -y --no-install-recommends python3-picamera2
```
Chaves SSH sem palavra-passe (no Imager: "Allow public-key authentication only", com a
chave `~/.ssh/id_ed25519.pub` do Mac) e VS Code com *Remote-SSH*, para a Lara editar com
um editor a sério.

⚠️ **O ambiente virtual tem de ver os pacotes do sistema:**
`python3 -m venv --system-site-packages .venv`. O `picamera2` só existe pelo `apt`; um venv
normal não o vê, e daqui a dois meses a câmara "não existe" sem ninguém perceber porquê.

💡 **Já que a câmara e o cabo chegaram, tira-lhes o risco hoje:** com o Pi **desligado e
sem alimentação** — a câmara só é detetada no arranque, e o conector CSI não é feito para
se ligar com corrente. Ponta de 15 pinos na câmara, ponta de 22 numa das portas CAM/DISP
(ficam entre os micro-HDMI e a Ethernet). Nas duas pontas, **os contactos metálicos ficam
virados para o lado oposto à patilha de plástico**; levantar a patilha, enfiar o cabo a
direito até ao fundo, fechar. Depois `rpicam-hello --list-cameras` tem de mostrar um
`imx708`. Se disser "No cameras available", é quase sempre o cabo ao contrário ou mal
encaixado — desligar, ver, repetir. A primeira fotografia (`rpicam-jpeg -n -o foto.jpg`)
vai para o caderno. E o momento "uau" que não estava previsto para esta fase:
`/usr/bin/python3 scripts/ver_camera.py` e a Lara abre `http://robo.local:8000` no
telemóvel — vê pelos olhos do robô antes de ele ter olhos.

**Critério de pronto:** `ssh lara@robo.local` funciona sem palavra-passe e o `ola.py` corre.

---

### FASE 2 · O robô fala
**Semana 2 · 2 horas**

**Objetivo:** Reproduzir no robô uma frase sintetizada no mac mini.

Esta fase começa depois de inventariar os três microfones, o MAX98357A e a
coluna que chegam em 5 de setembro.

**A Lara faz:**

1. Regista o modelo e a interface de cada microfone.
2. Escreve uma frase e pede ao serviço do mini para a sintetizar.
3. Ouve o WAV no Pi através da coluna.
4. Grava cinco frases e vê a transcrição produzida pelo Parakeet no mini.

**O adulto faz:** Confirma a impedância da coluna, monta o MAX98357A na
breadboard e mede a alimentação antes de ligar o altifalante.

**Critério de pronto:** Uma frase percorre o caminho completo do mini à coluna.
Quatro das cinco gravações são transcritas corretamente no mini. A interrupção
durante a fala não faz parte deste critério.

---

### FASE 3 · Escolher o ecrã da cara
**Semana 3 · 3 horas**

**Objetivo:** Comparar um HUB75 e um OLED concreto antes de desenhar a cabeça.

**A Lara faz:** Escolhe cinco cenas no `bot-face`: repouso, piscar, olhar,
coração e uma transição. Avalia a leitura a dois metros e escolhe a estética que
prefere.

**O adulto faz:** Regista o modelo do OLED e mede tempo de arranque, imagens por
segundo, memória, CPU e consumo nas duas opções. Confirma que o openWakeWord
continua a responder enquanto a cara anima.

**Critério de pronto:** A escolha fica registada com as medições. Até esse
momento, usamos os LEDs do mBot2 e não compramos nem recortamos peças para o
ecrã final.

---

### FASE 4 · O mBot2 responde ao Raspberry Pi
**Sessão de 2 horas**

**Objetivo:** Controlar o mBot2 intacto por USB e medir os sensores que já traz.

**A Lara faz:**

- liga o cabo USB sem retirar nenhuma peça
- identifica as duas rodas, os encoders e o giroscópio
- testa o ultrassónico e os quatro canais do sensor RGB
- experimenta as luzes do CyberPi e as animações do ultrassónico.

**O adulto faz:** Mantém as rodas no ar durante o primeiro movimento e confirma
que o comando de paragem funciona.

**Critério de pronto:** `scripts/spike_mbot2.py` identifica o CyberPi, lê os
sensores e para as duas rodas. O mBot2 continua montado.

---

### FASE 5 · O coração
**Semana 5 · 3–4 horas · esta é a fase do pai**

> **Não executar esta fase.** O desenho de três barramentos inclui um
> controlador de motores que já não faz parte do robô. É preciso redesenhar a
> potência para o mBot2 intacto.

**Objetivo:** Um sistema de alimentação a sério: uma bateria, três barramentos, fusíveis,
interruptor e botão de emergência.

**Momento "uau":** Carregar no interruptor e ver três LEDs verdes acenderem. O robô tem
corrente própria pela primeira vez.

**O pai faz** (a Lara observa, passa componentes e faz as medições):
- Monta os três reguladores na protoboard e **ajusta as tensões com o multímetro ANTES de
  ligar seja o que for**: 5,1 V / 5,7 V / 7,4 V.
- Cablagem em estrela desde os terminais da bateria, fio 18 AWG.
- Fusível principal de 10 A + fusível por ramal.
- Interruptor principal e botão de emergência (corta servos e motores, **não** o Pi).
- Condensadores de bulk.
- No `config.txt`: `usb_max_current_enable=1`.

**A Lara faz:**
- **Mede e regista** as três tensões no caderno, antes e depois de ligar a carga.
- Aprende o que faz um fusível. ⚠️ **A demonstração faz-se com uma pilha de 4,5 V ou
  uma fonte de bancada, NUNCA com o pack LiFePO4 de 6 Ah** — um curto nesse pack
  entrega centenas de amperes. É o pai que provoca o curto; a Lara observa e mede.
- Testa o botão de emergência.

**Critério de pronto:** As três tensões estão dentro de ±2% com o Pi ligado.
`vcgencmd get_throttled` dá `0x0`. O botão de emergência corta os barramentos de 5,7 V e
7,4 V e não o de 5 V.

⚠️ **Nesta fase não há atalhos.** Uma inversão de polaridade mata um Pi de €95. Regra
absoluta: **verificar duas vezes antes de ligar, sempre com a bateria desligada.**

---

### FASE 6 · As rodas andam
**Semana 6 · 3 horas**

**Objetivo:** O robô move-se por comando.

**Momento "uau":** Anda. Depois de cinco semanas de peças em cima da mesa, aquilo
atravessa a sala.

**A Lara faz:**
- Liga o mBot2 ao Pi por USB.
- Corre `python scripts/test_motors.py` com as rodas no ar.
- Confirma a orientação das rodas e ajusta apenas
  `mbot2.inverter_direita` se a medição o pedir.
- Usa `andar()`, `recuar()`, `virar_direita()`, `virar_esquerda()` e `parar()`.
- Programa uma dança curta com as luzes que já existem.

**O adulto faz:** Segura o robô no primeiro teste, confirma a porta USB estável
e fica junto ao comando de paragem durante o primeiro movimento no chão.

**Critério de pronto:** Anda 1 metro razoavelmente a direito, roda 90°, e para.

**Conceito a explicar:** Os encoders medem a rotação real. O giroscópio mede a
rotação do corpo. Comparar os dois mostra quando as rodas escorregam.

---

### FASE 7 · O robô não se magoa
**Semana 7 · 2–3 horas**

**Objetivo:** Medir os limites dos sensores do mBot2 antes de permitir movimento
autónomo.

**A Lara faz:**

- mede o ultrassónico contra objetos largos, estreitos e inclinados
- regista `L2`, `L1`, `R1` e `R2` em vários pisos e sobre espaço vazio
- compara as leituras com luz de quarto, sombra e luz do dia
- escolhe com o adulto os casos em que o robô deve recusar movimento.

**O adulto faz:** Mantém os motores desligados durante a calibração. O primeiro
ensaio de borda usa uma queda baixa e almofadada, com o robô seguro pela mão. Não
usa uma mesa nem escadas.

**Critério de pronto:** O obstáculo à frente é detetado de forma repetível. A
experiência do sensor RGB tem uma tabela de resultados. Uma leitura ausente ou
antiga faz o robô parar. A marcha-atrás autónoma permanece desligada enquanto
não houver cobertura traseira.

---

### FASE 8 · Os braços
**Semana 8 · 4 horas**

**Objetivo:** Dois braços com ombro e cotovelo, e uma garra que agarra.

**Momento "uau":** O robô acena. Um robô que acena deixa de ser um objeto.

**A Lara faz:**
- Monta os servos nos suportes e liga-os ao PCA9685 `0x41`.
- **Descobre os limites de cada junta na mão**: move o servo devagar e anota o ângulo em
  que o braço bate no corpo. Estes números vão para o `robot.yaml`.
- Escreve os gestos: `acenar()`, `apontar()`, `abrir_garra()`, `festejar()`.
- Faz o robô pegar num lápis.

**O pai faz:** Barramento de 5,7 V dedicado com 2200 µF de bulk. Confirma que os servos
**nunca** tocam nos pinos de 5 V do Pi. Limites de segurança no código, para um ângulo
absurdo não partir a mecânica.

**Critério de pronto:** Os 5 servos movem-se sem o Pi reiniciar. `acenar()` é reconhecível
como um aceno. A garra segura um lápis.

⚠️ **Se o Pi reiniciar quando os servos se mexem**, o problema é de alimentação, não de
código: mais bulk, fio mais grosso, ou um regulador só para os servos.

---

### FASE 9 · O robô vê
**Semanas 9–10 · 4 horas (duas sessões)**

**Objetivo:** Capturar e reconhecer no Pi as caras da família.

**Momento "uau":** A Lara passa à frente e ele diz *"Olá, Lara!"*. Este é o pico emocional
do projeto inteiro.

**A Lara faz:**

*Sessão A:* Liga a câmara, confirma a imagem e testa pouca luz, perfil e várias
pessoas. A imagem permanece no Pi.

*Sessão B:* Regista cada pessoa depois de pedir consentimento. Testa pessoas
conhecidas, desconhecidas e a eliminação dos dados.

**O adulto faz:** Confirma o desempenho de YuNet e SFace no Pi e verifica que
os dados de rosto não entram no Git.

**Critério de pronto:** Reconhece 4 pessoas em 5 tentativas cada. Diz "não te conheço" a um
estranho.

**Conversa importante:** *"Achas que este robô devia poder gravar a cara de alguém sem essa
pessoa saber?"* Mostrem-lhe o ficheiro com os números. Apaguem uma pessoa à frente dela. É
a primeira aula de privacidade dela, e é concreta.

---

### FASE 10 · O robô ouve
**Semanas 11–12 · 4 horas (duas sessões)**

**Objetivo:** Acordar no Pi com a palavra-chave e transcrever no mac mini.

**A Lara faz:**

*Sessão A:* Grava amostras da palavra de ativação e mede distância, ruído e
falsos despertares.

*Sessão B:* O Pi deteta a palavra-chave, envia o áudio e o Parakeet transcreve no
mini. Testa nomes próprios, fala rápida e silêncio no fim da frase.

**O adulto faz:** Mede a latência de cada etapa e confirma que `pára` continua
local. O microfone fica longe dos motores durante esta medição.

**Critério de pronto:** A palavra-chave funciona dez vezes seguidas a um metro.
Uma hora de ruído normal produz no máximo um falso despertar. Quatro de cinco
frases são transcritas corretamente no mini.

A interrupção durante a reprodução fica planeada para uma fase posterior. O
código atual não cancela áudio que já está a tocar.

---

### FASE 11 · O cérebro grande
**Semana 13 · 3 horas**

**Objetivo:** Ligar o robô ao LLM que corre no Mac.

**Momento "uau":** A Lara faz uma pergunta que ninguém programou — *"porque é que o céu é
azul?"* — e o robô responde. Bem.

**A Lara faz:**
- **Escreve o "system prompt"** — a personalidade do robô. Isto é dela.
- Testa como mudar o prompt muda a personalidade. Faz uma versão "robô mal-humorado".
  **Esta é a lição mais valiosa do projeto sobre o que os LLMs são.**

**O pai faz:**
```bash
launchctl setenv OLLAMA_HOST "0.0.0.0:11434"
launchctl setenv OLLAMA_KEEP_ALIVE "-1"
ollama pull gemma4:12b
```

**Critério de pronto:** Cinco perguntas com resposta coerente em ≤5 s cada. Com o Mac
desligado, diz *"o meu cérebro grande está a dormir"* em vez de rebentar.

---

### FASE 12 · O robô obedece
**Semana 14 · 3 horas**

**Objetivo:** O LLM controla o corpo todo — rodas, olhos e braços.

**Momento "uau":** *"Robô, cumprimenta a avó."* E ele vira-se, acena e diz olá. Ninguém
programou "cumprimentar a avó".

**A Lara faz:**
- Testa ordens diretas e depois **indirectas**, que é onde está a magia:
  - *"Robô, foge!"* → recua
  - *"Estou triste."* → cara triste e aproxima-se
  - *"Dá-me cinco!"* → vê-se o que ele inventa com um braço
- **Anota as ordens que falham** — vai ser a lista de melhorias.

**O pai faz:** Tool calling com validação estrita. Nunca executar uma ação sem verificar os
limites: um `mover(cm=5000)` deve ser **recusado**, não obedecido.

**Critério de pronto:** 8 em 10 ordens faladas resultam na ação certa.

---

### FASE 13 · O corpo grande
**Semana 15 · 4 horas ou mais — é a parte divertida**

**Objetivo:** Deixar de ser uma base de alumínio com fios e passar a ser **o AstroSonda —
uma personagem de ~38 cm**.

**Momento "uau":** Deixa de ser "o robô do projeto" e passa a ser *aquele boneco*. As
pessoas reconhecem-no antes de ele dizer uma palavra.

**A Lara faz:**
- Volta ao desenho da fase 0 e decide a versão final (ver §11 para as sete regras de forma).
- Constrói o corpo. **Cartão + cola quente primeiro. Sempre.** Duas horas em cartão ensinam
  mais sobre o que corre mal do que uma semana de CAD.
- Depois de uma semana a usar, corrige — e só então contraplacado ou 3D.
- **Requisito de engenharia:** tem de haver acesso ao interruptor, à bateria, ao cartão SD
  e às portas USB **sem desmontar tudo**. Deixem-na descobrir isto sozinha.

**O pai faz:** Organiza os cabos, verifica a ventilação do Pi, e o arranque automático
(`sudo systemctl enable robo`).

**Critério de pronto:** Liga-se o interruptor, não se toca em mais nada, e passados 40
segundos o robô diz "olá" sozinho e acena. Aguenta 3 horas de bateria. **E parece o
AstroSonda** — cabeça grande, olhos azuis num visor escuro, base a brilhar.

---

### FASE 14 · Personalidade — e a mudança para a secretária
**Semana 16 · 4 horas (duas sessões)**

**Objetivo:** Deixar de ser uma demo técnica e passar a ser *aquele robô* — o que vive na
mesa dela.

**Momento "uau":** A Lara está a fazer os trabalhos de casa, levanta os olhos, e o robô
está a bocejar.

**A Lara faz:**

*Sessão A — os sensores de toque.* Três TTP223 em GPIO 4, 16 e 26 — cabeça, costas e
frente. Descobrir o que cada toque deve fazer. É a peça de €6 que muda mais o robô do
projeto todo (D16).

*Sessão B — as atividades.* Abrir `robot/brain/companion.py`, ver a tupla `ATIVIDADES`, e
**acrescentar as dela**. Bocejar, espreitar, espreguiçar-se, distrair-se e dar uma
voltinha já lá estão. Faltam as que só ela vai lembrar-se.

```python
def _fazer_ginastica():
    arms.gesto("espreguicar")
    eyes.expressao("contente")

ATIVIDADES = ATIVIDADES + (("ginástica", _fazer_ginastica),)
```

Também:
- **Reações a pessoas específicas** — cumprimentar a Lara de forma diferente do pai.
- **Modo offline** — quando o Mac está desligado: olhos a dormir e 5 frases gravadas.
- **Jogos** — escondidas, Simão diz (agora com braços!), adivinhas.

**O pai faz:** `companion.py` e `attention.py` já estão escritos. O que falta é montar os
TTP223 e afinar os números do bloco `secretaria:` do `robot.yaml` — sobretudo
`segundos_ate_atividade` e `arrefecimento_saudacao_s`, que são os dois que decidem se o
robô é companhia ou chatice.

⚠️ **Antes de o pôr na mesa pela primeira vez:** `python scripts/test_companion.py`. Ele
recusa-se a dar luz verde se os sensores de precipício não responderem, e mostra o teto de
velocidade em vigor.

**Critério de pronto:** O robô passa uma hora na secretária ao lado da Lara a estudar, sem
a interromper uma única vez, e ela olha para ele pelo menos três vezes porque ele fez
alguma coisa.

**Conversa importante:** *"O que é que faz uma coisa parecer viva?"* O Eilik não tem
câmara. Não sabe quem tu és. E é o que as pessoas acham mais vivo. Porquê?

---

### FASE 15 · Mostrar ao mundo
**Semana 17 · 2 horas**

**A Lara faz:** Vídeo de 2 minutos (ela apresenta), README com as fotos das fases, e — se
quiser — apresentação na escola. Um robô que reconhece o professor e acena é imbatível
numa aula.

**Critério de pronto:** Existe um vídeo. O código está no Git com o nome dela nos commits.

---

### FASE 16 · "Segue-me"
**Depois da fase 15 · 5–6 horas (três sessões)**

**Objetivo:** O robô anda atrás da Lara pela casa. Foi ela que pediu.

**Momento "uau":** Ela levanta-se da secretária, diz *"segue-me"*, e ele vai atrás.

**⚠️ Pré-requisitos, sem exceção:**

- Fase 7 completa: ultrassons e precipício montados, testados e calibrados
- A velocidade real do robô **medida** (fase 6), não estimada
- Um **VL53L1X apontado ao chão 30 cm à frente**, com XSHUT para lhe mudar o endereço
- **Barreira física nas escadas**

**A Lara faz:**

*Sessão A — porque é que ele te perde?* Corre o detetor de caras e anda pela sala a virar
as costas. Descobre sozinha que o robô só a vê de frente. É o momento em que se percebe
porque é que "seguir" é diferente de "ver".

*Sessão B — o tracker.* Trocar o detetor por um `cv2.TrackerKCF`, semeado com a caixa da
cara. Ver quantos segundos ele aguenta antes de se perder, e o que o faz perder-se.

*Sessão C — afinar.* Os números do bloco `seguir:` do `robot.yaml`: `zona_morta` (treme?),
`ganho_rotacao` (curva de mais?), `area_parar` (chega demasiado perto?).

**O pai faz:** O segundo VL53L1X com XSHUT, a lógica de deteção de degrau por salto de
distância, e a barreira nas escadas.

**Critério de pronto:** Segue-a de uma ponta à outra do corredor sem bater e sem se perder.
**E para nas escadas, dez vezes em dez.**

**Conversa importante:** *"Porque é que é mais difícil seguir alguém do que reconhecê-la?"*
A resposta — que reconhecer é uma fotografia e seguir é um filme, e que a maior parte do
filme é de costas — é uma das ideias mais úteis do projeto todo.

---

## 8. Arquitetura do software

### 8.1 Estrutura

```
my-robot/
├── config/
│   ├── robot.yaml          ← nome, pinos, limites, IP do Mac
│   ├── expressoes.yaml     ← AS CARAS (a Lara edita isto)
│   └── personalidade.txt   ← o system prompt (a Lara edita isto)
├── firmware/
│   └── bot_face_esp32/     ← o renderizador da cara, para o ESP32
├── robot/
│   ├── hardware/
│   │   ├── motors.py       ← frente(), virar(), parar()
│   │   ├── arms.py         ← acenar(), apontar(), garra()
│   │   ├── eyes.py         ← expressao("feliz") → uma linha para o ESP32
│   │   ├── sensors.py      ← distancia(), precipicio()
│   │   └── power.py        ← bateria_pct(), tensao()
│   ├── perception/         ← camera.py, faces.py
│   ├── voice/              ← speak.py, listen.py, wakeword.py
│   ├── brain/              ← llm.py, tools.py, state.py
│   ├── expressions.py      ← lê as caras do YAML e valida-as
│   ├── gestures.py         ← os gestos dos braços (edita a Lara)
│   └── main.py
├── scripts/                ← um teste isolado por peça
└── data/faces/             ← assinaturas (NÃO vai para o Git)
```

### 8.2 Quatro regras de design

**R1 · Cada peça de hardware tem um script de teste isolado.** Quando algo falha às 22h de
domingo, tem de ser possível responder a "é o hardware ou é o código?" em 30 segundos.

**R2 · As funções que a Lara usa têm nomes em português e uma só responsabilidade.**
`falar("olá")`, `frente()`, `acenar()`. A camada complicada existe, mas está escondida.

**R3 · Uma falha tem um estado seguro.** Sem rede, não há novas ordens faladas. Sem uma
leitura de segurança necessária, o movimento autónomo fica bloqueado. O erro é explicado
sem mostrar um *stack trace* à Lara.

**R4 · A segurança física manda mais que o LLM.** Se o modelo mandar andar para a frente e
o sensor disser que há uma parede, ganha o sensor.

### 8.3 Configuração num sítio só

Tudo o que é ajustável vive no `config/robot.yaml`, para a Lara mudar comportamento sem
tocar em lógica: velocidade, limites dos servos, limiar das caras, tempo até adormecer,
distância mínima de segurança.

---

## 9. O que a Lara aprende em cada fase

Isto não é um projeto de eletrónica com um bocado de código. É um currículo disfarçado.

| Fase | Competência técnica | Ideia mais funda |
|---|---|---|
| 0 | Especificação, inventário | Definir o problema antes de o resolver |
| 1 | Linha de comandos, SSH, redes | Computadores falam uns com os outros |
| 2 | Instalar pacotes, chamar funções | Podes usar trabalho de milhares de pessoas |
| 3 | Estruturas de dados (matrizes) | **Dados e desenhos são a mesma coisa** |
| 4 | Multímetro, continuidade, engenharia inversa | **Descobre-se o que não está documentado** |
| 5 | Tensão, corrente, fusíveis, reguladores | A energia é um sistema, não um fio |
| 6 | Ciclos, funções, depuração física | O mundo real não obedece ao código |
| 7 | Sensores, ciclo de controlo, calibração | Autonomia = perceber + decidir + agir |
| 8 | Servos, ângulos, limites mecânicos | Software que mexe em coisas parte coisas |
| 9 | Visão por computador, *embeddings* | Um rosto pode virar 128 números |
| 10 | Áudio, latência, falsos positivos | Nenhum sistema acerta sempre |
| 11 | APIs, HTTP, prompts | **Um LLM convence-se, não se comanda** |
| 12 | *Tool calling*, validação | Nunca confiar em input sem verificar |
| 13 | Design, prototipagem, iteração | Cartão antes de CAD |
| 14 | Máquinas de estados, UX | A personalidade é engenharia |
| 15 | Documentação, comunicação | Trabalho não partilhado não conta |

### Quatro conversas para ter pelo caminho

**Fase 4 — Engenharia sem manual.** *"A Makeblock não nos diz o que faz cada fio. Vamos
descobrir."* Poucas coisas dão mais confiança a uma criança do que isto.

**Fase 9 — Privacidade.** *"Este robô conhece a tua cara. Quem é que devia poder decidir
isso?"*

**Fase 11 — O que é um LLM.** Mudem o system prompt à frente dela. **Provoquem uma
alucinação de propósito** — perguntem algo muito específico sobre a família e vejam-no
inventar com toda a confiança. É a melhor vacina possível contra confiar cegamente em IA.

**Fase 12 — Autonomia e limites.** *"Se ele pode andar e mexer os braços sozinho, quem é
responsável quando parte alguma coisa?"*

---

## 10. Segurança

### 10.1 Elétrica

| Regra | Porquê |
|---|---|
| **Química LiFePO4** | Sem fuga térmica auto-alimentada. Ver D9 |
| **Carregar sempre FORA do robô**, com o carregador próprio | Nunca deixar a carregar sem vigilância |
| Fusível de 10 A no positivo, antes de tudo | €0,50 de seguro |
| Fusível por ramal (3 A / 5 A / 5 A) | Isola a falha |
| Conectores XT30/XT60, nunca fios nus | Não se inverte polaridade por acidente |
| Desligar a bateria antes de mexer em fios | Regra absoluta, sem exceções |
| Ferro de soldar: **ver §10.5** | A regra mudou — não é a idade, é o comportamento |
| Verificar polaridade 2× antes de ligar | Um `+`/`−` trocado mata um Pi de €95 |
| Ajustar os reguladores **antes** de ligar a carga | 12,8 V no Pi é fatal |
| HC-SR04**P**, não HC-SR04 | O normal devolve 5 V e queima o GPIO |
| Servos **nunca** nos pinos de 5 V do Pi | Ver D10 |

### 10.2 Física

- **Botão de emergência** que corta a potência dos servos e motores — mas não a do Pi. Não
  é código, é um fio cortado. Código pode ficar pendurado.
- `atexit` a parar motores e a relaxar servos quando o programa termina, por qualquer razão.
- *Timeout* de movimento: nenhum comando dura mais de 3 s sem ser renovado.
- Velocidade máxima limitada a 60% no código. Um robô de 2 kg a toda a velocidade parte-se.
- **Limites de ângulo por servo**, do `robot.yaml`. Um ângulo absurdo parte a mecânica ou
  queima o servo contra o batente.
- **Braços param se alguém estiver muito perto** — a garra fecha com força suficiente para
  fazer doer num dedo pequeno.
- ⚠️ **NA SECRETÁRIA, a queda é o risco número um.** 75 cm de altura chegam para partir o
  painel, a câmara ou um servo. Três defesas, por esta ordem: velocidade limitada a 25% no
  `_limitar()` dos motores (por onde passa tudo, incluindo ordens do LLM); atividades
  ociosas que só rodam no sítio, nunca andam em frente; e os três sensores de precipício.
  **Correr `python scripts/test_companion.py` antes da primeira vez em cima da mesa.**

### 10.5 Soldadura — os factos, sem alarmismo

**O chumbo não evapora.** Funde a 327 °C e ferve a **1749 °C**; nós soldamos a 350. A via
de exposição real é **mão-boca**, não o ar — o serviço de segurança da Universidade de
Columbia é explícito: *"the primary route of exposure to lead from soldering is
ingestion"*. **Lavar as mãos com sabão a seguir resolve quase tudo.**

Mesmo assim, a lista de compras leva **solda sem chumbo**. Funde a 217 °C em vez de 183 e
molha um pouco pior, mas apaga uma preocupação inteira numa casa com crianças — e é o que
o manual de segurança da FIRST Robotics exige.

**O fumo que se vê é o fluxo, não o metal — e esse é o risco a sério.** A HSE britânica
classifica o fumo de colofónia como *"a common cause of occupational asthma"*, e a
sensibilização é **permanente**: uma vez sensibilizado, doses mínimas desencadeiam crise.

**As três medidas, por ordem de eficácia por euro:**

| # | Medida | Custo |
|---|---|---|
| 1 | **Não se debruçar sobre a junta** | €0 — e é o maior ganho isolado |
| 2 | Janela aberta + ventoinha a **puxar** o ar para longe das caras | ~€12 |
| 3 | Extrator com filtro de carvão, e só serve a 10–15 cm da junta | ~€30 |

**Regras de casa:**

- Ferro **sempre no suporte**, cabo longe da borda da mesa
- Cabelo apanhado, sem mangas largas
- **Óculos de proteção** — o risco ocular real não é o fumo, é o terminal cortado a saltar
- Nada de comer nem beber na bancada. Lavar as mãos a seguir
- Limpar a bancada com **pano húmido**, nunca varrer
- Nunca deixar o ferro ligado sem vigilância
- Queimadura: água fria corrente, 20 minutos

**E quando é que a Lara solda?** Não é a idade — é isto:

> Ela pode soldar quando puser o ferro no suporte de forma fiável entre juntas, **sem ter
> de se lembrar**. Testa-se na placa de prática da fase 0.5.

### 10.3 Dados e privacidade

Estamos a construir um aparelho com câmara e quatro microfones, usado por uma menor, dentro
de casa. Este ponto merece atenção a sério.

| Princípio | Implementação |
|---|---|
| **Nada sai de casa** | Toda a IA corre no Pi ou no Mac. Zero cloud |
| **Não guardar áudio** | Transcrito e descartado. Nunca escrito em disco |
| **Assinaturas, não fotos** | 128 números por pessoa, não imagens |
| **Consentimento explícito** | Só se regista quem disser que sim, sabendo o que é |
| **Direito a ser apagado** | `python scripts/enrol_face.py --apagar Nome` |
| **Nada de caras no Git** | `data/faces/` está no `.gitignore` |
| **Indicador visível** | Quando a câmara vê, os olhos mostram um ponto. Um aparelho que observa deve mostrar que observa |
| **Controlo de privacidade** | *"Para de olhar"* é comparado no Pi antes do LLM, mas depende da transcrição do mini. Um controlo físico continua a ser a forma independente da rede |
| **Dados entre Pi e mini** | O áudio da conversa segue para o mini dentro da rede privada. Imagens e assinaturas de rosto permanecem no Pi |

### 10.4 Conteúdo do LLM

- System prompt restritivo: temas adequados, respostas de 3 frases, admitir quando não sabe.
- Opcional: **Llama Guard 4** no Mac como segundo passo de verificação.
- **Modo pais:** ficheiro de tópicos proibidos, verificado antes de enviar ao LLM.
- Explicar à Lara que o robô pode dizer coisas erradas. Ela é a supervisora.

---

## 11. O aspeto — AstroSonda

O robô vai ter o visual do **Astro Bot**, o mascote da PlayStation. Mas não é uma
réplica: é uma **variante própria** — a versão **sonda espacial**, com rodas em vez de
pernas. No jogo o Astro tem dezenas de fatos (macaco, mergulhador, piloto); o de sonda
ainda não existe, e só vai existir depois de a Lara o desenhar.

**Isto não é decoração — é o que torna o projeto dela.** Um robô genérico é um trabalho
de escola. Um AstroSonda que ela inventou é uma coisa que ela vai querer mostrar.

> A folha de design com os desenhos, as cores e as proporções está em
> **`design-astrosonda.html`**. Imprimam-na e deixem-na desenhar por cima.

### 11.1 As sete decisões de forma

| # | Regra | Porquê |
|---|---|---|
| 1 | **Cabeça enorme** — ~40% da altura total | A Team Asobi desenhou-o com proporções de bebé: cabeça grande, barriga redonda, centro de gravidade baixo. Se parecer exagerada, está certa |
| 2 | **Não tem boca** | Tudo é dito com a **forma dos olhos**. É por isso que uma matriz 8×8 chega |
| 3 | **Azul é a cor base — o vermelho é para ícones** | Um olho inteiro vermelho é a linguagem dos inimigos; um coração vermelho está certo. O painel é RGB, portanto a regra vive no `expressoes.yaml`, não no hardware |
| 4 | **Faceplate escuro** | Acrílico preto de difusão, 2–3 mm, ~18% de transmissão: esconde a eletrónica apagada, deixa passar os LEDs |
| 5 | **Braços finos e escuros** | Os membros do Astro **não flutuam** — são finos, escuros, com articulações prateadas. O servo esconde-se na ombreira branca |
| 6 | **A base é a assinatura da variante** | Onde ele tem pernas, a sonda tem uma base com anel de LEDs azuis. As rodas ficam meio escondidas: lê-se como propulsor, não como carrinho |
| 7 | **Calote cromada e antena** | O topo espelhado e a antena curta são marcas do personagem. Custam quase nada e mudam a silhueta toda |

### 11.2 As cores

| Onde | Cor | Como fazer |
|---|---|---|
| Corpo, cabeça, mãos | `#F4F6F8` branco | Filamento PLA branco |
| Painéis do peito, cabeça, ombros | `#1E7FD4` azul | PLA azul, peças separadas aparafusadas |
| Propulsores e olhos | `#4FC3E8` azul-ciano | LEDs azuis atrás de acrílico |
| Faceplate e braços | `#161B22` quase preto | Acrílico preto de difusão (~170×90 mm) · varão preto |
| Calote do topo, cotovelos | cromado | Vinil espelhado ou tinta cromada |

⚠️ **Não existem códigos de cor oficiais da Sony** para o Astro. Estes vieram de amostrar
imagens do jogo — se a Lara quiser afinar, é pôr o jogo em pausa e usar um conta-gotas.

### 11.3 Onde vive cada peça

| Peça | Onde | Porquê |
|---|---|---|
| Painel HUB75 64×32 | Atrás do faceplate, na cabeça | É a cara |
| ESP32 | Ao lado do painel, dentro da cabeça | Desenha — cabo USB até ao Pi |
| Câmara | No faceplate, entre e abaixo dos olhos | O escuro esconde-a |
| **Array de 4 microfones** | **Topo da cabeça**, sob a calote cromada perfurada | O mais longe possível dos motores — ver D6 |
| Coluna | Peito, atrás do painel azul perfurado | A grelha faz parte do desenho |
| Raspberry Pi + protoboard | Corpo | Acesso pelas costas |
| Bateria | **Base, o mais baixo possível** | É a peça mais pesada — baixa o centro de gravidade |
| Servos dos ombros | Dentro das ombreiras brancas | Escondidos, como no Astro |
| Rodas do mBot2 | Dentro da base | Meio escondidas atrás do anel de luz |

### 11.4 Requisitos de engenharia que a estética não pode quebrar

| # | Requisito |
|---|---|
| DC1 | Câmara a ~25–30 cm do chão, ligeiramente inclinada para cima — as pessoas estão acima do robô |
| DC2 | Microfones no topo e **longe dos motores** |
| DC3 | Acesso ao interruptor, à bateria, ao cartão SD e ao USB **sem desmontar** |
| DC4 | Ar a circular à volta do Pi e dos reguladores — ambos aquecem |
| DC5 | Ombros com amplitude para os braços não baterem no corpo |
| DC6 | Cabos presos, nada perto das rodas nem das juntas |
| DC7 | Peso total < 2,5 kg |

⚠️ **O PLA amolece aos ~60 °C.** Para peças que toquem no Pi ou nos reguladores, usar
**PETG** (~80 °C). E um robô branco esquecido ao sol de verão, em Portugal, empena.

### 11.5 Método: cartão primeiro, sempre

```
1. Cartão + cola quente          (2 h)   ← descobrir o que está errado
2. Usar 1 semana                          ← descobrir o resto
3. Corrigir em cartão            (1 h)
4. Só agora: impressão 3D
```

Quase toda a gente quer saltar para o passo 4. É por isso que quase toda a gente faz uma
carcaça bonita que não deixa aceder ao cartão SD. **Uma cabeça em cartão demora duas
horas; uma cabeça impressa demora um fim de semana e não se corrige.**

### 11.6 Nota legal, curta

O Astro Bot é da Sony Interactive Entertainment. Para um projeto de família não há
problema nenhum — mas há quatro regras simples:

- **Não vender** o robô, nem cópias, nem aceitar encomendas
- **Não distribuir** ficheiros 3D derivados de recursos extraídos do jogo
- **Não usar** logótipos PlayStation/Sony nem apresentá-lo como produto oficial
- Se publicarem fotos ou vídeo, identifiquem como **projeto pessoal / fan art**

O facto de ser uma **variante própria** já vos afasta da réplica — é o caminho certo, e é
também o mais divertido.

## 12. Riscos e planos B

> Esta tabela pertence ao desenho histórico. A pinagem dos motores, os
> encoders ligados ao GPIO e o Whisper no Pi já não são riscos da arquitetura
> atual. Os riscos abertos estão em `docs/decisoes-atuais.md` e
> `docs/roteiro.md`.

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| **Pinagem dos motores do mBot2 não bate certo** | Média | Alto | Medir na fase 4 **antes** de cortar. Plano B: chassis 2WD de €13 + motores TT |
| **Encoders a 5 V queimam o GPIO** | Média | Alto | Medir a tensão antes de ligar. Level shifter se necessário |
| **Bibliotecas de Pi 4 não funcionam no Pi 5** | Alta | Alto | Já resolvido: tudo por I2C, `gpiozero`+`lgpio`. Nunca `RPi.GPIO` |
| **Falta o cabo CSI adaptador** | Alta | Médio | Está na encomenda 1 |
| **Servos fazem o Pi reiniciar** | Média | Alto | Barramento próprio + 2200 µF. Se persistir, regulador dedicado |
| **Stock de LiFePO4 pequeno em PT** | **Alta** | Médio | Confirmar antes da fase 5. Plano B: 3S Li-ion com BMS em caixa rígida |
| **Ligação ao mini indisponível** | Média | Médio | Watchdog fora do ciclo de rede, controlo local, explicação em cache e visão no Pi |
| **Palavra-chave dispara sozinha** | Média | Baixo | Mais amostras negativas; subir o limiar |
| **A Lara perde o interesse** | Média | **Crítico** | Voz e olhos nas primeiras 3 semanas; ela decide a estética; braços a meio, quando o entusiasmo abranda |
| **Fases 4 e 5 são pouco divertidas para ela** | **Alta** | Alto | São duas semanas de bancada a seguir a três de resultados. Dar-lhe o multímetro e as medições — o papel dela nestas fases é ser **a cientista que mede** |
| **Preços sobem outra vez (crise de RAM)** | Média | Médio | Comprar o Pi cedo |
| **O Mac está sempre desligado** | Média | Médio | Modo offline decente (fase 14) |

### Quando alguma coisa não funciona

Ensinar este método à Lara vale mais do que qualquer fase:

1. **É hardware ou software?** Corre o script de teste isolado.
2. **É alimentação?** `vcgencmd get_throttled`. Mede as tensões com o multímetro.
3. **Já funcionou alguma vez?** Se sim, o que mudou desde então?
4. **Divide ao meio.** Comenta metade do código. O erro está na metade que ficou?
5. **Lê a mensagem de erro até ao fim.** A resposta está lá 80% das vezes.
6. **Explica o problema em voz alta ao robô.** A sério — funciona. Chama-se *rubber duck
   debugging*, e agora o pato tem olhos de LED e acena.
7. Só agora: procurar na Internet.

---

## 13. A impressora 3D — investimento futuro

Não é preciso para começar. A encomenda 4 tem **€40 de serviço de impressão** para as
primeiras peças, e o corpo faz-se em cartão até à fase 13. Mas se o projeto pegar, a
impressora muda a natureza do trabalho.

### 13.1 Porquê comprar, e não encomendar

Para **um** robô, encomendar sai mais barato. Mas o projeto não é sobre obter peças — é
sobre **iterar**: imprimir, ver que não encaixa, corrigir, reimprimir no dia seguinte.
Com um serviço externo cada iteração custa dias e dinheiro, e o projeto morre à segunda
tentativa. **Uma criança que pode errar de graça experimenta dez vezes mais.**

### 13.2 A escolha

**Bambu Lab P1S — €379.** Fechada, 256×256×256 mm, filtro de carvão ativado, e o
ecossistema mais fácil do mercado para quem começa.

| Alternativa | Preço | Veredicto |
|---|---|---|
| **Bambu Lab A1** | €259 | Excelente máquina, mas **aberta**. Os €120 extra da P1S compram uma barreira física à volta de um bico a 250 °C, com uma criança de 11 anos por perto |
| **Bambu Lab A1 mini** | €189 | ⚠️ **Evitar.** 180×180×180 obriga a partir a cúpula da cabeça em 4–6 gomos — muitas juntas a lixar e colar, e frustração garantida |
| **Elegoo Centauri Carbon 2 Combo** | €379 | Fechada e já com multicor. A melhor relação preço/valor de 2026, se não fizerem questão do ecossistema Bambu |
| **Bambu Lab P2S** | €519 | A P1S melhorada (out/2025). Melhor, mas não o suficiente para justificar +€140 aqui |
| **Prusa MK4S** | ~€719 | Fabricante europeu, open-source, peças e apoio na UE. Fora do que este projeto precisa |

### 13.3 Multicor: **não vale a pena** neste projeto

Parece a resposta óbvia para um robô branco e azul. Não é.

O AMS lite custa +€110 (combo a €489) e **desperdiça ~8 g de filamento por cada troca de
cor**. Numa peça pequena com 8 trocas, **81% do filamento vai para o lixo**.

Mas as nossas peças são **grandes e de uma só cor**: a cúpula é branca, o painel do peito
é azul. Troca-se o rolo à mão entre peças — dois minutos. **O multicor só compensaria
para detalhes de várias cores dentro da mesma peça**, que aqui não existem.

### 13.4 Segurança — a parte que interessa

Um relatório da UL Chemical Insights, feito em salas de aula, mediu em impressoras FDM
**mais de 200 compostos orgânicos voláteis distintos**, incluindo formaldeído acima do
dobro do limite recomendado da Califórnia. E o PLA, apesar de ser o mais limpo, emitiu
**3,4×10⁸ partículas ultrafinas por hora** — que uma medição por massa subestima. O
relatório avisa explicitamente para crianças.

Ou seja: **o PLA é o mais seguro, mas não é "seguro sem cuidados".** Cinco regras:

1. **Impressora fechada.** A caixa é uma barreira física contra queimaduras, contém a
   maior parte das partículas e reduz muito o ruído.
2. **Não no quarto dela.** Garagem, arrumos, ou escritório com janela. Se tiver de ser
   numa divisão habitada, um purificador HEPA+carvão ao lado (€80–150).
3. **Só PLA e PETG.** Nada de ABS ou ASA em casa sem extração para o exterior.
4. **A criança carrega o ficheiro e vê pela câmara.** Só abre a tampa depois de arrefecer.
5. Nota: o filtro de carvão da P1S trata dos COVs, **mas não é HEPA** — não apanha as
   partículas ultrafinas. Daí a regra 2.

### 13.5 Custo real

| | |
|---|---|
| Impressora P1S | €379 |
| Filamento inicial (PLA branco + PLA azul + PETG) | ~€45 |
| **Total para arrancar** | **~€424** |
| O robô inteiro consome | 1,5–2,5 kg → €25–40 |
| Eletricidade | ~€0,02/hora — desprezável |
| Desgaste (bicos, placas, correias) | €40–60/ano |

⚠️ **Uma metade de cúpula demora 8 a 20 horas a imprimir.** Uma cabeça completa é um fim
de semana. Digam isto à Lara **no primeiro dia** — a expectativa errada aqui estraga a
experiência toda.

### 13.6 Antes de comprar

O **FabLab Porto** (Rua António Carneiro 302-R, seg–sex 14h–20h) e o **FabLab Lisboa**
deixam ver máquinas a trabalhar. Uma visita antes de gastar €400 é meia hora bem passada —
e para a Lara, ver uma impressora a construir uma peça camada a camada é o tipo de coisa
que decide um projeto.

---

## 14. Depois de acabar

| Ideia | Dificuldade | Nota |
|---|---|---|
| **Usar os encoders com o ESP32** | ⭐⭐⭐ | Já temos a placa e os fios ligados. 8 unidades PCNT em hardware. Anda mesmo a direito e mede distância |
| Olhos a cores (GC9A01) | ⭐ | €31, transformação visual completa |
| Comando por telemóvel | ⭐⭐ | Servidor web no robô |
| ~~Seguir uma pessoa~~ | — | **Deixou de ser opcional: virou a FASE 16.** Ver D17 |
| **Modo noturno (2ª câmara, IR)** | ⭐⭐ | €21,90. O Pi 5 tem duas entradas CSI — entra ao lado da Camera Module 3, sem substituir nada (D4b) |
| **CAN bus entre o Pi e o ESP32** | ⭐⭐⭐ | Temos duas placas com CAN. "A linguagem que os carros falam" |
| Modelo AMÁLIA para conversa em pt-PT | ⭐ | O LLM feito em Portugal |
| **Robô sem o Mac ligado** | ⭐⭐⭐ | LLM pequeno no próprio robô, para o levar à escola. Antes de comprar acelerador, ler o D8b: sai mais barato e mais rápido um Pi 5 de 16 GB |
| Base de carga automática | ⭐⭐⭐⭐ | Contactos + marcador visual |
| Mapa da casa (SLAM) | ⭐⭐⭐⭐⭐ | LIDAR ~€100, muito software |
| Dois robôs a comunicar | ⭐⭐⭐ | O melhor projeto se houver um amigo com outro |

---

## Apêndice A · Comandos de emergência

> Lista histórica. Os comandos de I2C e reSpeaker abaixo não descrevem o
> hardware atual. O mBot2 liga por USB e a cadeia de áudio ainda não foi
> escolhida.

```bash
ping robo.local                   # está vivo?
ssh lara@robo.local               # entrar
sudo systemctl stop robo          # PARAR TUDO
journalctl -u robo -n 100         # o que correu mal?
python scripts/check_health.py    # verificação completa

i2cdetect -y 1                    # 0x40 motores · 0x41 servos · 0x29 ToF · 0x48 bateria
ls /dev/ttyUSB* /dev/ttyACM*      # o ESP32 da cara
rpicam-hello --list-cameras       # câmara (tem de aparecer um imx708)
aplay -l                          # o reSpeaker aparece? "card N: Array [reSpeaker XVF3800 ...]"
speaker-test -c2 -t wav           # coluna (ligada ao reSpeaker, não ao Pi)

vcgencmd measure_temp             # temperatura
vcgencmd get_throttled            # 0x0 = alimentação OK
python scripts/test_power.py      # tensão e percentagem da bateria

curl http://mac.local:11434/api/tags   # o Mac serve o LLM?
```

## Apêndice B · Instalação de raiz

> Instalação histórica. Não a executar inteira. Instala modelos de visão no Pi
> e configura um reSpeaker que não pertence ao inventário atual. No destino, o
> Pi executa a palavra-chave, YuNet e SFace. STT, LLM e TTS correm no mini.

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git python3-venv python3-pip i2c-tools \
     avahi-daemon libnss-mdns libportaudio2 ffmpeg \
     python3-lgpio python3-gpiozero
sudo apt install -y --no-install-recommends python3-picamera2   # a câmara: só pelo apt
sudo raspi-config    # Interface Options → I2C ✓ SPI ✓

# /boot/firmware/config.txt — só a partir da fase 5 (bateria):
#   usb_max_current_enable=1
# (Não há dtparam=i2s nem dtoverlay=hifiberry-dac: o som sai pelo reSpeaker, por USB.)

# /etc/asound.conf — o reSpeaker é a placa de som por omissão (coluna E microfones):
#   defaults.pcm.card Array
#   defaults.ctl.card Array

git clone <repo> ~/my-robot && cd ~/my-robot        # ou rsync a partir do Mac
python3 -m venv --system-site-packages .venv         # ⚠️ sem a flag, o picamera2 não existe
source .venv/bin/activate
pip install -r requirements.txt                      # ~10 min: whisper, opencv, onnxruntime
pip install --no-deps "openwakeword>=0.6.0"          # ⚠️ --no-deps: ver requirements.txt
python scripts/download_models.py   # YuNet e SFace (a voz vem do Mac)
python scripts/check_health.py
```

⚠️ **O `--no-deps` do openwakeword não é opcional.** A versão 0.6.0 declara o
`tflite-runtime` como dependência obrigatória no Linux, e esse pacote morreu no Python
3.11 (última versão em novembro de 2023). Com o Python do Pi (3.13/3.14) o `pip` desiste
da lista *inteira* por causa dele. Nós só usamos o backend ONNX, por isso instala-se
sem as dependências dele e as que interessam (onnxruntime, scipy, scikit-learn, tqdm) já
estão no `requirements.txt`. Pelo mesmo motivo o `lgpio` vem do `apt` e não do `pip`.

💡 O nome do Mac na rede não é `mac.local` — é o que o `scutil --get LocalHostName` disser
no Mac, seguido de `.local`. Põe-no em `config/robot.local.yaml` (não vai para o Git):

```yaml
llm:
  host: "NOME.local"
voz:
  servidor: "http://NOME.local:8420/falar"
```

Sem isto o `check_health.py` e o robô *parecem* encravar: cada tentativa de falar com o
Mac espera pelo mDNS e pelo DNS antes de desistir. Em qualquer script, `Ctrl+C` mostra a
linha exata onde estava à espera.

---

*Plano v2, elaborado a 15 de agosto de 2026. Preços verificados nessa data em lojas
portuguesas, alemãs, britânicas e polacas — confirmar antes de encomendar, sobretudo o
Raspberry Pi e o pack LiFePO4.*

*Revisão de 25 de agosto de 2026 (o Pi, a câmara e o Active Cooler chegaram): o som passa
a sair pelo reSpeaker XVF3800, que sobe para a encomenda 1, e o amplificador I2S MAX98357A
sai do plano (D6, fase 2, §5, §6); a coluna é a da Botnroll; o venv no Pi leva
`--system-site-packages` (Apêndice B); `libcamera-hello` passou a `rpicam-hello`. Mais
tarde no mesmo dia, ao instalar no Pi: o `openwakeword` passa a instalar-se com `--no-deps`
(o `tflite-runtime` não existe para Python ≥3.12) e o `lgpio` vem do `apt`; o
`check_health.py` verifica primeiro se o nome do Mac existe na rede, em vez de encravar.*
