# Navegação — «Lylla, vai à cozinha»

> Desenha-se a planta da casa, treina-se um cérebro a conduzir lá dentro por
> **evolução** (centenas de robôs por geração, os melhores têm filhos), e o
> ficheiro que sai daí é o que a Lylla lê no Raspberry Pi.
>
> Tudo o que é divertido acontece em **[`escola-de-conducao.html`](escola-de-conducao.html)** —
> abre-se com dois cliques, não precisa de instalar nada, e corre no portátil
> da Lara.

---

## Em cinco minutos

1. Abre `docs/escola-de-conducao.html` no browser. Já vem lá uma casa de
   exemplo (um T3 com corredor) para não se começar do zero.
2. **Passo 1 — Planta.** Pinta as paredes, deixa os buracos das portas, pinta o
   chão de cada divisão e dá-lhe um nome. É esse nome que se lhe vai dizer em
   voz alta. Guarda em `data/casa.json`.
3. **Passo 2 — Treino.** Carrega em *Começar a evoluir* e deixa correr. Na
   primeira geração andam todos contra as paredes. Por volta da vigésima já há
   quem chegue. Guarda o melhor em `data/piloto.json`.
4. **Passo 3 — Campeã.** Vê a melhor sozinha, à velocidade a que a Lylla anda
   mesmo, com o gato e o saco a aparecer onde lhes apetece.
5. No robô:

   ```bash
   ROBO_SIMULAR=1 python scripts/escondidas.py --onde "quarto da Lara"
   ```

   e, quando os sensores de precipício estiverem montados e testados,
   `navegacao.ativo: true` no `config/robot.yaml`.

---

## As três maneiras de aprender, e a pergunta que as separa

A pergunta não é «quanto é que ela aprende» — é **onde é que a casa fica
guardada**. Cada modo responde de maneira diferente, e é isso que decide o que
consegue fazer.

| | **Pura** | **Descoberta** | **Híbrida** |
|---|---|---|---|
| O que recebe no início | a direção do destino em linha reta, através das paredes | as divisões com nome, e **zero paredes** | a planta |
| Onde fica a casa guardada | nos pesos da rede | no mapa que elas desenham com o ultrassom | na planta, mais a mobília que elas descobrem |
| O que evolui | conduzir *e* adivinhar o caminho | conduzir, enquanto o mapa se faz | só conduzir |
| Serve para o robô a sério? | não | ainda não — ver os números | **sim** |

**A pura é a do vídeo do Code Bullet.** Vale a pena vê-la uma vez, porque é ali
que se percebe o que é a evolução. Mas numa casa a sério ela **decora as missões
em que treinou** — a secção «só com o sensor de distância» tem a medição.

**A descoberta é a resposta honesta a «e sem planta nenhuma?».** A primeira
geração não sabe onde estão as paredes: mede, e o que fica provado passa a
mapa. As primeiras dezenas de gerações são feias, porque sem mapa a rota é a
linha reta; depois as paredes começam a aparecer e a rota dá-lhes a volta
sozinha.

**A híbrida é a que vai para o robô.** A planta dá a rota — isso é um problema
resolvido há cinquenta anos e não vale a pena reinventá-lo — e a rede trata do
que a planta não sabe: o saco que hoje está no corredor, o gato, e a pessoa que
atravessa sem olhar. É a divisão de trabalho certa: **a planta sabe onde estão
as paredes; só a experiência sabe o que fazer quando aparece um gato.**

---

## O conselho das três redes

Não é uma rede, são três, e cada uma tem um problema pequeno:

```
   RUMO ─────┐                    só sabe para onde quer ir.
             ├──> mistura ──> rodas      Nunca ouviu falar de obstáculos.
 EVASÃO ─────┘        ▲                  Não tem memória.
     ▲   │            │
     │   │        ÁRBITRO ─┘        só vê os sensores — e a que VELOCIDADE
     └───┘                          cada coisa se aproxima. É isto que apanha
   memória                          o gato. E escreve uns números para si
   (4 números)                      própria, que volta a ler no passo a seguir.

                                    o árbitro decide de quem se ouve mais
                                    neste décimo de segundo, e até que
                                    velocidade deixa ir — e lê a memória
                                    também, senão a evasão sabe que está a
                                    contornar e não tem o volante para o fazer.
```

