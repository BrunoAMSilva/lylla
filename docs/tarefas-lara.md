# Tarefas da Lara

Este é o teu caderno de construção da Lylla. Faz as tarefas pela ordem em que
aparecem. Uma experiência pode dar "não funciona" e ficar concluída na mesma,
desde que registes o que mediste e o que decidimos fazer a seguir.

O plano técnico completo está no [`roteiro ativo`](roteiro.md). Quando uma peça
chegar ou uma decisão mudar, confirma também as
[`decisões atuais`](decisoes-atuais.md) e o
[`inventário`](componentes.md).

## O que já escolheste

- [x] Escolher o nome do robô
- [x] Desenhar a tua variante do Astro
- [x] Desenhar pelo menos nove formas de olhos
- [x] Escrever o que queres que o robô consiga fazer
- [x] Inventariar e fotografar o mBot2 e as placas CAN

### Nome do robô

Lylla

### As caras da Lylla

1. Corações
2. Olhos serrados
3. Olhos em arco (feliz)
4. Olhos semi-serrados (dormir)
5. Olhos normais (círculo)
6. Piscar o olho
7. Olho grande e olho pequeno (medo)
8. Notas musicais (2)
9. Olhos chateados (Com um corte em forma de sombraçelha para baixo)

### O meu robô vai conseguir

1. Andar: sem bater nos obstáculos e seguir as pessoas que ele conhece.
2. Dançar: Dar uma volta, fazer um coração no chão, andar para a frente e para trás, ou para os lados.
3. Ver e reconhecer pessoas.
4. Falar e perguntar coisas que nós podemos saber responder.
5. Usar o nome como palavra chave para iniciar a audição e responder a perguntas.
6. Jogar às escondidas: andar pela casa e encontrar o rosto da pessoa com que ele está a jogar.

## O que já preparaste

- [x] Criar a instalação do Raspberry Pi OS Lite
- [x] Definir o nome de utilizador, a palavra-passe e o nome do robô
- [x] Ativar SSH e configurar a rede Wi-Fi
- [x] Montar a câmara no Raspberry Pi
- [x] Ligar ao Raspberry Pi por SSH a partir do mac mini
- [x] Configurar o Tailscale com o papá
- [x] Configurar o Pi com o script do papá
- [x] Criar o repositório e guardar nele os documentos e o código

## Como trabalhar

Em código, começa sempre em simulação:

```bash
ROBO_SIMULAR=1 python3
```

Depois escreve `from lylla import *` e usa `ajuda()` para ver os comandos. O
ficheiro `meus_comandos.py` guarda as funções que inventares. A Lylla carrega
esse ficheiro quando arranca.

No fim de cada etapa:

1. Guarda as medições ou a conclusão.
2. Mostra ao adulto o que aconteceu.
3. Vê as alterações com `git status --short`.
4. Submete apenas o trabalho dessa etapa.

Movimento real tem outra regra. Primeiro testamos com as rodas no ar. Só depois
passamos para uma zona livre no chão, sem escadas, com um adulto junto à Lylla.

## Etapa 0. Programar sem mexer no robô

Estas tarefas podem ser feitas enquanto o hardware está a ser preparado.

- [ ] Abrir o Python em modo de simulação e correr `ajuda()`
- [ ] Experimentar `olhos("feliz")`, `luz("azul")` e `dizer("olá Lara")`
- [ ] Fazer um quadrado com `andar()` e `virar_direita()`
- [ ] Ler a função `dar_uma_volta()` em `meus_comandos.py`
- [ ] Criar um comando novo que não use movimento real
- [ ] Provocar um erro nesse comando e confirmar que a Lylla continua a arrancar
- [ ] Corrigir o erro e submeter a alteração

## Etapa 1. Conhecer o mBot2 inteiro

Não vamos desmontar o mBot2. O Raspberry Pi fala com ele pelo cabo USB e usa os
motores, encoders, giroscópio, ultrassons, luzes e sensores que já lá estão.

- [ ] Ligar o mBot2 ao Pi com um cabo USB de dados
- [ ] Correr `python scripts/spike_mbot2.py --sem-medir --sensores --luzes`
- [ ] Identificar os LEDs do CyberPi e as animações do sensor ultrassónico
- [ ] Colocar as rodas no ar com um adulto a segurar o robô
- [ ] Correr `python scripts/spike_mbot2.py --sem-medir --com-motores`
- [ ] Anotar qual das rodas responde a `EM1` e qual responde a `EM2`
- [ ] Confirmar que as duas rodas param no fim do teste

A etapa passa quando o script encontra o CyberPi, lê distância e movimento, e
consegue fazer cada roda rodar e parar. Se alguma parte falhar, anota a mensagem
exata antes de mudar cabos ou código.

## Etapa 2. Ver o chão com quatro sensores

O sensor RGB quádruplo foi feito para linha e cor. Vamos medir se também
distingue o chão de uma borda. Nesta experiência os motores ficam desligados.

