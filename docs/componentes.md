# Inventário de componentes

Atualizado em 15 de setembro de 2026. Este inventário regista o que está em
casa, o que já foi medido, o que vem a caminho e o que ainda precisa de
confirmação.

⚠️ **As peças de áudio de 5 de setembro eram do capacete, não do robô.** Os três
microfones e os dois MAX98357A foram comprados a dobrar, para servirem os dois
projetos — mas o robô nunca teve ouvidos. Ver a secção «Medições».

Não desmontar o mBot2. Não comprar controladores ou sensores que dupliquem o
que ele já fornece antes de medir o hardware real.

## Medições

### Alimentação — 15/09/2026 ✅ PASSOU

`scripts/vigiar_energia.py --forcar 90`, com a **fonte oficial USB-C de 27 W**
(5,1 V / 5 A, €13,90):

| | Valor |
|---|---|
| EXT5V mínimo sob carga | **5,124 V** |
| Banda ao longo dos 90 s | 5,124 – 5,146 V |
| Corrente do core (`VDD_CORE_A`) | 5,1 A em carga · 0,72 A em repouso |
| Temperatura | 41,1 → 58,7 °C, com Active Cooler |
| Avisos | **nenhum** — sem `SUBTENSÃO`, sem `estrangulado` |

Limiar de «firme» é 4,95 V; de falha, 4,80 V. Há **174 mV de folga** sobre o
primeiro.

⚠️ **O mínimo caiu na PRIMEIRA amostra, quando a carga ainda subia** (3,55 A), e
a tensão até subiu ligeiramente depois. Ou seja: o que se vê é ruído do ADC, não
queda de tensão. Comparar com agosto, onde a fonte antiga lia 5,117 V em repouso
e **caía a 4,758 V** sob carga — um colapso de 359 mV. Problema resolvido.

⚠️ `VDD_CORE_A` é a corrente do barramento do **core** (~0,8 V), não dos 5 V de
entrada. Os «5,1 A» são ~4 W, não 25 W.

⚠️ Este teste é **só de CPU**, de propósito — sem câmara, sem OpenCV, sem
periféricos. A carga real mede-se na etapa de visão.

### OpenCV — 15/09/2026 ✅ RESOLVIDO

`python -c "import cv2; print(cv2.__version__)"` → **4.14.0**

O *bus error* de agosto no `import cv2` era consequência dos cortes de corrente,
não de instalação corrompida. Com a fonte boa, carrega sem problema. Não é
preciso reinstalar nem verificar o cartão.

## Confirmado em casa

| Componente | Estado e uso imediato |
|---|---|
| Raspberry Pi 5 | Instalado. Controla o corpo, executa a palavra-chave e reconhece pessoas. Encaminha áudio para o mac mini. |
| Fonte de 5 V e 3 A | Existe. Não a usar como fonte principal do Pi 5 nem de um ecrã sem confirmar a carga. |
| Dissipador ativo do Raspberry Pi | Usar nos testes prolongados. |
| Câmara para Raspberry Pi | Montada e pronta para testes de captura. |
| Cartão microSD de 64 GB | Sistema do Pi. |
| mBot2 completo | Manter CyberPi, shield, motores e cabos intactos. Controlar por USB. |
| Motores com encoder do mBot2 | Medir distância e velocidade através do shield. |
| Sensor ultrassónico do mBot2 | Usar já para obstáculos à frente. |
| Sensor RGB quádruplo do mBot2 | Experimentar os quatro canais como deteção frontal de linha, cor e borda. Ainda não conta como proteção validada contra quedas. |
| LEDs do CyberPi e do ultrassónico | Cara temporária enquanto o ecrã final está por decidir. |
| Placa de desenvolvimento ESP32 | Encontrada. É de cerca de 2017 e tem Micro-USB. Pode controlar o protótipo HUB75, mas o modelo da placa, o módulo ESP32, o conversor USB-série e a pinagem ainda precisam de ser identificados. |
| Ferro de soldar e materiais | Recebidos. Inventariar o suporte, a solda, a limpeza da ponta, a ventilação e a proteção ocular antes da primeira sessão. |
| Adafruit Feather RP2040 CAN Bus | Guardar para uma necessidade que o mBot2 não cubra. |
| Adafruit Feather M4 CAN Express | Guardar para uma necessidade que o mBot2 não cubra. |
| mac mini | Executa transcrição, linguagem e síntese de voz. |

## Recebido a 5 de setembro de 2026 — já identificado

