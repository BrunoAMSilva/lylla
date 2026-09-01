"""DAR UMA VOLTA A MEDIR, E DESCOBRIR ONDE SE ESTÁ.

╔══════════════════════════════════════════════════════════════════════════╗
║  O MAPA NÃO SERVE SÓ PARA SABER POR ONDE IR. SERVE PARA SABER ONDE SE    ║
║  ESTÁ — e é aí que ele paga o trabalho todo.                            ║
║                                                                          ║
║  A odometria gasta-se: ao fim de uns metros, a Lylla julga-se meio       ║
║  metro ao lado. Até agora a resposta era parar e perguntar. Agora há     ║
║  uma resposta melhor, e é surpreendentemente simples:                    ║
║                                                                          ║
║    1. parar e dar uma volta lenta sobre si, a medir a cada passo         ║
║       (um sensor a rodar é um LiDAR pobre: ~30 medidas à volta toda);    ║
║    2. para cada posição candidata à volta da que ela julga ter,          ║
║       perguntar ao mapa «se eu estivesse AQUI, o que é que veria?»;      ║
║    3. ficar com a candidata em que o previsto bate melhor com o medido.  ║
║                                                                          ║
║  Chama-se *scan matching*, e é metade do que faz um robô aspirador       ║
║  saber onde está. A outra metade é o mapa, que já temos.                 ║
╚══════════════════════════════════════════════════════════════════════════╝

⚠️ DUAS COISAS QUE ESTE CÓDIGO SE RECUSA A ACREDITAR:

   · leituras SEM ECO não entram na conta. Uma parede oblíqua devolve o som
     para o lado e o sensor diz «não há nada» — usar isso como prova punha a
     Lylla a corrigir-se para o sítio errado com toda a confiança.
   · uma correção grande demais é rejeitada. Se a melhor candidata está a
     mais de meio metro do que a odometria diz, provavelmente o corredor
     casou com o corredor errado. Mais vale perguntar a uma pessoa do que
     acreditar num palpite bonito.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Quanto se procura à volta da posição que a odometria dá.
# Quanto se procura à volta da posição que a odometria dá. Alargar isto custa
# ao quadrado (são posições numa grelha) mas é barato em absoluto — e uma
# procura demasiado estreita é a pior das duas: não encontra e não sabe que
# não encontrou.
BUSCA_CM = 90.0
BUSCA_GRAUS = 25.0
PASSO_GROSSO_CM = 15.0
PASSO_GROSSO_GRAUS = 5.0
PASSO_FINO_CM = 4.0
PASSO_FINO_GRAUS = 1.5

MIN_AMOSTRAS = 8              # menos do que isto não decide nada
TETO_ERRO_CM = 60.0           # um desencontro enorme não conta mais que isto
CASTIGO_SEM_PREVISAO = 45.0   # o mapa não prevê nada e ela vê alguma coisa:
                              # é mobília que o mapa não tem. Custa, não veta.
ERRO_ACEITAVEL_CM = 25.0      # acima disto não se acredita no resultado
ERRO_MAXIMO_CM = 40.0         # para a escala da confiança
DISTANCIA_RIVAL_CM = 40.0     # a partir de que distância uma candidata conta
                              #   como uma explicação DIFERENTE do que ela vê
MARGEM_EMPATE_CM = 0.5        # empate técnico: há duas respostas → não decide
MARGEM_DUVIDA_CM = 4.0        # ganhou, mas por pouco → acredita e volta a ver cedo


@dataclass
class Amostra:
    rumo: float               # o rumo (absoluto, como ela o julga) da medição
    distancia_cm: float


@dataclass
class Correcao:
    dx: float = 0.0
    dy: float = 0.0
    drumo: float = 0.0
    erro_cm: float = 99.0
    confianca: float = 0.0
    amostras_usadas: int = 0
    erro_rival_cm: float = 99.0     # a melhor explicação ALTERNATIVA, longe daqui
    ambigua: bool = False           # empate: há duas respostas igualmente boas
    duvidosa: bool = False          # ganhou por pouco: acredita-se, com reservas

    @property
    def aceite(self) -> bool:
        return (self.amostras_usadas >= MIN_AMOSTRAS
                and self.erro_cm <= ERRO_ACEITAVEL_CM
                and not self.ambigua)

    @property
    def salto_cm(self) -> float:
        return math.hypot(self.dx, self.dy)


@dataclass
class Varrimento:
    """As medidas de uma volta sobre si própria."""

    rumo_inicial: float = 0.0
    rodado: float = 0.0
    _ultimo_rumo: float | None = None
    amostras: list[Amostra] = field(default_factory=list)

    def juntar(self, rumo: float, distancia_cm: float) -> None:
        if self._ultimo_rumo is not None:
            self.rodado += abs(_normalizar(rumo - self._ultimo_rumo))
        self._ultimo_rumo = rumo
        # uma medida a cada ~10°, que é o que o sensor consegue distinguir
        if not self.amostras or abs(_normalizar(rumo - self.amostras[-1].rumo)) > math.radians(9):
            self.amostras.append(Amostra(rumo, distancia_cm))

    @property
    def completo(self) -> bool:
        return self.rodado >= 2 * math.pi * 0.95 or len(self.amostras) >= 40


# ---------------------------------------------------------------------------
# «Se eu estivesse aqui, o que é que via?»
# ---------------------------------------------------------------------------

def alcance_previsto(casa, x: float, y: float, angulo: float, alcance_cm: float) -> float:
    """A distância à primeira parede (ou mobília aprendida) nesta direção."""
    cm = casa.cm
    dx, dy = math.cos(angulo), math.sin(angulo)
    cx, cy = int(x // cm), int(y // cm)
    if casa.eh_parede(cx, cy):
        return 0.0
    passo_x = 1 if dx > 0 else -1
    passo_y = 1 if dy > 0 else -1
    delta_x = abs(cm / dx) if dx != 0 else math.inf
    delta_y = abs(cm / dy) if dy != 0 else math.inf
    t_x = (((cx + 1) * cm if dx > 0 else cx * cm) - x) / dx if dx != 0 else math.inf
    t_y = (((cy + 1) * cm if dy > 0 else cy * cm) - y) / dy if dy != 0 else math.inf
    while True:
        if t_x < t_y:
            cx += passo_x
            t = t_x
            t_x += delta_x
        else:
            cy += passo_y
            t = t_y
            t_y += delta_y
        if t > alcance_cm:
            return alcance_cm
        if casa.eh_parede(cx, cy):
            return t


def _erro(casa, x, y, rumo, amostras, alcance_cm) -> tuple[float, int]:
    total = 0.0
    usadas = 0
    for a in amostras:
        if a.distancia_cm >= alcance_cm * 0.95:
            continue                       # sem eco não é prova de nada
        previsto = alcance_previsto(casa, x, y, a.rumo + rumo, alcance_cm)
        if previsto >= alcance_cm:
            total += CASTIGO_SEM_PREVISAO
        else:
            total += min(abs(previsto - a.distancia_cm), TETO_ERRO_CM)
        usadas += 1
    return (total / usadas if usadas else 999.0), usadas


def emparelhar(casa, x: float, y: float, amostras: list[Amostra],
               alcance_cm: float = 200.0) -> Correcao:
    """Onde é que ela estava mesmo, comparado com onde julgava estar.

    Procura em duas passagens — uma grossa e larga, outra fina à volta da
    melhor — porque procurar tudo com passo fino demorava segundos e não
    encontrava nada de diferente.
    """
    uteis = [a for a in amostras if a.distancia_cm < alcance_cm * 0.95]
    if len(uteis) < MIN_AMOSTRAS:
        return Correcao(amostras_usadas=len(uteis))

    def procurar(cx, cy, cr, raio_cm, raio_rad, passo_cm, passo_rad, registo=None):
        melhor = (math.inf, cx, cy, cr, 0)
        n_cm = int(raio_cm / passo_cm)
        n_rad = int(raio_rad / passo_rad)
        for ix in range(-n_cm, n_cm + 1):
            for iy in range(-n_cm, n_cm + 1):
                px, py = cx + ix * passo_cm, cy + iy * passo_cm
                if not casa.livre(px, py, 5):
                    continue           # não vale a pena: ela não cabia ali
                for ir in range(-n_rad, n_rad + 1):
                    pr = cr + ir * passo_rad
                    e, usadas = _erro(casa, px, py, pr, uteis, alcance_cm)
                    if registo is not None:
                        registo.append((e, px, py, pr, usadas))
                    if e < melhor[0]:
                        melhor = (e, px, py, pr, usadas)
        return melhor

    todas: list[tuple[float, float, float, float, int]] = []
    grosso = procurar(x, y, 0.0, BUSCA_CM, math.radians(BUSCA_GRAUS),
                      PASSO_GROSSO_CM, math.radians(PASSO_GROSSO_GRAUS), todas)
    fino = procurar(grosso[1], grosso[2], grosso[3],
                    PASSO_GROSSO_CM, math.radians(PASSO_GROSSO_GRAUS),
                    PASSO_FINO_CM, math.radians(PASSO_FINO_GRAUS), None)
    erro, bx, by, brumo, usadas = min(grosso, fino, key=lambda m: m[0])

    # ---- há OUTRA explicação, longe daqui, tão boa como esta? -------------
    #
    # Um corredor é igual a si próprio um metro à frente, e há sempre uma
    # segunda candidata razoável — o vale é comprido nessa direção. Isso não
    # é motivo para deitar fora a resposta: a direção ATRAVESSADA ao corredor
    # está bem determinada, e é a que interessa para não raspar nas paredes.
    #
    # Por isso duas medidas em vez de uma:
    #   · EMPATE  (as duas explicam igualmente bem) → não decide, pergunta.
    #   · DÚVIDA  (ganhou por pouco) → acredita, mas fica com a incerteza
    #     grande, e volta a verificar daqui a pouco em vez de daqui a três
    #     metros.
    #
    # ⚠️ Isto NÃO resolve o robô raptado: se alguém a levantar e a puser noutra
    #    divisão, ela emparelha com confiança no sítio errado, e nenhuma destas
    #    contas dá por isso (a defesa é verificar tantas vezes que nunca fique
    #    longe, e perguntar quando não bate certo). Resolver a sério é guardar
    #    várias hipóteses ao mesmo tempo — um filtro de partículas — e isso é
    #    outro projeto.
    rival = math.inf
    for e, px, py, _pr, _u in todas:
        if math.hypot(px - bx, py - by) > DISTANCIA_RIVAL_CM:
            rival = min(rival, e)
    ambigua = rival - erro < MARGEM_EMPATE_CM
    duvidosa = rival - erro < MARGEM_DUVIDA_CM

    return Correcao(
        dx=bx - x, dy=by - y, drumo=_normalizar(brumo),
        erro_cm=erro, amostras_usadas=usadas, erro_rival_cm=rival,
        ambigua=ambigua, duvidosa=duvidosa,
        confianca=0.0 if ambigua else max(0.0, min(1.0, 1.0 - erro / ERRO_MAXIMO_CM)) * (0.5 if duvidosa else 1.0),
    )


def _normalizar(a: float) -> float:
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a
