# Visão no Raspberry Pi

Guia de arranque da visão, do cabo até "Olá, Lara!".

Este guia pressupõe o Pi 5 já instalado, com o projeto e o venv, e acesso por
SSH sem monitor. A captura, YuNet e SFace correm no Pi. O código está em
`robot/perception/camera.py`, `faces.py` e `attention.py`.

---

## Antes de mexer: as duas coisas que te vão enganar

**1 · O `ROBO_SIMULAR`.** Se estiver a `1` no ambiente do Pi (ficou de fases
anteriores), o `test_camera.py` responde `câmara → foto simulada` e devolve
`None` — exatamente como se a câmara estivesse avariada. Confirma antes de
suspeitares do hardware:

```bash
echo "ROBO_SIMULAR=[$ROBO_SIMULAR]"     # tem de vir vazio no Pi
grep -rn ROBO_SIMULAR ~/.bashrc ~/.profile 2>/dev/null
```

O `config.a_simular()` deteta o Pi sozinho pelo `/proc/device-tree/model` — no
Pi não é preciso definir nada. Na dúvida, força: `ROBO_SIMULAR=0 python …`

**2 · O `check_health.py` mentia sobre a câmara.** Procurava o `libcamera-hello`,
que já não existe (desde o Bookworm as ferramentas chamam-se `rpicam-*`). Dava
❌ com a câmara boa **e o texto do erro mandava-te desmontar o cabo CSI**. Já
está corrigido — tenta o `rpicam-hello` primeiro e só depois o antigo.

---

## Passo 0 · Desligar o Pi a sério

O conector CSI **não é hot-plug**. Ligar a fita com o Pi alimentado estraga o
conector, e às vezes a câmara.

```bash
sudo shutdown -h now
```

Espera o LED verde apagar de vez e **tira a ficha**. Só então mexes na fita.

---

## Passo 1 · O cabo

O Pi 5 usa o conector **mini de 22 pinos**; a Camera Module 3 traz o cabo
**standard de 15**. O que faz a ponte é o cabo *Standard–Mini* (é o «cabo
adaptador» dos €4,50 na lista de compras).

**A regra é a mesma nas duas pontas, e é esta:**

> Os **contactos metálicos ficam virados para o lado contrário ao da patilha**
> que se levanta.

Do lado da câmara isso quer dizer contactos virados **para a placa da câmara**
(ou seja, para o lado oposto à lente).

Como se enfia: levantar a patilha, meter a fita **a direito e até ao fundo**,
baixar a patilha. Não dobrar a fita em ângulo vivo — as pistas partem-se por
dentro sem se ver nada por fora.

No Pi 5 há **dois** conectores (`CAM/DISP 0` e `CAM/DISP 1`). Usa o **0** e
deixa o 1 livre — é onde entra a câmara IR se a Lara um dia quiser modo
noturno (secção D4b do plano), sem tirar esta.

---

## Passo 2 · O sistema vê a câmara?

Liga o Pi e, por SSH:

```bash
rpicam-hello --list-cameras
```

Tem de aparecer um **`imx708`**. É este o teste que separa «problema de
hardware» de «problema de software» — enquanto isto falhar, não vale a pena
mexer em Python nenhum.

Uma foto de verdade, sem o projeto pelo meio:

```bash
rpicam-jpeg -o /tmp/teste.jpg -t 2000
ls -la /tmp/teste.jpg
```

**`No cameras available`?** É o cabo, em 9 casos em 10. Por ordem:
mal enfiado (volta a fazê-lo, com força e a direito) → ao contrário (roda a
fita 180° **numa** das pontas) → conector errado. Não é preciso mexer no
`/boot/firmware/config.txt`: o Bookworm deteta a Camera Module 3 sozinho.

---

## Passo 3 · O venv — onde vive o software do robô

⚠️ **O passo 2 ter corrido bem não quer dizer que haja venv nenhum.** O
`picamera2` vem do `apt` e o Python do sistema vê-o sozinho — a câmara
funciona na mesma com o projeto por instalar. Confirma:

```bash
ls -d ~/my-robot/.venv 2>/dev/null || echo "❌ não existe"
```

### Criar

⚠️ **O `--system-site-packages` não é opcional, e é a decisão toda deste
passo.** O `picamera2` só existe pelo `apt`, e um venv normal não o vê. Sem a
flag, a câmara desaparece exatamente no momento em que começas a usar o
projeto — e o erro aponta para o Python, não para o venv.

```bash
# o que TEM de vir do apt, nunca do pip
sudo apt install -y python3-venv python3-lgpio python3-gpiozero
sudo apt install -y --no-install-recommends python3-picamera2

cd ~/my-robot
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
which python                # tem de dar ~/my-robot/.venv/bin/python
```