Três redes pequenas em vez de uma grande, por duas razões. A primeira é que
cada uma aprende mais depressa um problema simples. A segunda é melhor: na
página vê-se, ao vivo, **qual delas está a mandar** — as três barras à direita
são as três opiniões. Uma rede grande é uma caixa preta; três pequenas são uma
explicação que se pode mostrar a uma criança.

**A memória é a única parte que não é uma conta só de ida.** São quatro números
que a evasão escreve num passo e volta a ler no seguinte; ninguém lhes diz o
que significam, e o que costuma sair da evolução é um sinal de «vou por este
lado» que se mantém aceso durante a manobra. Sem eles, contornar uma parede sem
mapa é impossível *por construção* — ver a secção «só com o sensor de
distância». O rumo não tem memória, de propósito.

São 311 números com cinco feixes e sem memória, 339 com um feixe e quatro
números de memória. Cabem num ficheiro de 13 KB.

---

## O campo de distância — o truque que faz tudo funcionar

A pergunta «por onde é que se vai da sala à cozinha?» resolve-se **uma vez por
destino**, e ao contrário: a partir da cozinha, para trás, calcula-se para
*cada quadrado da casa* quantos centímetros faltam até lá chegar. É um
Dijkstra, e demora milissegundos.

Depois disso, navegar é descer a colina: de qualquer ponto, andar sempre para
o vizinho com o número mais pequeno. Isto é melhor do que um A\* clássico por
uma razão prática: **se ela for empurrada, ou der uma volta grande a fugir do
gato, não é preciso planear nada outra vez.** O campo serve de qualquer sítio.

O mesmo campo é o professor no treino: o *fitness* mede o progresso por ele.
O robô nunca o vê — **o mapa é o professor, não a cábula.**

---

## O que faz um movimento parecer natural

O *fitness* não recompensa só chegar. Chegar vale 300 pontos e chegar depressa
vale mais 200; mas há três castigos que não são sobre chegar, e são eles que
fazem a diferença entre um robô que cumpre a tarefa e um robô que se vê andar
sem se estranhar:

- **raspar nas paredes** (−25 pelo tempo passado a menos de 20 cm de alguma coisa)
- **andar aos esses** (−40 pela variação da viragem — o *jerk*)
- **girar no sítio** e **andar para trás** (−30 cada)

E bater custa 220, que é quase o que vale chegar. Mesmo assim ela bate às
vezes: um gato que atravessa a 45 cm/s por trás dos feixes é, às vezes,
inevitável — como na vida.

O outro metade do realismo é a física: duas rodas, aceleração limitada (leva
0,4 s a chegar aos 22 cm/s), 24 cm de largura. **É esta chatice toda que faz
com que o que se aprende ali sirva cá fora.**

---

## O currículo — porque é que ela aprende mesmo

Uma coisa que não se vê no vídeo do Code Bullet, e que aqui foi precisa: as
primeiras gerações só apanham **viagens curtas**, e o alcance vai crescendo
sozinho à medida que elas começam a chegar (a métrica *Viagens até* mostra-o).

Sem isto, as primeiras 200 gerações são 200 zeros: numa casa de 9 metros,
nenhum robô ao acaso chega ao outro lado, e sem ninguém a chegar não há nada
para selecionar. Com isto, aos 20 minutos já há 80% a chegar. Ninguém ensina
uma criança a andar de bicicleta a descer a rua toda ao primeiro dia.

---

## ⚠️ «Só com o sensor de distância» — o que dá e o que não dá

A pergunta é justa: ao fim de gerações que cheguem, não devia ela navegar a
casa só com o ultrassom? A resposta medida é **sim, aprende a conduzir muito
bem; não, não aprende a casa.** E o caminho até lá teve três surpresas.

### 1. Sem memória, contornar uma parede não pode acontecer

A rede é uma **função das entradas**. Duas posições diferentes que deem a mesma
leitura de sensor e o mesmo ângulo para o destino têm obrigatoriamente a mesma
resposta. E «estou a contornar esta parede pela direita» não cabe em nenhuma
leitura de sensor: é uma coisa que só se sabe **por se ter começado a fazer**.

