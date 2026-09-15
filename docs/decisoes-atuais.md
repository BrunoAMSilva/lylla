# Decisões atuais

Atualizado em 5 de setembro de 2026.

Este ficheiro regista a arquitetura que estamos a construir agora. Quando outro
documento disser o contrário, este ficheiro e a configuração executável têm
precedência. O histórico das alternativas pode continuar no `PLANO.md`, mas não
deve ser usado como instrução de montagem.

## Objetivo desta etapa

Usar primeiro o hardware que já existe. A etapa termina quando a Lylla consegue
andar com o mBot2 intacto, mostrar uma cara temporária, ouvir a palavra-chave e
trocar áudio com o mac mini. Seguir pessoas, navegar pela casa e jogar às
escondidas ficam depois desta integração básica.

## Decidido

- O mBot2 fica inteiro. O Raspberry Pi controla o CyberPi e o mBot2 Shield por
  USB. Conservamos os encoders, o giroscópio, os ultrassons e o sensor RGB
  quádruplo.
- Não compramos TB6612 nem um PCA9685 para os motores. Um PCA9685 pode continuar
  a ser necessário mais tarde para os braços.
- O Raspberry Pi trata do corpo, da palavra-chave, da visão, do reconhecimento
  de pessoas e do encaminhamento de dados.
- O mac mini executa a transcrição, o modelo de linguagem e a síntese de voz.
- A interrupção da fala continua no plano. Não é critério de conclusão da etapa
  atual.
- A tecnologia da cara continua por decidir. Até à decisão, usamos os LEDs do
  sensor ultrassónico do mBot2.
- `meus_comandos.py` é carregado quando `robot.main` arranca. Um erro nesse
  ficheiro é comunicado, mas não impede o resto do robô de arrancar.

O comando de aprendizagem `lylla.luzes(...)` já chega aos LEDs do mBot2. O
ciclo normal de `robot.main` ainda usa o controlador HUB75 para as expressões.
Ligar a API normal dos olhos aos LEDs temporários é trabalho por fazer antes
da demonstração integrada.

## Fluxo pretendido

```text
microfone -> Pi: palavra-chave e pré-rolo
           -> mac mini: transcrição, resposta e síntese de voz

câmara    -> Pi: captura, deteção e reconhecimento de pessoas

mac mini  -> Pi: áudio, expressão e ações
Pi        -> mBot2 por USB: rodas, encoders, giroscópio, distância e chão
```

O reconhecimento de pessoas e a execução dos limites de movimento ficam no Pi.
Os comandos diretos não passam pelo modelo de linguagem, mas uma ordem falada
precisa de ser transcrita no mini. O timeout atual dos motores partilha o ciclo
que espera pela rede e pode chegar tarde. A etapa 3 tem de o transformar num
watchdog independente. Até esse watchdog e um corte físico serem validados, um
adulto mantém acesso à alimentação do mBot2 durante o movimento.

## Decisão aberta sobre a cara

### Problema

A cara precisa de mostrar os olhos da Lara, piscar, olhar para uma pessoa e
transitar entre expressões. Ainda não sabemos se a textura visível dos pontos ou
a liberdade gráfica de um OLED produz o melhor resultado no corpo real.

### Restrições

- Ainda não escolhemos o modelo, o tamanho nem a interface do OLED.
- O `bot-face` em `/Users/brunosilva/Developer/bot-filter` é um renderizador
  WebGL e um editor. Não é um controlador de ecrã físico.
- A implementação HUB75 já tem firmware, protocolo série e 19 expressões.
- Encontrámos uma placa ESP32 de cerca de 2017 com Micro-USB. Continua a ser
  apenas candidata ao HUB75 até identificarmos a placa e testarmos compilação,
  carregamento e comunicação série.
- A API pública dos olhos deve permanecer igual para Lara, qualquer que seja o
  ecrã escolhido.

### Alternativas

| Opção | Trabalho necessário | Vantagem principal | Custo ou risco | Esforço |
|---|---|---|---|---|
| HUB75 64x32 com ESP32 | Ligar e testar o código que já existe | Pontos RGB visíveis, brilho alto e animação fora do Pi | Fonte de 5 V dedicada, cablagem e volume | Pequeno |
| OLED HDMI ou DSI | Ambiente gráfico, arranque em modo quiosque e ponte de comandos | Pode reutilizar o `bot-face` quase inteiro | Chromium, arranque mais complexo e risco de burn-in | Médio |
| OLED SPI ou I2C | Renderizador sem browser e controlador para o modelo escolhido | Montagem compacta | Menor reutilização do POC e limite do barramento | Grande |

### Experiência antes da escolha

1. Escolher um OLED concreto e registar tamanho, resolução, interface, cor,
   brilho, consumo e preço.
2. Fotografar as marcações do ESP32, identificar a placa e confirmar que aceita
   o firmware e responde por série através de um cabo Micro-USB de dados.
3. Mostrar no HUB75 e no OLED as mesmas cinco cenas: repouso, piscar, olhar,
   coração e transição entre duas expressões.
4. Medir tempo de arranque, imagens por segundo, memória, CPU e efeito sobre a
   deteção da palavra-chave.
5. Ver as duas opções a dois metros, com luz de quarto e com luz do dia.
6. Confirmar que a cara arranca sozinha depois de desligar e voltar a ligar.
7. Escolher só depois deste teste. Até lá, nenhum recorte do corpo depende do
   tamanho de um ecrã.

## Sensor de chão do mBot2

O sensor RGB quádruplo tem quatro leitores virados para baixo. Mede a luz
refletida em `L2`, `L1`, `R1` e `R2`, numa escala de 0 a 100. A nossa hipótese
é que uma borda provoque uma queda brusca nessa leitura. Vale a pena testar,
mas a Makeblock não apresenta o sensor como proteção contra quedas.

Isto ainda não é uma proteção validada. O fabricante especifica deteção de
linha e cor a uma distância de 5 a 15 mm. A luz ambiente, a altura e a cor do
chão alteram o resultado. O sensor só cobre a frente do robô.

Antes de o ligar ao movimento, medimos os quatro canais sobre chão claro, chão
escuro, tapete, sombra, luz direta e espaço vazio. Uma leitura em falta ou
antiga deve mandar parar. O primeiro teste de movimento usa uma borda baixa e
almofadada, com um adulto a segurar o robô. Mesas e escadas ficam fora desta
experiência.

O caminho de produção ainda não lê esta barra. `robot/hardware/sensors.py`
continua ligado ao desenho antigo de sensores externos. Até a etapa de
integração estar concluída, `seguranca.verificar_precipicio` e o movimento no
modo de secretária ficam desligados na configuração.

O mesmo caminho antigo trata a ausência do sensor de distância como caminho
livre. A integração do ultrassónico do mBot2 deve inverter essa regra. Uma
leitura ausente ou antiga impede movimento novo.

### Fontes do sensor

- [Descrição e calibração do sensor RGB quádruplo](https://support.makeblock.com/hc/en-us/articles/24279693845527-Quad-RGB-Sensor)
- [API dos quatro canais e da escala de cinzentos](https://support.makeblock.com/hc/en-us/articles/20072497351063-Input-modules)
