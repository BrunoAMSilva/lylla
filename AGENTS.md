# Instruções do projeto

O objetivo é ajudar a Lara a criar, programar e montar a Lylla. Lara participa
nas decisões e nas experiências. Um adulto trata de potência, soldadura, cortes
e primeiros testes com movimento real.

## Capacidades pretendidas

- mover-se com rodas
- reconhecer rostos com consentimento e associá-los a pessoas
- falar
- ouvir
- manter uma conversa por áudio
- mostrar olhos expressivos num ecrã

Seguir pessoas, navegar entre divisões e jogar às escondidas são capacidades
posteriores. Só entram depois de os testes de movimento e segurança passarem.

## Arquitetura atual

- Manter o mBot2 inteiro e controlá-lo pelo Raspberry Pi através de USB.
- Usar os encoders, o giroscópio, os ultrassons e o sensor RGB quádruplo do
  mBot2 antes de comprar sensores equivalentes.
- Executar no mac mini a transcrição, o modelo de linguagem e a síntese de voz.
- Executar no Raspberry Pi a palavra-chave, a visão, o reconhecimento de
  pessoas, o controlo do corpo e a aplicação dos limites locais de segurança.
- Comparar no Pi os comandos diretos depois de o mini os transcrever. Uma
  ordem falada depende do mini, mesmo quando não passa pelo modelo de linguagem.
- Tratar a interrupção durante a fala como trabalho futuro. Não a apresentar
  como uma capacidade atual.
- Manter aberta a escolha entre HUB75 e OLED para a cara. Usar entretanto os
  LEDs do mBot2.

Ler `docs/decisoes-atuais.md` ao alterar arquitetura, componentes, fases ou
exercícios. Esse ficheiro contém as alternativas em aberto e os testes que as
decidem.

## Ordem de trabalho

1. Usar e medir o hardware que já temos.
2. Inventariar e testar cada peça nova quando chegar.
3. Integrar apenas peças que resolvam uma lacuna observada.
4. Fazer primeiro testes de bancada. Passar ao chão apenas depois dos limites e
   sensores estarem verificados.
5. Adiar autonomia avançada até a integração básica ter um teste completo.

## Segurança e privacidade

- Um erro, uma leitura antiga ou um sensor ausente deve impedir movimento
  autónomo.
- O sensor RGB do mBot2 pode ser experimentado como detetor frontal de borda.
  Não é a única proteção permitida perto de uma queda.
- O primeiro teste dos motores é feito com as rodas no ar.
- O primeiro teste de borda usa uma queda baixa e almofadada, com um adulto a
  segurar o robô. Não usar mesas nem escadas.
- A ação de parar e a ação de deixar de olhar são executadas no Pi e não passam
  pelo modelo de linguagem. Quando são pedidas por voz, dependem da transcrição
  do mini.
- Um watchdog independente e um controlo físico devem parar o movimento quando
  o mini, a rede ou o ciclo principal falham. O timeout atual ainda partilha o
  ciclo principal e não cumpre sozinho este requisito.
- Guardar uma pessoa exige consentimento. A pessoa pode ver a lista e apagar os
  seus dados.