Sem sítio onde guardar isso, não há gerações que cheguem — não é um problema de
treino, é de construção. A **memória** são uns números que a evasão escreve num
passo e volta a ler no seguinte (e o árbitro também os lê, senão a evasão sabe
que está a contornar e não tem o volante para o fazer). Ninguém lhes diz o que
significam: o que sai da evolução é um sinal de «vou por este lado» que se
mantém aceso durante a manobra.

O rumo **não** tem memória, de propósito: continua a ser a parte simples que só
sabe onde é o destino.

### 2. O fitness mente, e o castigo não resolve isso

Para sair do escritório é preciso primeiro **afastar-se** da sala. Quem se
afasta pontua pior, e quem pontua pior não tem filhos. A espécie inteira
converge para a parede porque a parede é, de facto, a melhor jogada à luz da
pontuação. Um castigo por estar encostado muda a paisagem, mas não muda o facto
de o caminho certo passar por um vale.

A saída conhecida (Lehman & Stanley, 2008 — e o exemplo do artigo é
precisamente um labirinto destes) é deixar de perguntar só «foste bem?» e
passar a perguntar também **«foste a um sítio onde mais ninguém foi?»**. Quem
tenta a porta pontua mal, mas é raro, e a raridade compra-lhe filhos. Na
geração seguinte já há quem esteja do outro lado, e a partir daí a pontuação
normal volta a saber orientar-se.

É o *slider* da **curiosidade**. Compara-se onde cada robô ficou no fim de cada
missão, e a novidade é a distância média aos quinze mais parecidos. Mistura-se
por posição na tabela e não por pontos (senão a escala de uma esmaga a outra), e
**os intocados do topo continuam a sair da pontuação a sério**: a curiosidade
escolhe quem tem filhos, nunca deita fora a campeã.

Nesta casa, um feixe, 300 gerações — e cada uma das duas sozinha quase não
chega:

| | campeã | nível a que o currículo chegou |
|---|---|---|
| sem memória, sem curiosidade | 50%, para sempre | **2,8 m** (nunca saiu do início) |
| memória 4, curiosidade 0 | 59% | 4,9 m |
| memória 0, curiosidade 35% | 75% | 10,5 m |
| **memória 4, curiosidade 35%** | **75–100%** | **11,8 m — a casa toda** |

### 3. E depois o exame, que mudou a conclusão toda

A percentagem que se vê a subir é nas **missões em que ela treina**, e a prova é
fixa de propósito (é o que faz a curva assentar). Isso mede aprender — mas não
mede *navegar a casa*. Para isso há agora um **exame**: catorze missões que ela
nunca viu, de qualquer divisão para qualquer divisão, a casa toda, sem currículo
nenhum e com os obstáculos todos.

| cérebro | de onde vem a rota | missões do treino | **exame (14 novas)** |
|---|---|---|---|
| puro, 4 missões | de lado nenhum | 75% | 7% |
| puro, 8 missões | de lado nenhum | 83% | **21%** |
| descoberta | do mapa que ela desenhou | 64–80% | **0%** |
| descoberta | *(o mesmo cérebro, com a planta)* | — | 50% |
| **híbrido** | da planta | 98% | **64%** |

Três coisas para ler aqui, e a terceira é a que interessa:

- **O modo puro decora.** Com o dobro das missões de treino, o exame sobe de 7%
  para 21% — está a generalizar um bocadinho, e mais missões dariam mais. Mas a
  casa tem de caber em algum lado, e **339 números de rede não chegam** para nove
  divisões e as portas todas.
- **O cérebro não é o problema.** O mesmo cérebro treinado às escuras, se lhe
  derem a rota certa, faz 50% do exame — quase tanto como o treinado com ela.
  **Conduzir aprende-se sem mapa; saber por onde é que se vai, não.**
- **Um mapa a 60% é pior do que mapa nenhum.** O modo descoberta encontrou 53%
  das paredes com um feixe e 60% com cinco, e fez **0%** do exame — pior do que o
  modo puro, que não tem mapa nenhum. A razão é simples e vale a pena guardá-la:
  *um mapa com buracos dá rotas erradas com confiança*, e o piloto segue-as.

### O que isto quer dizer para a Lylla