| Componente | O que se sabe hoje |
|---|---|
| 3 microfones MEMS I2S (Amazon.es B0GLXLX2HS) | ⚠️ **Do capacete, não do robô.** São cápsulas MEMS I2S: entregam amostras em bruto, não fazem AEC, e o Pi 5 passou o I2S para o RP1 (problemas abertos). Um está na bancada do stormtrooper; os outros servem o capacete do Vader. Chip exato ainda por confirmar na etiqueta (o pack de 3 mais comum é INMP441). |
| 2× MAX98357A I2S de 3 W | ⚠️ **Também do capacete.** Saem do caminho de áudio do robô: o reSpeaker é analógico e o MAX98357A só aceita I2S digital. Ficam para o capacete do Vader e para a bancada. Entrada `SD` nunca ao ar (é shutdown **e** seleção de canal); `GAIN` ao ar = 9 dB; saída em ponte, nenhum borne ao GND. |
| Fonte USB-C de 27 W para Raspberry Pi 5 | ✅ **Testada a 15/09: 5,124 V mínimo sob carga, sem avisos.** Ver «Medições». É a fonte principal do Pi. Com ela o Pi negoceia o perfil de 5 A sozinho, logo os periféricos USB não ficam presos aos 600 mA. |
| Coluna de 3 W | ✅ **Dois altifalantes de 8 Ω** (confirmado). Liga ao reSpeaker, não ao Pi. ⚠️ Medir se os dois partilham negativo comum antes de os ligar a um amplificador em ponte. |
| Pente vertical de 40 pinos, passo 2,54 mm | Confirmar se é para soldar no Pi, numa placa de interface ou noutro módulo. |
| Breadboard de 400 pontos | Usar nos ensaios de baixa tensão. Não usar em trajetos de corrente elevada. |
| Flat cable M/M de 40 pinos, 20 cm | Verificar continuidade e usar apenas depois de desenhar a pinagem. |
| Botão de pressão preto de 28 mm | Medir os contactos e decidir se será comando lógico ou paragem. Um botão lógico não substitui o corte de potência. |
| Interruptor rocker preto de 20 mm, 2 pinos | Confirmar corrente e tensão nominais antes de o colocar no caminho de alimentação. |

## Por localizar ou confirmar

| Componente | Questão em aberto |
|---|---|
| Identificação do ESP32 | Fotografar as marcações dos dois lados. Registar o módulo, a referência da placa, o conversor USB-série, a porta criada pelo Micro-USB e a pinagem antes de ligar o HUB75. |
| Chip dos três microfones | Confirmar na etiqueta. Não muda a decisão — muda só a nota da bancada do capacete. |
| Contactos do botão de 28 mm e do rocker de 20 mm | É a única coisa que decide se é preciso comprar um botão DPST de emergência. |
| Negativo comum na coluna | Cada par deve ler ~7-8 Ω e entre pares deve ler infinito. Se não ler infinito, têm massa comum e não podem ir a um amplificador em ponte. |

## A caminho — encomendado à Mauser a 15/09/2026

| Componente | Ref. | Preço | Para quê |
|---|---|---|---|
| reSpeaker Mic Array v2.0 (XMOS XVF-3000) | 096-8389 | €55,30 | Os ouvidos. AEC em hardware, beamforming, deteção de direção, e é a placa de som USB do robô. Saída **analógica** por jack de 3,5 mm (codec WM8960). |
| Amplificador PAM8403 (Whadda WPI411) | 047-3485 | €7,65 | Entre o jack e a coluna passiva. Estéreo 2×3 W, 4-8 Ω: um módulo toca os dois altifalantes. Só é preciso se o jack sozinho não der volume. |
| 2× sensor ToF VL53L1X | 095-9477 | €9,99 cada | Ver as paredes de lado, no corredor. ⚠️ Dois no mesmo I2C partilham endereço: sequenciar pelo XSHUT. |

## Decisões de compra adiadas

### Ecrã da cara

A escolha entre HUB75 e OLED continua aberta. O HUB75 já tem firmware e
protocolo. O OLED pode reutilizar mais do `bot-face` se tiver HDMI ou DSI, mas o
modelo concreto ainda não foi escolhido. Não comprar nem recortar o corpo antes
da experiência descrita em `docs/decisoes-atuais.md`.

### Movimento

O POC confirmou o controlo do mBot2 por USB. O TB6612 e o PCA9685 de motores
saem da lista de compras. Se os braços forem construídos, pode ser necessário
um PCA9685 dedicado aos servos.

### Proteção contra quedas

Usar primeiro o sensor RGB quádruplo como experiência. A compra de sensores de
precipício fica dependente dos resultados em pisos claros, escuros e com luz
variável. A cobertura traseira continua em falta mesmo que a experiência
frontal resulte.