- [ ] Correr `python scripts/spike_mbot2.py --sem-medir --chao`
- [ ] Medir `L2`, `L1`, `R1` e `R2` em chão claro
- [ ] Repetir em chão escuro, tapete, sombra e luz do dia
- [ ] Com um adulto a segurar o robô, medir sobre espaço vazio
- [ ] Preencher a tabela e escrever a conclusão

| Condição | L2 | L1 | R1 | R2 |
|---|---:|---:|---:|---:|
| Chão claro |  |  |  |  |
| Chão escuro |  |  |  |  |
| Tapete |  |  |  |  |
| Sombra |  |  |  |  |
| Luz do dia |  |  |  |  |
| Espaço vazio |  |  |  |  |

Resultado escolhido:

- [ ] Os quatro canais separam chão de vazio nas condições testadas
- [ ] Há valores que se confundem e este sensor não pode vetar movimento assim

Esta medição é um diagnóstico. Não transforma o sensor numa proteção contra
quedas. Para medir o vazio, usa uma caixa baixa com uma almofada à frente. Não
uses uma mesa nem uma escada. Mesmo que o resultado seja bom, o sensor só vê a
frente e não protege uma marcha-atrás.

## Etapa 3. Andar com o mBot2

Esta etapa usa só o hardware que já existe. O teste decorre numa zona plana,
longe de escadas e sem se aproximar de uma borda.

- [ ] Em simulação, mandar andar 30 cm e ler quanto andou
- [ ] Fazer um quadrado e comparar os quatro lados
- [ ] Com as rodas no ar, repetir os comandos no mBot2
- [ ] Com as rodas no ar, bloquear a ligação ao mini e medir o tempo até os motores pararem
- [ ] Confirmar que o watchdog funciona fora do ciclo que espera pela rede
- [ ] Confirmar que uma leitura de distância ausente ou antiga impede movimento
- [ ] No chão, andar devagar numa zona livre e medir um percurso de 1 m
- [ ] Parar perante um obstáculo detetado pelo ultrassónico
- [ ] Testar `pára` com o mini ligado e confirmar que o LLM não recebe a frase

Um adulto prepara a zona e fica junto à alimentação do mBot2. O corte físico de
movimento ainda está por resolver. Não há marcha-atrás autónoma enquanto não
existir deteção traseira de borda.

## Etapa 4. Reconhecer pessoas no Raspberry Pi

O código de reconhecimento corre no Pi. As fotografias e assinaturas não
precisam de ir para o mini.

- [ ] Abrir `python scripts/ver_visao.py` e ver a imagem no browser
- [ ] Testar pouca luz, perfil e duas pessoas na mesma imagem
- [ ] Perguntar a uma pessoa se quer ser registada
- [ ] Guardar a pessoa com `python scripts/enrol_face.py Lara`
- [ ] Testar cinco vezes e contar os acertos
- [ ] Mostrar a lista com `python scripts/enrol_face.py --listar`
- [ ] Apagar uma pessoa com `python scripts/enrol_face.py --apagar Lara`
- [ ] Confirmar que uma pessoa nova aparece como `desconhecido`
- [ ] Programar um cumprimento que não se repita de dois em dois segundos

O comando `não olhes para mim` é comparado no Pi depois de o mini transcrever a
frase. Desliga o mini durante um teste e confirma que o reconhecimento de
pessoas continua a funcionar. Confirma também que uma ordem falada deixa de ser
entendida.

## Etapa 5. Receber e identificar o material

Quando a encomenda chegar, não ligues as peças logo. Primeiro descobrimos
exatamente o que veio.

- [x] Confirmar que o ferro de soldar e os materiais chegaram
- [x] Encontrar a placa ESP32 antiga com Micro-USB
- [ ] Fotografar os três microfones junto das etiquetas
- [ ] Registar marca, modelo, interface e alimentação de cada microfone
- [ ] Confirmar o modelo e os pinos do MAX98357A I2S de 3 W
- [ ] Registar a impedância, a ficha e os canais da coluna de 3 W
- [ ] Confirmar a fonte USB-C de 27 W para o Raspberry Pi 5
- [ ] Identificar o pente de 40 pinos, a breadboard e os fios M/M
- [ ] Medir os contactos do botão de 28 mm
- [ ] Ler a corrente e a tensão nominais do interruptor rocker
- [ ] Inventariar o suporte do ferro, a solda, a limpeza da ponta, a ventilação e os óculos
- [ ] Fotografar as marcações dos dois lados do ESP32
- [ ] Identificar a referência da placa, o módulo ESP32 e o conversor USB-série
- [ ] Ligar o ESP32 com um cabo Micro-USB de dados e anotar a porta que aparece
- [ ] Carregar um programa de teste e confirmar a resposta pela porta série
- [ ] Atualizar o estado de cada peça em `docs/componentes.md`