O mapa não é uma cábula que se dá ao robô para lhe poupar trabalho — **é o único
sítio com espaço para guardar uma casa**. A rede aprende o que é para aprender
(conduzir, contornar, não raspar); a casa vive no mapa. Foi por isso que a ideia
do mapa desenhado por elas estava certa desde o início; o que falta não é
esperteza, é **medir mais**: com um único olho apontado à frente, e a ver mal as
paredes de que passa rente, o mapa fica a meio por muito que ela ande.

É também a resposta à pergunta dos sensores, e agora com um número em vez de uma
opinião: cinco feixes em vez de um levam o mapa desenhado de 53% para 60% das
paredes. Ajuda, e não chega. O que faltaria a seguir é **varrer de propósito** —
parar e dar uma volta sobre si própria de vez em quando, como o `varrimento.py`
já faz para se localizar — em vez de mapear só o que calha estar à frente.

---

## ⚠️ O que isto NÃO resolve

Três coisas, e é melhor sabê-las antes de montar o robô do que depois.

### 1. Ela não sabe onde está — mas já se sabe encontrar

Não há GPS dentro de casa. A Lylla soma o que mandou as rodas fazer
(*odometria*), e o erro **acumula-se**. Pior: não cresce com a distância,
cresce com o **quadrado** dela. O erro que interessa não é «andei 3 cm a
mais», é «fiquei meio grau torto» — e meio grau, ao fim de cinco metros, é
meio metro ao lado.

Isso está resolvido, e a solução é o mapa: **ver onde está** (secção mais
abaixo). De dois em dois metros ela pára, dá uma volta lenta a medir, e
compara o que vê com o que o mapa diz que devia ver dali. Medido no ensaio,
numa travessia de 7 m com uma roda a andar 3% menos que a outra:

| | chegou | erro máximo | embates |
|---|---|---|---|
| sem ir ver onde está | **0 em 3** — encravada aos 2,3 m | 4,1 m | 285 |
| a ir ver de 2 em 2 m | **2 em 3** | 33 cm | 23 a 28 |

O que ficou por resolver é o **robô raptado**: se alguém a levantar e a puser
noutra divisão, ela emparelha com confiança no sítio errado, e nenhuma conta
dá por isso. A defesa é verificar tantas vezes que nunca fique longe — e
perguntar quando o que vê não bate certo com nada. Resolver a sério é guardar
várias hipóteses ao mesmo tempo (um filtro de partículas), e é outro projeto.

E continua a valer a pena, por ordem de esforço:

| | o que resolve | esforço |
|---|---|---|
| dizer-lhe onde está | o rapto, e o arranque | nada — já funciona |
| **encoders nas rodas** | a patinagem, que é o erro maior | a mecânica do mBot2 já os tem; falta ler |
| marcadores ArUco nas ombreiras | repõe a posição a zero em cada porta | impressora + OpenCV, que já lá está |

### 2. Ela tem um olho, e o piloto foi treinado com cinco

O piloto de exemplo usa **cinco feixes** num leque de 120°. A Lylla tem hoje
**um** sensor apontado à frente. O `ir_para.py` faz o que pode — diz-lhe «não
vejo nada» nos quatro que faltam — e avisa no arranque, mas é uma mentira e
nota-se: ela passa ao lado de coisas que não vê.

Treinou-se um piloto de 1 feixe (800 gerações) para ver se resolvia. **Não
resolve, e a medição é clara** — a mesma travessia de 7 m, no mesmo ensaio:

| piloto | chegou | embates em paredes |
|---|---|---|
| 5 feixes (4 deles a dizer sempre «não vejo nada») | 2 em 3 | 23 a 28 |
| 1 feixe, treinado de propósito para 1 feixe | 0 em 3 | 177 a 1690 |

O piloto de 5 feixes ganha **no robô de um sensor**, e a razão é
interessante: sem informação lateral, ele aprendeu a confiar na rota — e a
rota, desde que há mapa e varrimento, é de confiança. O de 1 feixe aprendeu a
depender de um sensor que não chega, e passa a viagem a raspar.

No treino vê-se o mesmo: com 5 feixes o nível chega aos 11,6 m da casa toda;
com 1 feixe estaciona nos 6-9 m por mais gerações que se lhe dê.

**A conclusão é de hardware, não de software:** dois VL53L1X nos cantos
(~12 €, mesmo barramento I²C, sem pinos novos) e treinar com 3 feixes. É o
primeiro salto grande, e agora há números para o justificar.

