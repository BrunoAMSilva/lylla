# Roteiro ativo de construção

Atualizado em 5 de setembro de 2026.

Este é o caminho de construção atual. `PLANO.md` conserva investigação e
decisões antigas, mas não deve ser seguido como uma sequência de montagem.
Arquitetura e decisões em aberto estão em `docs/decisoes-atuais.md`. O material
disponível está em `docs/componentes.md`.

## Regra de passagem

Uma etapa só termina quando o critério de pronto passa. Um resultado em
simulação não prova o hardware. Um teste isolado de hardware não prova a
integração.

Cada experiência com movimento começa com as rodas no ar. Os primeiros testes
no chão usam velocidade baixa, uma zona livre e um adulto junto ao robô.

## Etapa 1. Confirmar o mBot2 intacto

**Objetivo**

Confirmar que o Raspberry Pi controla o mBot2 por USB e lê o hardware que já
existe.

**Pré-requisitos**

- mBot2 montado e carregado
- cabo USB de dados
- Raspberry Pi ligado à fonte oficial
- biblioteca `makeblock` instalada

**Lara faz**

1. Liga o mBot2 ao Pi sem retirar nenhuma peça.
2. Corre `python scripts/spike_mbot2.py --sem-medir --sensores --luzes`.
3. Identifica os LEDs do CyberPi e as cinco animações do ultrassónico.
4. Com as rodas no ar e um adulto a segurar o robô, corre
   `python scripts/spike_mbot2.py --sem-medir --com-motores`.
5. Regista no caderno que roda corresponde a `EM1` e `EM2`.

**O adulto faz**

Confirma que o cabo transporta dados e mantém o robô seguro durante o teste dos
motores.

**Critério de pronto**

O script identifica o CyberPi. As duas rodas respondem, param e contam o
movimento. O giroscópio e o ultrassónico devolvem leituras.

## Etapa 2. Medir o chão com o sensor RGB

**Objetivo**

Descobrir se os quatro sensores de linha conseguem distinguir o chão de uma
borda nas divisões onde Lylla será usada.

**Pré-requisitos**

A etapa 1 passou. Os motores permanecem desligados durante toda esta etapa.

**Lara faz**

1. Corre `python scripts/spike_mbot2.py --sem-medir --chao`.
2. Mede `L2`, `L1`, `R1` e `R2` sobre chão claro, chão escuro, tapete e sombra.
3. Com um adulto a segurar o robô, mede os mesmos canais sobre espaço vazio.
4. Anota os valores e procura um intervalo que separe chão de vazio em cada
   canal.

**O adulto faz**

Segura o robô. A experiência não usa uma mesa nem uma escada. Uma caixa baixa,
com uma almofada à frente, chega para a leitura de vazio.

**Critério de pronto**

Há uma tabela com seis condições e quatro canais. Só avançamos para um veto de
movimento se todos os canais distinguirem chão de vazio nas condições testadas.
Uma leitura ausente ou antiga contará como perigo.

**Limite do resultado**

O sensor está na frente. Mesmo que o teste passe, não protege uma marcha-atrás
nem todas as aproximações durante uma rotação. Não é proteção suficiente junto
a escadas.

## Etapa 3. Movimento controlado com o mBot2

**Objetivo**

Usar as rodas, os encoders, o giroscópio e o ultrassónico que já existem.

**Pré-requisitos**

- etapa 1 concluída
- identificação estável da porta USB do mBot2
- paragem por Ctrl+C testada com as rodas no ar
- comportamento definido para perda do cabo USB

**Trabalho de implementação**

O caminho de produção ainda usa o adaptador antigo em
`robot/hardware/sensors.py`. Antes do teste de obstáculo, a distância deve vir
de `robot.hardware.mbot2.distancia_cm()`. O sensor de chão continua fora do
movimento até passar a etapa 2 e ter leituras com idade controlada.

`motors.verificar_timeout()` corre hoje no ciclo principal. Uma espera de rede
pode atrasá-lo. Antes do teste no chão, o watchdog deve correr fora desse ciclo
ou ser garantido pelo CyberPi. O ensaio desliga a ligação ao mini com as rodas
no ar e mede quanto tempo demora a parar.

**Lara faz**

Programa um quadrado e mede os quatro lados. Depois acrescenta a paragem por
obstáculo do ultrassónico.

**O adulto faz**

Testa primeiro com as rodas no ar. No chão, prepara uma zona plana e longe de
escadas. Fica junto à alimentação do mBot2. Não permite marcha-atrás autónoma
enquanto não houver cobertura traseira.

**Critério de pronto**

Lylla anda 1 m, roda 90 graus e para perante um obstáculo. Uma leitura de
distância ausente ou antiga impede o movimento. O timeout para os motores sem
comando novo funciona dentro do limite medido, mesmo quando o ciclo de rede
fica preso. Este teste não se aproxima de uma borda.

## Etapa 4. Reconhecer pessoas no Raspberry Pi

**Objetivo**

Detetar uma cara no Raspberry Pi, registar uma pessoa com consentimento e
receber um nome ou o resultado `desconhecido`.

**Lara faz**

1. Abre a imagem com `python scripts/ver_visao.py`.
2. Testa pouca luz, perfil e duas pessoas na mesma imagem.
3. Regista uma pessoa com consentimento através de
   `python scripts/enrol_face.py Lara`.
4. Lista os registos e apaga o registo de teste.

**O adulto faz**

Confirma que YuNet e SFace correm no Pi, que `data/faces/` não entra no Git e
que desligar o mini não altera o reconhecimento.