O adulto confirma as especificações elétricas. Soldadura, alimentação e o
primeiro teste da coluna não são tarefas para fazer sozinha. O ESP32 não se liga
ao painel HUB75 até a placa e a pinagem estarem identificadas.

## Etapa 6. Fazer uma conversa por áudio

Só começamos depois de escolher um microfone compatível e de confirmar a
ligação entre o MAX98357A e a coluna.

O Pi capta e reproduz o áudio. O mac mini executa a transcrição, prepara a
resposta e gera a voz.

- [ ] Gravar cinco frases curtas com o microfone escolhido
- [ ] Ver no mini o texto que o Parakeet reconheceu
- [ ] Marcar quantas das cinco frases ficaram corretas
- [ ] Escrever uma frase para a Lylla dizer
- [ ] Ouvir essa frase na coluna ligada ao Pi
- [ ] Fazer um turno completo do microfone até à resposta na coluna

Nesta etapa, espera que a Lylla acabe de falar antes de dizer outra coisa.
Interromper a fala fica no plano, mas será feito mais tarde.

## Etapa 7. Escolher a cara

A escolha continua aberta entre HUB75 e OLED. Enquanto testamos, os LEDs do
mBot2 são a cara provisória.

O protótipo `bot-face` está em
`/Users/brunosilva/Developer/bot-filter`. Ele mostra o desenho num browser, mas
ainda não controla um ecrã físico.

- [ ] Escolher um OLED concreto e anotar tamanho, resolução e interface
- [ ] Preparar as mesmas cinco cenas no HUB75 e no OLED
- [ ] Usar repouso, piscar, olhar, coração e uma transição
- [ ] Ver as duas opções a dois metros, com luz do quarto e luz do dia
- [ ] Escolher qual representa melhor os nove desenhos
- [ ] Juntar a tua opinião às medições de arranque, fluidez, CPU e memória
- [ ] Registar a decisão em `docs/decisoes-atuais.md`

Não copies números do `bot-face` diretamente para
`config/expressoes.yaml`. Os ecrãs podem ter resoluções e escalas diferentes.
Não compramos o ecrã nem cortamos o corpo antes desta comparação.

## Etapa 8. Acordar a Lylla

A palavra-chave é a única inferência de áudio que fica no Pi. A transcrição, a
conversa e a voz continuam no mac mini.

- [ ] Experimentar "Olá Lylla" dez vezes a um metro
- [ ] Contar quantas vezes a Lylla acorda corretamente
- [ ] Deixá-la uma hora com ruído normal e contar falsos despertares
- [ ] Fazer uma pergunta e ouvir a resposta completa
- [ ] Usar um comando de `meus_comandos.py` pela voz
- [ ] Confirmar que `pára` e `não olhes para mim` não passam pelo LLM
- [ ] Confirmar que ambos precisam do mini para transcrever a voz

## Etapa 9. Instalar o ecrã escolhido

- [ ] Mostrar por nome as nove caras que desenhaste
- [ ] Fazer a Lylla piscar e olhar para uma pessoa
- [ ] Escolher a cara de repouso, de pensamento e de sono
- [ ] Reiniciar o Pi e confirmar que a cara volta sozinha
- [ ] Manter os mesmos comandos de olhos, seja qual for o ecrã escolhido

## Etapa 10. Fazer a demonstração completa

Numa só sessão, a Lylla deve arrancar sem teclado, mostrar uma expressão, andar
e parar em segurança, acordar com "Olá Lylla", conversar por áudio, reconhecer
uma pessoa com consentimento e executar um comando teu. Depois desligamos o mac
mini e confirmamos que o reconhecimento continua no Pi e que o timeout e o
controlo local conseguem parar o movimento sem uma ordem falada.

- [ ] Completar a demonstração sem saltar nenhum teste
- [ ] Anotar o que falhou à primeira
- [ ] Corrigir uma coisa de cada vez
- [ ] Reiniciar e repetir os testes afetados

## Projetos para depois

### Dançar

- [ ] Fazer `dar_uma_volta()` com quatro rotações medidas
- [ ] Criar `frente_e_tras()` dentro dos limites de segurança
- [ ] Desenhar no papel um coração com centímetros e graus
- [ ] Juntar luzes e movimento num comando `dança`

### Seguir uma pessoa

Primeiro a Lylla aprende a virar a cara sem andar. O seguimento com rodas só
começa depois da etapa 10 e depois de existir cobertura adequada contra quedas.

### Jogar às escondidas

Guardar um mapa, ir de divisão em divisão e procurar uma pessoa são tarefas de
navegação autónoma. Também ficam depois da etapa 10. Nunca se testam perto de
escadas.

### Interromper a fala

Mais tarde, a Lylla poderá parar a voz quando alguém começar a falar. A conversa
da etapa 6 é de meio duplex. Uma pessoa fala, depois a outra.
