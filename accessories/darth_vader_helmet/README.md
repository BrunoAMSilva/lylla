# Capacete de Darth Vader

Modificador de voz em tempo real para Teensy 4.0. Produz uma voz mais grave,
com ressonância de máscara, e uma respiração com inspiração, expiração e pequenos
estalidos de válvula. Conserva o interruptor de adulto/criança no pino 2.

Abre `darth_vader_helmet.ino` no Arduino IDE. Mantém `vader_dsp.h` na mesma pasta.
Seleciona **Teensy 4.0**, **USB Type > Serial**, **CPU Speed > 600 MHz** e
**Optimize > Faster**. A biblioteca Audio vem com o pacote Teensy. Não precisas
de instalar outra biblioteca nem de acrescentar hardware.

## Primeiro teste

1. Começa com a coluna afastada do microfone e o volume baixo. O microfone deve
   ficar perto da boca, protegido do sopro direto. A montagem dentro do capacete
   precisa de isolamento entre a coluna e o microfone para evitar feedback.
2. Abre o monitor série a **115200**. Envia `b` para ouvir apenas a respiração.
   `-` e `+` alteram o volume em passos de 0,05.
3. Envia `c`. A saída fica em silêncio e o monitor continua a mostrar o
   microfone. Fala normalmente. Usa um valor de `RMS` observado durante uma
   vogal sustentada como `referenceRms`, no início de `vader_dsp.h`. O valor
   inicial é 0,020. Se o alterares, volta a carregar o sketch.
4. Envia `v` e testa uma frase. Compara o interruptor aberto, adulto, com o
   pino 2 ligado a GND, criança. Não forces a garganta para fazer uma voz grave.
5. Envia `a` para juntar voz e respiração. Confirma que a porta fecha quando
   deixas de falar e que a respiração, sozinha, não a abre.

O LED pisca mais depressa no modo criança. O programa arranca sozinho sem o
monitor série. O modo e as alterações de volume pelo monitor não são guardados.

| Comando | Resultado |
| --- | --- |
| `a` | Voz e respiração |
| `v` | Só voz |
| `b` | Só respiração, sem redução de volume pela voz |
| `c` | Silêncio para medir o microfone |
| `+` / `-` | Aumenta / reduz o volume |
| `?` | Mostra a ajuda |

`micPico` perto de 1 indica saturação na entrada. `limitador` abaixo de 1 indica
que a soma está a ser atenuada para evitar saturação digital. `CPUmax` deve
ficar abaixo de 100%, com margem. `falhas` conta falhas de alocação de blocos
de áudio e deve ficar em zero. Estes valores só podem ser medidos no Teensy.

O limitador digital não mede o volume acústico nem elimina o feedback.

## Ajustar o som

Os parâmetros editáveis estão em `Tuning`, no início de `vader_dsp.h`.

| Parâmetro | Inicial | O que altera |
| --- | --- | --- |
| `referenceRms` | 0.020 | Nível de fala usado pelo compressor e pela porta |
| `adultPitch` | 0.80 | Descida de 3,9 semitons |
| `childPitch` | 0.64 | Descida de 7,7 semitons |
| `master` | 0.65 | Volume de tudo |
| `voice` | 1.0 | Volume da voz |
| `breath` | 0.85 | Volume da respiração |
| `valve` | 1.0 | Estalido e fuga curta de ar na respiração sintética |
| `consonants` | 0.55 | Definição das consoantes |
| `gateOpen` / `gateClose` | 0.22 / 0.11 | Limiares relativos a `referenceRms` |
| `breathUnderVoice` | 0.32 | Fração da respiração mantida enquanto se fala |

Se a voz ficar demasiado artificial, aproxima o pitch de 1. O intervalo
aceite é 0,55 a 1. Numa voz adulta já grave, começa por 0,90. Se perderes
palavras, calibra primeiro o microfone e experimenta aumentar `consonants`.
Se a própria coluna abrir a porta, melhora a separação física e reduz o volume
antes de subir os limiares.

A altura da voz e a ressonância mudam, mas a dicção, o sotaque e a identidade
vocal continuam a ser os de quem fala. Isto não é um modelo de conversão de voz
de James Earl Jones. O timbre final também depende da resposta da coluna e da
montagem no capacete. A classificação de 3 W / 8 Ω não descreve essa resposta.

## Ouvir no computador

O renderizador compila o mesmo `vader_dsp.h` usado no Teensy. Requer Python 3
e `clang++` ou `g++`. Não requer NumPy nem SciPy.

Na pasta deste sketch:

```sh
python3 previsao_respiracao.py
python3 previsao_respiracao.py --input voz.wav --mode voice --output voz-vader.wav
python3 previsao_respiracao.py --input voz.wav --mode full --child --output voz-crianca.wav
python3 previsao_respiracao.py --input voz.wav --compare --output comparacao.wav
python3 previsao_respiracao.py --test
```