**Critério de pronto**

Cada pessoa pode aceitar o registo, ver a lista e apagar os seus dados. Quatro
de cinco tentativas reconhecem cada pessoa registada. Uma pessoa nova não recebe
o nome de outra.

## Etapa 5. Inventariar o material entregue

**Objetivo**

Transformar nomes de encomenda em componentes identificados e testáveis.
O ferro de soldar e os respetivos materiais já chegaram. Também foi encontrada
uma placa ESP32 de cerca de 2017 com Micro-USB.

**Lara faz**

1. Fotografa cada peça junto da respetiva etiqueta.
2. Regista marca, modelo, tensão, corrente, interface e conectores.
3. Marca cada linha de `docs/componentes.md` como recebida, em falta ou errada.
4. Agrupa as peças por áudio, alimentação, montagem e prototipagem.
5. Fotografa as marcações dos dois lados do ESP32 e regista que porta aparece
   quando é ligado com um cabo Micro-USB de dados.

**O adulto faz**

Monta uma bancada de soldadura segura. Confirma as especificações elétricas do
MAX98357A, da coluna, do botão e do interruptor antes de qualquer ligação.
Inspeciona o ESP32 antes de o alimentar e escolhe a placa correta na ferramenta
de compilação antes de tentar carregar firmware.

**Critério de pronto**

Os três microfones têm modelo e interface conhecidos. A coluna tem impedância e
número de canais registados. O botão e o rocker têm os contactos e valores
nominais confirmados. Fica decidido qual deles pode servir de paragem local. Se
nenhum tiver a classificação necessária, o inventário regista o componente que
falta. O ESP32 tem a placa, o conversor USB-série e a porta registados. Compila,
aceita um programa de teste e responde por série antes de ser ligado ao HUB75.

## Etapa 6. Fazer uma conversa por áudio sem interrupção

**Objetivo**

Capturar uma frase no Pi, transcrevê-la no mac mini e reproduzir no robô uma
resposta sintetizada no mini.

**Pré-requisitos**

A etapa 5 identificou pelo menos um microfone e confirmou a compatibilidade
entre o MAX98357A e a coluna.

**Lara faz**

1. Grava cinco frases curtas através do microfone escolhido.
2. Confirma o texto produzido pelo Parakeet no mac mini.
3. Escreve uma frase para Lylla dizer.
4. Ouve a resposta na coluna ligada ao Pi.

**O adulto faz**

Liga o MAX98357A na breadboard e configura a entrada e a saída de áudio. Mede a
alimentação antes de ligar a coluna.

**Critério de pronto**

Quatro das cinco frases são transcritas corretamente. Uma resposta percorre o
caminho completo do microfone ao mini e volta à coluna. Nesta etapa, Lara espera
que Lylla termine de falar antes de iniciar outro turno.

## Etapa 7. Escolher a tecnologia da cara

**Objetivo**

Comparar HUB75 e um OLED concreto no corpo e com os efeitos pretendidos.

**Pré-requisitos**

O OLED candidato tem modelo, interface, tamanho, resolução, cor, brilho,
consumo e preço conhecidos. O POC `bot-face` corre a partir de
`/Users/brunosilva/Developer/bot-filter`.

**Lara faz**

Escolhe cinco cenas para comparar. Usa repouso, piscar, olhar, coração e uma
transição. Vê cada opção a dois metros, com luz de quarto e luz do dia.

**O adulto faz**

Mede tempo de arranque, imagens por segundo, memória, CPU, consumo e efeito
sobre o openWakeWord. Confirma como o ecrã arranca sem teclado nem monitor.

**Critério de pronto**

A decisão fica escrita em `docs/decisoes-atuais.md`, com o modelo escolhido e
os números medidos. Só depois se compram peças ou se corta o corpo à medida.

## Etapa 8. Palavra-chave e turno completo

**Objetivo**

Acordar localmente com "Olá Lylla" e completar uma conversa através do mini.

**Critério de pronto**

A palavra-chave funciona dez vezes seguidas a um metro. Uma hora de ruído normal
produz no máximo um falso despertar. O turno completo termina com fala e uma
ação segura. `Pára` e `não olhes para mim` são comparados no Pi antes do LLM,
mas o teste regista que precisam da transcrição do mini.

Interromper Lylla durante a reprodução fica fora deste critério.

## Etapa 9. Integrar o ecrã escolhido

**Objetivo**

Instalar o backend escolhido na etapa 7 sem mudar os comandos que Lara usa.

**Critério de pronto**

As nove expressões escolhidas aparecem por nome. Piscar, olhar e mudar de
expressão funcionam durante uma conversa. Reiniciar o Pi recupera a cara sem
intervenção manual.

## Etapa 10. Demonstrar o conjunto básico

O teste final percorre estes casos numa única sessão:

1. arrancar sem teclado
2. mostrar uma expressão
3. andar e parar com segurança
4. acordar com "Olá Lylla"
5. transcrever e responder por áudio
6. reconhecer uma pessoa conhecida e rejeitar uma desconhecida
7. executar um comando de `meus_comandos.py`
8. respeitar `pára` e `não olhes para mim` com o mini ligado
9. parar pelo watchdog independente ou pelo corte físico com o mac mini desligado
10. reiniciar e repetir os pontos 2, 4 e 7

## Etapas posteriores

Braços, interrupção durante a fala, seguimento, navegação entre divisões e o
jogo das escondidas são extensões. Cada uma precisa de critérios próprios. O
seguimento e a navegação só começam depois da etapa 10 e depois de existir
cobertura adequada contra quedas.