### 3. O simulador não é a tua casa

Não há tapetes, não há soleiras, o chão não escorrega, e os obstáculos são
círculos. Um cérebro que na página chega 90% das vezes vai chegar menos em
casa. É por isso que os sensores mandam sempre por cima da rede — ver a
caixa no topo do `ir_para.py`.

---

## O mapa que ela desenha sozinha

A planta diz onde estão as paredes. Não diz que há um cesto da roupa no
corredor, nem que o sofá mudou de sítio. Isso ela aprende, e a técnica tem
nome: **mapa de ocupação em log-odds** (Moravec e Elfes, 1985).

Cada leitura do ultrassom soma ou subtrai evidência a cada quadrado. Parede
vista cem vezes vale muito; saco visto duas vezes vale pouco. Só entra na
rota o que passar de `2.5` — na prática, «visto muitas vezes, de sítios
diferentes».

Há duas peças que não são óbvias e **sem as quais isto não funciona**:

**1. Marcar também o vazio.** Uma leitura de 120 cm não é um facto, são dois:
«há alguma coisa a 120 cm» **e** «não há nada entre 0 e 120». Sem o segundo,
o saco que já saiu do corredor fica no mapa para sempre — ninguém o apaga.
Com ele, os raios que passam por onde o saco estava apagam-no sozinhos.

**2. Um teto na evidência (±5).** Sem limite, uma parede vista mil vezes
precisava de mil leituras contrárias para desaparecer, e no dia em que se
muda a estante ela ficava no mapa uma semana.

O ficheiro (`data/mapa.json`) abre-se num editor de texto e vê-se a casa:

```
.............1...........a.1......      e = de certeza vazio
.............11a13233322add11.....      . = não sei
.............1.c.c14#1bbcee11.....      # = de certeza ocupado
..............aeeeeeeeeeeee.......
```

### ⚠️ O ultrassom vê mal paredes, e isso está desenhado nas contas

- O som **reflete como um espelho**: uma parede que não esteja quase
  perpendicular ao feixe manda o eco para o lado, e o sensor diz «não vejo
  nada». Marcar vazio através de uma parede é o erro que estraga um mapa —
  por isso uma leitura sem eco só marca vazio até 70% do alcance, e com
  metade do peso.
- O feixe tem **~15° de abertura**. A 2 m, o eco pode vir de meio metro de
  largura e não se sabe de onde. Por isso o vazio marca-se no cone todo (é
  seguro: se o eco veio a 120 cm, não há nada mais perto em lado nenhum do
  cone) e o obstáculo espalha-se pelo arco, com o peso dividido. São muitas
  leituras de sítios diferentes que o afiam.

### ⚠️ E a regra que custou uma tarde

**Mapear com a posição errada estraga o mapa** — e o mapa estragado fica
guardado no disco e estraga todas as viagens seguintes. Aconteceu aqui: um
ensaio com a posição a fugir escreveu paredes a mais, e a viagem seguinte
começou com «não sei chegar à cozinha» de dentro do corredor.

Por isso só se aprende com a posição *confirmada*: menos de 25 cm de deriva
calculada **e** menos de 1,5 m andados desde o último varrimento que correu
bem. A conta da deriva é otimista por natureza (não sabe da roda que patinou
agora); ter emparelhado com o mapa há pouco caminho é a única confirmação a
sério que existe.

E há uma rede de segurança que não se tira: **a mobília aprendida nunca
tranca uma porta.** Se a camada aprendida fizer o destino deixar de ser
alcançável, é deitada fora. Entre acreditar no que aprendeu e conseguir sair
do quarto, sai-se do quarto.

---

## Saber onde está: o varrimento

O mapa não serve só para saber por onde ir. Serve para saber **onde se está**,
e é aí que ele paga o trabalho todo.

1. parar e dar uma volta lenta sobre si, a medir a cada passo (um sensor a
   rodar é um LiDAR pobre: ~30 medidas à volta toda);
2. para cada posição candidata à volta da que a odometria dá, perguntar ao
   mapa «se eu estivesse **aqui**, o que é que via?»;
3. ficar com a candidata em que o previsto bate melhor com o medido.