O primeiro comando cria `respiracao-vader.wav`, com 20 segundos. O antigo
`respiracao-nova.wav`, se existir, continua disponível para comparação.
Os WAVs de entrada devem ser PCM de 16 bits, mono, a 44100 Hz. Para converter:

```sh
ffmpeg -i gravacao.m4a -ar 44100 -ac 1 -c:a pcm_s16le voz.wav
```

A gravação é ajustada para simular RMS de microfone de 0,020 durante a fala.
Usa `--mic-rms` para experimentar outro nível. O resultado não inclui o efeito
acústico do capacete, o feedback nem a resposta da coluna.

`--compare` coloca a gravação original antes da versão processada, com uma
pausa de 750 ms e RMS igual nos dois trechos. `voz-comparacao.wav`, quando
incluído, usa uma frase gerada pela voz Daniel do macOS. É uma demonstração do
efeito numa voz sintética, não uma gravação do microfone do capacete.

## Usar uma respiração gravada

A síntese incluída é uma aproximação. Para reproduzir uma respiração específica,
usa uma gravação isolada de um ciclo completo. O original de Ben Burtt foi
gravado através de um regulador de mergulho.
[Entrevista com Ben Burtt](https://www.20k.org/episodes/starwarspewpew)

Recorta uma inspiração, a pausa, uma expiração e a pausa seguinte. Começa e
termina em silêncio. Converte o recorte para WAV mono de 16 bits a 22050 Hz:

```sh
ffmpeg -i ciclo.wav -ar 22050 -ac 1 -c:a pcm_s16le ciclo-22050.wav
python3 tools/import_breath.py ciclo-22050.wav
```

O script cria `breath_sample.h`. O sketch e o renderizador passam a usar essa
gravação automaticamente. Os estalidos já devem estar na gravação. O parâmetro
`valve` só atua sobre a síntese. O volume, a redução durante a fala e o limitador
continuam a atuar nos dois casos.

Um ciclo de 4,35 segundos ocupa cerca de 192 KB de flash. O conversor aceita
0,5 a 12 segundos, remove o offset, ajusta o pico a 0,45 e suaviza os primeiros
e últimos 10 ms. Para voltar à síntese, muda o nome de `breath_sample.h` para
`breath_sample.h.disabled` e volta a carregar o sketch.

## Ligações

| Teensy 4.0 | Ligação |
| --- | --- |
| 21 | BCLK / SCK do microfone e BCLK do MAX98357A |
| 20 | WS / LRCLK do microfone e LRC do MAX98357A |
| 8 | DOUT / SD do microfone |
| 7 | DIN do MAX98357A |
| 3,3 V | Alimentação do microfone |
| GND | Massa comum e L/R do microfone para `CANAL_MIC = 0` |
| 2 | Interruptor para GND, opcional |

O sketch envia o mesmo áudio aos dois canais I2S. Não é necessário MCLK nestes
dois módulos. Mantém a alimentação do amplificador adequada ao teu módulo.
A coluna liga a OUT+ e OUT-, sem ligar nenhum desses terminais a GND.
[I2S de entrada da PJRC](https://www.pjrc.com/teensy/gui/index.html?info=AudioInputI2S),
[I2S de saída da PJRC](https://www.pjrc.com/teensy/gui/index.html?info=AudioOutputI2S),
[MAX98357A](https://learn.adafruit.com/adafruit-max98357-i2s-class-d-mono-amp/pinouts),
[datasheet MSM261S4030H0](https://www.makerhero.com/img/files/download/Microfone-Sipeed-MSM261S4030H0-Datasheet.pdf).

## O que mudou no DSP

O shifter escreve continuamente num buffer circular. Ao mudar a posição de
leitura, procura uma parte da onda semelhante e faz uma transição de 8 ms.
A interpolação permite ler posições fracionárias. Esta abordagem substitui o
`AudioEffectGranular` do sketch anterior, cujo próprio código o descreve como
um efeito de glitch.
[Código da biblioteca Audio](https://github.com/PaulStoffregen/Audio/blob/master/effect_granular.cpp),
[atrasos variáveis e interpolação](https://www.dsprelated.com/freebooks/pasp/Delay_Line_Signal_Interpolation.html).

A voz conserva mais graves e mistura uma pequena parte das consoantes sem
alterar o tom. O compressor antecede a saturação, e as ressonâncias têm ganhos
moderados. A respiração e as rampas de volume são calculadas amostra a amostra
na interrupção de áudio. A respiração continua mesmo quando não chega um bloco
do microfone. A rotina `loop()` trata apenas dos controlos e do monitor série.

Os testes verificam a altura e a continuidade de tons, a porta, o silêncio, as
duas fases da respiração, a válvula, o limite de saída, as mudanças de modo e o
loop de amostras em flash. A compilação para Teensy 4.0 foi verificada com o
pacote Teensy 1.62.0. Ainda é necessário ouvir e medir o conjunto físico.
