# FASE 9 · O robô vê — arranque da câmara

Guião de arranque da visão, do cabo até «Olá, Lara!».
Pressupõe o Pi 5 já instalado, com o projeto e o venv, e acesso por **SSH sem monitor**.

O código todo já está escrito — `robot/perception/camera.py`, `faces.py`,
`attention.py`. Isto aqui é **ligar e provar que funciona**, não programar.

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

## Passo 3 · Os modelos estão no Pi?

⚠️ A pasta `models/` está no `.gitignore`. **O `git clone` não os traz** — no
Mac estão lá, no Pi provavelmente não.

```bash
cd ~/my-robot && source .venv/bin/activate
python scripts/download_models.py
ls -la models/*.onnx
```

Esperado: `face_detection_yunet_2023mar.onnx` (~230 KB) e
`face_recognition_sface_2021dec.onnx` (~39 MB). O script verifica o sha256 —
um download truncado só daria erro muito mais à frente, ao carregar o ONNX.

---

## Passo 4 · O `picamera2` vê-se de dentro do venv?

```bash
python -c "from picamera2 import Picamera2; print('✅ picamera2 ok')"
```

**`ModuleNotFoundError`?** O venv não foi criado com `--system-site-packages`.
**Não se resolve com `pip install picamera2`** — essa versão do PyPI não é a
mesma e não fala com o `libcamera` do sistema. Recriar é a única saída:

```bash
sudo apt install -y --no-install-recommends python3-picamera2
deactivate; rm -rf .venv
python3 -m venv --system-site-packages .venv
source .venv/bin/activate && pip install -r requirements.txt
```

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

**Primeiro lê em voz alta o texto que está no topo do `enrol_face.py`** — é a
primeira aula de privacidade da Lara e é concreta.

```bash
python scripts/enrol_face.py Lara
python scripts/enrol_face.py --listar
```

São 8 fotos com poses diferentes; precisa de pelo menos **3 boas**.

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

**Critério de pronto (FASE 9):** reconhece 4 pessoas em 5 tentativas cada, e
diz «não te conheço» a um estranho.

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
| `câmara → foto simulada` | `ROBO_SIMULAR=1` no ambiente |
| `No module named picamera2` | Venv sem `--system-site-packages` |
| `Faltam os modelos de visão` | `python scripts/download_models.py` (a `models/` está no gitignore) |
| Vê a imagem mas 0 caras | Imagem invertida (`rodar_180`), ou contraluz |
| Reconhece toda a gente como a mesma pessoa | Só há uma pessoa registada — regista uma segunda |
| Lento (>50 ms a detetar) | Estás a detetar a 640×480. Detetar a 320×240 e recortar da imagem grande |

---

## A experiência da Lara (FASE 9, sessão A)

Correr o detetor a **160×120, 320×240 e 640×480**, 100 imagens de cada,
cronometrar, e fazer o gráfico em papel. Ela vai ver sozinha que o tempo cresce
com o número de píxeis — e perceber porque é que **escolher bem** vale mais do
que comprar uma placa de €130 (secção D8b do plano).

É exatamente esta a razão de existirem duas resoluções na configuração:
`secretaria.resolucao_deteccao` (320×240, para saber **onde** está uma cara) e
`faces.resolucao` (640×480, para saber **quem é**).