Chama-se *scan matching*. Medido com um ultrassom que espelha (70% dos ecos
rasos perdidos) e mede com 6 cm de ruído, a recuperar um erro de 40 cm e 9°:
volta a ficar a **1 a 7 cm** do sítio certo, em 0,2 s de conta.

Duas coisas que este código se recusa a acreditar:

- **leituras sem eco não entram na conta.** Usar «não vejo nada» como prova
  punha-a a corrigir-se para o sítio errado com toda a confiança;
- **um empate não é uma resposta.** Um corredor é igual a si próprio um metro
  à frente. Quando a segunda melhor candidata, longe dali, explica igualmente
  bem o que ela vê, a resposta certa é dizer que não sabe e perguntar. Quando
  ganha por pouco, acredita — mas fica com a incerteza alta e volta a
  verificar dentro de pouco caminho.

### Verificar cedo, não em pânico

A tentação é só ir ver onde se está quando já se está perdida. **Não
funciona**, e a razão é bonita: a conta da deriva é otimista, e a procura só
olha 90 cm à volta. Quando a conta finalmente dispara, o erro verdadeiro já
pode estar fora do alcance da procura — e aí ela «corrige-se» com toda a
confiança para o sítio errado. Foi exatamente o que aconteceu na primeira
versão.

A regra que ficou: **o gatilho é um quarto do que a procura alcança** (20 cm
contra 90), ou de dois em dois metros, o que vier primeiro. Custa sete
segundos e mantém o erro sempre dentro do que a procura apanha.

```bash
ROBO_SIMULAR=1 python scripts/ensaio_navegacao.py                  # a viagem toda
ROBO_SIMULAR=1 python scripts/ensaio_navegacao.py --sem-varrimento # e sem isto
```

O `ensaio_navegacao.py` tem duas posições: a **verdadeira**, que ele conhece
e o robô nunca vê, e a que **ela julga ter**. Mais um ultrassom que espelha
nas paredes e uma roda que anda 3% menos que a outra. É o robô a sério, sem
o robô — e é onde se medem os números das tabelas.

---

## Às escondidas

`scripts/escondidas.py` é o mesmo `ir_para` usado sete vezes seguidas, com
duas ideias por cima:

- **a ordem não é ao acaso**: vai primeiro aos sítios onde já a encontrou
  antes, e entre dois igualmente prováveis vai ao mais perto. A memória está
  em `data/esconderijos.json` e é uma contagem, não uma rede — a Lara pode
  abrir o ficheiro e perceber porque é que ele foi primeiro à cozinha;
- **ao chegar, dá uma volta sobre si**, devagar. A câmara vê ~60°, e ela pode
  estar atrás da porta.

```bash
ROBO_SIMULAR=1 python scripts/escondidas.py --onde "quarto da Lara"
python scripts/escondidas.py --esquecer        # limpa a memória
```

Os dois pesos que decidem o jogo estão à vista em `ordem_de_procura()`:
teimoso (vai sempre ao mesmo sítio) de um lado, preguiçoso (percorre por
ordem de distância) do outro. **O jogo interessante está no meio** — e isso
é uma coisa para a Lara afinar, não para o código decidir.

### Pôr o jogo na boca dela

O `procurar` **não está** no catálogo de ações do LLM, de propósito: o
`acoes.py` avisa que os modelos pequenos escolhem bem entre 6 a 8 ações e que
acima disso se baralham, e com o `ir_para` já vamos em oito. Se quiseres
arriscar a nona, são seis linhas em `robot/brain/acoes.py`:

```python
"procurar": {
    "descricao": "Procura uma pessoa pela casa, divisão a divisão, até a encontrar.",
    "parametros": {"quem": {"type": "string", "description": "Quem procurar."}},
    "obrigatorios": ["quem"],
},
```

e em `robot/brain/tools.py`:

```python
def _procurar(quem: str = "Lara", **_) -> str:
    estado, mensagem = procurar.comecar(quem)
    return Recusa(mensagem) if estado == "recusa" else mensagem

IMPLEMENTACOES["procurar"] = _procurar
```

Depois **testa as outras ações** — sobretudo o `mover` e o `seguir`. Se o
modelo começar a confundi-las, tira esta.

---

## Os números que se podem mexer

No `config/robot.yaml`, secção `navegacao:`:

| | |
|---|---|
| `ativo` | ⚠️ vem a `false`. Em `ROBO_SIMULAR=1` anda sempre — lá não há nada para partir |
| `velocidade_max` | 0.45, mais baixo que o teto do chão, porque ela anda às cegas para os lados |
| `feixes_reais` | quantos sensores de distância existem mesmo (hoje: 1) |
| `deriva_para_varrer` | **o número mais importante.** A que erro calculado ela pára para ir ver onde está. Regra: um quarto dos 90 cm que o varrimento procura |
| `metros_entre_varrimentos` | e de quanto em quanto caminho o faz de qualquer maneira |
| `deriva_maxima_cm` | a partir daqui já nem tenta emparelhar — pergunta a uma pessoa |
| `mapear`, `mapear_ate_cm` | se aprende mobília, e até que distância da última posição confirmada |
| `segundos_a_espreitar` | quanto tempo dá a volta sobre si ao chegar a uma divisão |

Na página, o que mais muda o resultado:

- **modo** — puro, descoberta ou híbrido. É a escolha que decide o teto de tudo
  o resto; ver «só com o sensor de distância».
- **missões por geração** — 3 é o mínimo para não decorar uma viagem, e mais
  missões dão um cérebro que passa em percursos novos. Medido no modo puro: 4
  missões → 7% no exame, 8 missões → 21%.
- **memória** — 4 números por omissão. A zero, contornar uma parede sem mapa é
  impossível por construção; no modo híbrido quase não muda nada (a rota já
  desfaz a ambiguidade), e por isso não custa deixá-la ligada.
- **curiosidade** — 0% por omissão, e é assim que deve ficar em híbrido. Nos
  modos sem planta, 35% é a diferença entre o currículo ficar nos 2,8 m e
  chegar à casa toda; 20% já não chega.
- o **número de feixes**, e os dois de sempre:

- **qualidade do mapa** — a 70%, o mapa do treino leva buracos onde uma parede
  oblíqua devolveu o eco para o lado, paredes engordadas (nunca dentro de uma
  porta) e fantasmas no meio do chão;
- **rodas tortas** — a posição de cada robô afasta-se da verdadeira, e é a
  errada que ele usa para seguir a rota. Como no robô a sério, volta ao sítio
  de dois em dois metros.

Postos a 0, aprende-se mais depressa e sai um piloto que confia no mapa — e
esse é o piloto que bate na primeira ombreira que o mapa tiver 20 cm ao lado.
No canvas vê-se o **fantasma cinzento** (onde ela julga estar), os **×
vermelhos** (paredes que o mapa não tem) e as **manchas cinzentas** (paredes
que o mapa inventou).

---

## ⚠️ Quando parece que não aprende nada

Aconteceu, e as quatro causas valem mais do que a correção. Sintomas: robôs a
**rodar sobre si próprios** e a percentagem que chega a saltar entre 0 e 30%
durante milhares de gerações.

### 1. Ficar quieto compensava mais do que tentar

O castigo de bater estava em 220 e o progresso valia 100. Contas:

| | |
|---|---|
| andou 30% do caminho e bateu | 30 − 220 = **−190** |
| ficou parado a rodar no sítio | **−40** |

Não tentar era a melhor jogada — e como é a melhor jogada que tem filhos, a
população inteira convergia para robôs a girar. **Isto não é um erro de
programação, é um erro de contabilidade**, e é a forma mais comum de um
treino por evolução falhar: a coisa que se mede não é a coisa que se quer.

Agora são três números a segurar a ordem certa, e estão à vista no
`fitness()`: parado −140, meio caminho e bater −90, arrancar contra a parede
−220, atravessar a casa sem bater +550.

### 2. Escolher duas divisões à mão desligava o currículo

Com `origem` e `destino` fixos só há uma missão possível — e é logo a de nove
metros, desde a geração 0. Nenhum robô ao acaso chega ao outro lado da casa,
não há nada para selecionar, e ficam-se quatrocentas gerações de zeros.

A saída é a mesma ideia pelo outro lado: em vez de encurtar a missão,
**começa-se mais perto do fim**. A primeira geração parte a dois metros e meio
da porta, e o ponto de partida vai recuando pela rota à medida que elas
chegam. Chama-se currículo ao contrário, e é o que se faz a quem está a
aprender a estacionar.