**Confirma a flag ANTES de instalar seja o que for.** São cinco segundos, e
poupam fazer os dez minutos seguintes para deitar fora:

```bash
python -c "from picamera2 import Picamera2; print('✅ o venv vê a câmara')"
```

Falhou? O venv foi criado sem a flag. `deactivate; rm -rf .venv` e repete.
**Não** tentes `pip install picamera2`: o pacote do PyPI tem o mesmo nome, é
outra coisa, e não fala com o `libcamera` do sistema.

### Instalar

```bash
pip install -r requirements.txt               # ~10 min no Pi
pip install --no-deps "openwakeword>=0.6.0"   # ⚠️ o --no-deps não é opcional
```

O `--no-deps` está explicado no topo do `requirements.txt`: o `openwakeword`
0.6.0 declara o `tflite-runtime` como obrigatório, esse pacote morreu no
Python 3.11, e sem a flag o `pip` desiste da **lista inteira** por causa dele.

💡 **Só queres ver caras hoje?** Para os passos 5 a 9 chegam três pacotes, e
instalam-se em segundos. O resto (voz, áudio, GPIO) fica para quando for
preciso:

```bash
pip install PyYAML "opencv-python-headless>=4.10,<5"
```

⚠️ Repara que o **numpy não está nesta lista, de propósito**. Ele já lá está,
vindo do `apt` com o `python3-picamera2`, e o venv vê-o por causa do
`--system-site-packages`. Pedi-lo ao `pip` obrigava-o a instalar outro por
cima — que é precisamente o choque descrito a seguir. Deixa o `pip` decidir:
o que já estiver satisfeito, ele salta.

### Confirmar que a instalação não partiu a câmara

⚠️ **Isto não é paranoia — é a armadilha clássica do Pi.** O `picamera2` vem
do `apt`, compilado contra o numpy **do sistema**. O `pip install` põe outro
numpy dentro do venv, que passa à frente dele. Se os dois não forem
compatíveis, o `picamera2` deixa de importar: a instalação corre bem, diz
tudo verde, e a câmara morre.

```bash
python -c "import picamera2, cv2, numpy; print('✅ tudo:', cv2.__version__, numpy.__version__)"
```

Se o `picamera2` rebentar **agora** e funcionasse no passo 2, é exatamente
isto. Compara os dois numpy:

```bash
/usr/bin/python3 -c "import numpy; print('sistema:', numpy.__version__)"
python              -c "import numpy; print('venv   :', numpy.__version__)"
```

Versões principais diferentes (1.x contra 2.x) confirmam o diagnóstico. A
solução é o venv ceder — o numpy do sistema é o que o `picamera2` conhece, e
este projeto só usa numpy antigo e aborrecido (`dot`, `mean`, `savez`):

```bash
pip uninstall -y numpy      # o venv volta a ver o do sistema
```

---

## Passo 4 · Os modelos estão no Pi?

⚠️ A pasta `models/` está no `.gitignore`. **O `git clone` não os traz** — no
Mac estão lá, no Pi não.

```bash
cd ~/my-robot && source .venv/bin/activate
python scripts/download_models.py
ls -la models/*.onnx
```

Esperado: `face_detection_yunet_2023mar.onnx` (~230 KB) e
`face_recognition_sface_2021dec.onnx` (~39 MB). O script verifica o sha256 —
um download truncado só daria erro muito mais à frente, ao carregar o ONNX,
com uma mensagem que ninguém liga a isto.

---

## Passo 5 · Ver pelos olhos dela (sem monitor)

```bash
/usr/bin/python3 scripts/ver_camera.py
```

Ele imprime o endereço. Abre no browser do Mac **ou do telemóvel**:
`http://<nome-do-pi>.local:8000`

Corre com o `/usr/bin/python3` de propósito: só precisa do `picamera2` do apt,
não do venv nem do resto do projeto.

👧 **Faz este passo com a Lara ao lado.** É a primeira vez que se vê pelos
olhos da Lylla, e é um momento melhor do que qualquer número no terminal.

---

## Passo 6 · A orientação — não é estética

Se a imagem estiver de pernas para o ar (acontece sempre que a câmara fica
montada com o cabo a sair por cima), confirma primeiro:

```bash
/usr/bin/python3 scripts/ver_camera.py --rodar
```

E depois torna-o definitivo. No `config/robot.yaml`, secção `faces:`,
**acrescenta a linha** (ainda lá não está — o `camera.py` lê a chave com
`False` por omissão):

```yaml
faces:
  limiar: 0.45
  fotos_por_pessoa: 8
  resolucao: [640, 480]
  rodar_180: true        # ← esta
```

⚠️ **Porque é que isto interessa mais do que parece:** o YuNet só encontra
caras **direitas**. Com a imagem invertida ele não se queixa — diz
simplesmente «não vejo ninguém», e vais passar a noite a culpar o modelo, a
luz e o limiar.

