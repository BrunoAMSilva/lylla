# Instruções rápidas

Estas instruções servem para entrar no Raspberry Pi e fazer os primeiros testes.
A ordem de construção está no [`roteiro ativo`](roteiro.md). As tarefas da Lara
estão em [`tarefas-lara.md`](tarefas-lara.md).

Não uses `PLANO.md` como guia de montagem. Esse ficheiro conserva investigação
antiga. Em caso de conflito, segue as
[`decisões atuais`](decisoes-atuais.md) e o
[`inventário de componentes`](componentes.md).

## Ligar ao Raspberry Pi

No terminal do mac mini:

```bash
ssh lara@lylla.local
```

Se o nome não responder, confirma com um adulto qual é o nome atual do Pi no
Tailscale. Não alteres a rede para contornar o problema.

Depois de entrar:

```bash
cd ~/my-robot
```

## Ativar o ambiente Python

O ambiente virtual existente é ativado assim:

```bash
source .venv/bin/activate
which python
```

O segundo comando deve mostrar um caminho que termina em
`my-robot/.venv/bin/python`.

Para criar o ambiente pela primeira vez:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install --no-deps "openwakeword>=0.6.0"
```

No Raspberry Pi, `--system-site-packages` é necessário para o ambiente ver a
câmara instalada pelo sistema.

## Testar a câmara sem reconhecimento

Primeiro confirma a câmara e tira uma fotografia. Isto ainda não reconhece
ninguém.

```bash
rpicam-hello --list-cameras
rpicam-jpeg -o /tmp/teste.jpg -t 2000
```

Para copiar a fotografia para o mac mini, abre outro terminal no mini:

```bash
scp lara@lylla.local:/tmp/teste.jpg .
```

O Pi capta a imagem, deteta os rostos e reconhece as pessoas. Esses dados não
precisam de sair do robô.

## Testar o mBot2 intacto

Liga o mBot2 ao Pi por USB. Não retires o CyberPi, o shield, os motores nem os
sensores.

Este teste acende luzes, mas não move as rodas:

```bash
python scripts/spike_mbot2.py --sem-medir --sensores --luzes
```

O teste seguinte move as rodas. Um adulto segura o mBot2 com as rodas no ar e
fica pronto para o desligar:

```bash
python scripts/spike_mbot2.py --sem-medir --com-motores
```

Não faças o primeiro teste de movimento no chão nem em cima de uma mesa.

## Medir o sensor de chão

O teste dos quatro canais RGB não move os motores:

```bash
python scripts/spike_mbot2.py --sem-medir --chao
```

Regista os valores em `docs/tarefas-lara.md`. Para medir espaço vazio, um
adulto segura o robô sobre uma caixa baixa com uma almofada à frente. Um bom
resultado não transforma este sensor numa proteção completa contra quedas.

## Programar em simulação

No Mac ou no Pi:

```bash
ROBO_SIMULAR=1 python3
```

Dentro do Python:

```python
from lylla import *
ajuda()
olhos("feliz")
andar(30)
```

Nada se move neste modo. Guarda comandos novos em `meus_comandos.py`. O arranque
da Lylla carrega esse ficheiro e comunica um erro sem desligar o resto do robô.

## Saber onde cada trabalho corre

O Raspberry Pi executa a palavra-chave, capta e reproduz áudio, deteta e
reconhece rostos, controla o mBot2 e aplica os limites locais de movimento.

O mac mini executa os modelos de transcrição, conversa e síntese de voz. Com o
mini desligado, a Lylla continua a reconhecer pessoas. Não consegue entender
`pára`, `não olhes para mim` nem outra ordem falada. O timeout atual dos motores
partilha o ciclo principal e ainda não é um watchdog independente. Até a etapa
3 o separar e existir um corte físico confirmado, o movimento real decorre com
as rodas no ar ou numa zona plana, com um adulto junto à alimentação do mBot2.

Durante a etapa de áudio, espera que a Lylla acabe de falar antes de começares
outra frase. A interrupção durante a fala será acrescentada mais tarde.

## Antes de testar hardware

Confirma estas quatro condições:

- um adulto sabe qual teste vai começar
- o comando para parar está ao alcance
- cabos e alimentação foram verificados
- a zona não tem escadas nem uma queda alta

Se aparecer um erro, copia a mensagem exata. Não mudes várias ligações ao mesmo
tempo. Uma leitura ausente ou antiga impede movimento autónomo.