### 3. A deriva crescia sem limite — e no robô não cresce

As rodas tortas faziam a posição fugir durante um minuto e meio inteiro, até
metros de erro. Nenhum cérebro consegue nada assim: a rota que segue já não
tem nada a ver com o sítio onde está.

Mas **o robô a sério não anda assim**: de dois em dois metros pára, dá uma
volta a medir e volta a saber onde está com centímetros de erro. O simulador
estava a treinar para um mundo *pior* do que o verdadeiro — que é exatamente
o mesmo erro de treinar num mundo melhor, só que ao contrário.

### 4. O mapa mau tapava portas

Engordar paredes ao acaso fechava quadrados dentro das portas — e uma porta
tem quatro. A rota passava a raspar na ombreira, ou dava a volta à casa toda.
Agora só se engordam paredes onde há folga (`folga >= 3`), que é onde um mapa
a sério as engorda.

### E a percentagem, para se poder ler

O número de UMA geração salta de 0 a 80% sem o cérebro ter mudado nada —
cada geração apanha obstáculos novos, mapa novo e rodas novas. O que se mostra
agora é a **média das últimas dez gerações**, contada em todas as missões e
não só na que se vê. E o gráfico ganhou a linha laranja do **comprimento das
viagens**: é vê-la a subir por baixo da verde que mostra que está a aprender.

Depois disto, na casa de exemplo: **nível 11,6 m (a casa toda) à geração 100 e
86-91% a chegar à geração 700** — com mapa mau e rodas tortas ligados. E no
`ensaio_navegacao.py`, com um ultrassom que espelha: 3 travessias em 4, **zero
embates**.

---

## Quando alguma coisa corre mal

| o que se vê | o que é |
|---|---|
| «A divisão X está fechada — falta-lhe uma porta» | pintaste as paredes à volta toda. Apaga um bocado de parede para fazer a porta (4 quadrados = 80 cm) |
| A métrica *Alcançáveis* diz 5/7 | o mesmo, mas antes de treinares. É para isso que ela está lá |
| Treina 100 gerações e ninguém chega | vê se o destino tem chão pintado, e se a origem tem espaço para um robô de 24 cm |
| «Não tenho piloto treinado» | falta o `data/piloto.json` — treina e guarda |
| Os testes falham no `test_a_conta_e_a_mesma_do_browser` | alguém mexeu na matemática de um dos lados. É exatamente para isso que aquele teste existe: ver [`piloto.py`](../robot/navigation/piloto.py) |
| Ela diz «perdi-me» a meio | é a odometria, não é uma avaria. Diz-lhe onde está |

---

## Os ficheiros

```
docs/escola-de-conducao.html   editor de planta + simulador + treino (uma página, zero instalação)
data/casa.json                 a planta (as paredes)
data/mapa.json                 o que ela aprendeu com o ultrassom (a mobília)
data/piloto.json               o cérebro treinado (números + casos de teste + a sequência da memória)
data/piloto-1feixe.json        o mesmo, treinado com UM sensor — para comparar
data/casa-bruno.json           a planta da casa a sério (55×32, 11,0 × 6,4 m, 9 divisões)
data/piloto-casa-bruno.json    o cérebro para essa casa: híbrido, 1 feixe, memória 4 — 64% no exame
data/piloto-descoberta.json    o cérebro treinado SEM planta nenhuma — para ver, não para usar
data/esconderijos.json         onde já encontrou cada pessoa

robot/navigation/casa.py       paredes, divisões, campo de distância    ← o mesmo algoritmo do browser
robot/navigation/piloto.py     as três redes, em numpy                  ← a mesma conta do browser
robot/navigation/pose.py       onde ela julga estar, e o quanto pode estar enganada
robot/navigation/memoria_espaco.py  o mapa de ocupação: a mobília, aprendida
robot/navigation/varrimento.py      dar uma volta a medir e descobrir onde está
robot/navigation/ir_para.py    junta tudo — e deixa os sensores mandar por cima de tudo
robot/navigation/procurar.py   às escondidas
scripts/escondidas.py          jogar hoje, sem robô nenhum
scripts/ensaio_navegacao.py    a viagem toda, com um ultrassom que mente como o verdadeiro
tests/test_navegacao.py        49 testes, e os dois primeiros são os que interessam
```