---

## Passo 7 · Detetar

> ⚠️ **VOLTA AO VENV AQUI.** O passo 5 usava o `/usr/bin/python3` de propósito
> (só precisava do `picamera2` do apt). Deste passo em diante é preciso o
> OpenCV, que está no venv e **não** no Python do sistema. Correr o do sistema
> dá `No module named 'cv2'` **com a câmara perfeitamente boa** — e a
> tentação é ir mexer no cabo.
>
> ```bash
> cd ~/my-robot && source .venv/bin/activate
> which python          # tem de dar ~/my-robot/.venv/bin/python
> ```

```bash
python scripts/test_camera.py
```

Esperado:

```
   ✅ imagem 640×480
   🔍 1 cara(s) encontrada(s) em 4 ms
      [1] desconhecido  (semelhança 0.00) em (210,140) 180×180px
```

`desconhecido` está **certo** — ainda não ensinaste ninguém. O que importa
aqui é o `1 cara(s)` e o tempo: no Pi 5 o YuNet a 640×480 anda pelos 2–5 ms.

**Vê a imagem e 0 caras?** Por esta ordem: orientação (passo 6) → luz (de
frente para a janela, nunca em contraluz) → distância (60–100 cm) → e só
depois o limiar de confiança do detetor, que está a `0.85` no
`robot/perception/faces.py`, na linha do `FaceDetectorYN.create`. Baixar para
`0.7` apanha mais caras e também mais falsos positivos.

---

## Passo 8 · Ensinar caras

```bash
python scripts/ver_visao.py          # depois abre http://<pi>.local:8001
```

A página mostra o vídeo com as caixas, os nomes, a semelhança e os tempos — e
é lá que se regista uma cara. **O texto da privacidade está na própria página
para ser lido em voz alta**, e o botão só desbloqueia depois de alguém
confirmar que a pessoa concordou.

⚠️ **Porque é que isto não se faz pelo terminal.** Quem está a posar está
virado para a **câmara**, de costas para o ecrã — nunca chega a ler «vira-te
para a esquerda». A primeira versão tinha uma contagem 3-2-1 e metade das
fotos saía com a pose errada. Na página, a instrução está ao lado do vídeo, a
Lara vê a própria cara com a caixa à volta, e é ela que carrega em
**Capturar** quando está pronta. Sem pressa, e sem ninguém a ler nada de
costas.

São 8 fotos com poses diferentes; precisa de pelo menos **3 boas**.

O `scripts/enrol_face.py` continua a existir para quando só há terminal — e já
não tem contagem: espera pelo Enter em cada pose.

⚠️ **Regista pelo menos duas pessoas** (tu e a Lara). Com uma cara só no
ficheiro o teste não prova nada: o `identificar()` compara com quem conhece e
devolve o melhor — se só houver um, é sempre esse. Um falso positivo e um
acerto ficam iguais. **Duas pessoas é o mínimo para o número significar
alguma coisa.**

---

## Passo 9 · O teste a sério

```bash
python scripts/test_camera.py --continuo
```

Passa à frente, afasta-te, vira-te de lado, põe as duas pessoas juntas, e vê
o nome e a **semelhança** ao vivo.

**Critério de pronto:** reconhece 4 pessoas em 5 tentativas cada e diz "não te
conheço" a um estranho. O teste continua a passar com o mini desligado.

**Como se afina o limiar** (`faces.limiar`, agora `0.45`):

| O que vês | O que fazer |
|---|---|
| Lara sai a 0,40–0,44 quase sempre | Volta a registar com mais luz **antes** de baixar o limiar |
| Um estranho sai acima de 0,45 | Sobe para 0,50 |
| Troca a Lara por ti | Regista os dois outra vez, com fundos e luzes diferentes |

O valor oficial do OpenCV é **0,363**; não desças abaixo disso. É muito pior
chamar «Lara» a uma visita do que dizer «não te conheço» à Lara.

---

## Passo 10 · O diagnóstico completo

```bash
python scripts/check_health.py
```

Câmara ✅, YuNet ✅, SFace ✅ e as pessoas conhecidas. É este o comando a
correr sempre que alguma coisa parecer estranha, **antes** de mexer em código.

---

## Quando corre mal — tabela rápida

| Sintoma | Causa mais provável |
|---|---|
| `No cameras available` | Cabo ao contrário ou mal enfiado. Contactos para o lado contrário da patilha |
| `Could not open any dmaHeap device` — e **com `sudo` funciona** | Não é o cabo. Falta o grupo `video` ao teu utilizador. Ver o quadro dos grupos, a seguir |
| `câmara → foto simulada` | `ROBO_SIMULAR=1` no ambiente |
| `No module named picamera2` | Venv sem `--system-site-packages` — ou não há venv nenhum (passo 3) |
| `No module named 'cv2'` **depois** de `✅ imagem 640×480` | Python errado. **Não é o cabo** — a câmara acabou de dar uma imagem. `source .venv/bin/activate`, e se faltar mesmo, `pip install -r requirements.txt` |
| `picamera2` deixou de importar **depois** do `pip install` | Choque de numpy: o do venv passou à frente do do sistema. `pip uninstall -y numpy` |
| `ImportError: libGL.so.1` ao importar o cv2 | Pacote errado: o Pi OS Lite não tem bibliotecas gráficas. `pip uninstall -y opencv-python && pip install 'opencv-python-headless>=4.10,<5'` |
| `Faltam os modelos de visão` | `python scripts/download_models.py` (a `models/` está no gitignore) |
| Vê a imagem mas 0 caras | Imagem invertida (`rodar_180`), ou contraluz |
| Reconhece toda a gente como a mesma pessoa | Só há uma pessoa registada — regista uma segunda |
| **O Pi desliga-se (LED vermelho fixo) ao detetar alguém** | Alimentação. Medir com `python scripts/vigiar_energia.py --forcar 90`. O que é novo no momento da deteção não é a câmara — essa já estava a filmar — é o SFace a pôr o CPU em carga. Provar sem a visão pelo meio: `stress-ng --cpu 4 --timeout 60s`. Se também se desligar, é a fonte, não o código |
| Lento (>50 ms a detetar) | Estás a detetar a 640×480. Detetar a 320×240 e recortar da imagem grande |

---

## Se funciona com `sudo` e sem `sudo` não

**Isto não é a câmara, é o teu utilizador.** O `/dev/dma_heap/*` pertence a
`root:video`, e uma conta criada à mão com `sudo useradd -m nome` **não leva
grupo suplementar nenhum** — o utilizador que o Raspberry Pi Imager cria leva
quinze. Sintoma: `Could not open any dmaHeap device`, e tudo a funcionar com
`sudo`.

**A regra vale para o projeto todo:** comando que falha por permissões e passa
com `sudo` é grupo em falta. Nunca se resolve a correr o robô com `sudo`.

```bash
for g in adm dialout cdrom sudo audio video plugdev games users \
         input render netdev gpio i2c spi lpadmin; do
  getent group "$g" >/dev/null && sudo usermod -aG "$g" "$USER"
done
```

Depois **sai da sessão e volta a entrar** — alterações de grupo não se aplicam a
uma sessão que já estava aberta. Confirma com `groups`.

Para este guia bastam os grupos necessários à câmara:

| Grupo | O que desbloqueia | Onde ia falhar |
|---|---|---|
| `video`, `render` | `/dev/dma_heap`, GPU, câmara | neste guia |

---

## A experiência da Lara

Esta medição mostra o custo da visão no Pi e ajuda a escolher uma resolução que
reconheça pessoas sem atrasar o resto do robô.

```bash
python scripts/medir_visao.py
```

Corre o detetor a **160×120, 320×240 e 640×480**, 100 medições em cada, e
imprime no fim uma tabela de duas colunas — píxeis e milissegundos — pronta a
passar para papel quadriculado.

**Faz este passo com uma pessoa à frente da câmara**, não com a sala vazia. A
coluna que interessa não é a do tempo, é a das **caras**: a 160×120 ele é três
vezes mais rápido e muitas vezes deixa de ver a pessoa. Depressa não serve de
nada se deixar de ver — e é essa a lição, não o gráfico.

Três coisas que a tabela mostra e vale a pena perguntar-lhe **antes** de ela ver
os números:

1. *«Se o dobro dos píxeis demorasse o dobro do tempo, os pontos ficavam numa
   linha reta ou numa curva?»* — depois marquem os pontos e vejam.
2. *«Porque é que reconhecer custa o mesmo em todas as resoluções?»* — porque o
   SFace recorta e endireita a cara para 112×112 antes de olhar para ela.
   **Detetar paga-se aos píxeis; reconhecer paga-se à cara.**
3. *«Se isto tudo dá menos de 5% de um núcleo, valia a pena uma placa de
   €130?»* — é a secção D8b do plano, respondida por ela com o cronómetro dela.

E é também a razão de existirem duas resoluções na configuração:
`secretaria.resolucao_deteccao` (320×240, para saber **onde** está uma cara) e
`faces.resolucao` (640×480, para saber **quem é**).

Sem câmara à mão (no Mac, por exemplo) mede-se na mesma com uma fotografia:

```bash
python scripts/medir_visao.py --imagem foto.jpg
python scripts/medir_visao.py --medicoes 30        # mais depressa
python scripts/medir_visao.py --csv medidas.csv    # se preferirem o Excel
```
