"""A PLANTA DA CASA — paredes, divisões, e o caminho até cada uma.

╔══════════════════════════════════════════════════════════════════════════╗
║  ESTE FICHEIRO É O MESMO ALGORITMO QUE CORRE NO BROWSER                  ║
║                                                                          ║
║  A planta desenha-se e o cérebro treina-se em docs/escola-de-conducao    ║
║  .html. O que lá se aprende só serve se as contas aqui derem o mesmo     ║
║  resultado — por isso as constantes (2.6, 0.7, 1.4142) são as mesmas,    ║
║  linha a linha, e não «mais ou menos as mesmas».                        ║
║                                                                          ║
║  Se um dia mudar uma delas, tem de mudar nos dois sítios, e o            ║
║  tests/test_navegacao.py está lá para gritar quando isso não acontecer.  ║
╚══════════════════════════════════════════════════════════════════════════╝

O formato do ficheiro (data/casa.json) é de propósito legível por uma pessoa:
as paredes são linhas de texto com '#' e '.', as divisões são as mesmas linhas
com uma letra por divisão. Abre-se num editor de texto e percebe-se.
"""

from __future__ import annotations

import heapq
import json
import math
from dataclasses import dataclass
from pathlib import Path

LETRAS = "abcdefghijklmnopqrstuvwxyz"

# Estes três números descrevem a Lylla vista de cima. Estão repetidos no
# piloto.json (secção `fisica`) — quem manda é o piloto, estes são o recurso
# para quando se quer olhar para a planta sem carregar cérebro nenhum.
RAIO_CM = 12.0

VIZINHOS = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
            (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142))
VIZINHOS4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


@dataclass
class Divisao:
    nome: str
    cor: str = "#36E0FF"


class Casa:
    """Uma planta carregada de um casa.json."""

    def __init__(self, dados: dict) -> None:
        if dados.get("formato") != "lylla-casa-1":
            raise ValueError("Isto não é um casa.json da Lylla (falta formato: lylla-casa-1).")
        self.nome = dados.get("nome", "casa")
        self.cols = int(dados["colunas"])
        self.rows = int(dados["linhas"])
        self.cm = float(dados["cm_por_celula"])
        self.divisoes = [Divisao(d["nome"], d.get("cor", "#36E0FF")) for d in dados["divisoes"]]
        self.parede = bytearray(self.cols * self.rows)
        self.zona = [-1] * (self.cols * self.rows)
        for y in range(self.rows):
            linha_p = dados["paredes"][y]
            linha_z = dados["zonas"][y]
            for x in range(self.cols):
                i = y * self.cols + x
                self.parede[i] = 1 if linha_p[x] == "#" else 0
                self.zona[i] = LETRAS.find(linha_z[x])
        p = dados.get("partida", {"coluna": 1, "linha": 1})
        self.partida = (int(p["coluna"]), int(p["linha"]))
        self._campos: dict[int, list[float]] = {}
        self._folga: list[int] | None = None
        self._maior = 0.0
        # A camada APRENDIDA: o que o ultrassom foi encontrando e a planta não
        # sabe (o sofá, o cesto da roupa, a caixa que ficou no corredor). Vazia
        # até alguém a pôr — ver memoria_espaco.py e ir_para.py.
        self.aprendido: bytearray | None = None

    # -- carregar ----------------------------------------------------------
    @classmethod
    def de_ficheiro(cls, caminho: str | Path) -> "Casa":
        return cls(json.loads(Path(caminho).read_text(encoding="utf-8")))

    # -- o básico ----------------------------------------------------------
    def i(self, x: int, y: int) -> int:
        return y * self.cols + x

    def dentro(self, x: int, y: int) -> bool:
        return 0 <= x < self.cols and 0 <= y < self.rows

    def eh_parede(self, x: int, y: int) -> bool:
        """Bloqueado — pela planta OU pelo que ela aprendeu que está ali.

        As duas coisas contam do mesmo modo para quem planeia e para quem
        verifica colisões, e é essa a ideia: a planta sabe as paredes, a
        memória sabe a mobília, e ao robô interessa-lhe é «passo ou não».
        """
        if not self.dentro(x, y):
            return True
        i = self.i(x, y)
        if self.parede[i] == 1:
            return True
        return self.aprendido is not None and self.aprendido[i] == 1

    def definir_aprendido(self, ocupadas: bytearray | None) -> None:
        """Trocar a camada aprendida. Deita fora as contas que dependiam dela."""
        if ocupadas is not None and len(ocupadas) != self.cols * self.rows:
            raise ValueError("a camada aprendida não tem o tamanho da planta")
        self.aprendido = ocupadas
        self.invalidar()

    def invalidar(self) -> None:
        self._campos = {}
        self._folga = None
        self._maior = 0.0

    def celulas_aprendidas(self) -> int:
        return sum(self.aprendido) if self.aprendido else 0

    def centro(self, x: int, y: int) -> tuple[float, float]:
        return ((x + 0.5) * self.cm, (y + 0.5) * self.cm)

    def largura_cm(self) -> float:
        return self.cols * self.cm

    def altura_cm(self) -> float:
        return self.rows * self.cm

    def indice_divisao(self, nome: str) -> int:
        """Aceita «sala», «Sala», «a sala», «à sala» — o LLM não escreve sempre igual."""
        alvo = _normalizar(nome)
        for k, d in enumerate(self.divisoes):
            if _normalizar(d.nome) == alvo:
                return k
        for k, d in enumerate(self.divisoes):   # depois, por conter
            if alvo and (alvo in _normalizar(d.nome) or _normalizar(d.nome) in alvo):
                return k
        return -1

    def nomes(self) -> list[str]:
        return [d.nome for d in self.divisoes]

    # -- geometria ---------------------------------------------------------
    def livre(self, x: float, y: float, r: float) -> bool:
        """Cabe um círculo de raio r com o centro em (x, y)?"""
        cm = self.cm
        x0, x1 = int(math.floor((x - r) / cm)), int(math.floor((x + r) / cm))
        y0, y1 = int(math.floor((y - r) / cm)), int(math.floor((y + r) / cm))
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                if not self.eh_parede(cx, cy):
                    continue
                px = min(max(x, cx * cm), (cx + 1) * cm)
                py = min(max(y, cy * cm), (cy + 1) * cm)
                if (x - px) ** 2 + (y - py) ** 2 < r * r:
                    return False
        return True

    def linha_de_vista(self, a: tuple[float, float], b: tuple[float, float], r: float) -> bool:
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        passos = max(2, math.ceil(d / (self.cm * 0.4)))
        for k in range(1, passos):
            t = k / passos
            if not self.livre(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, r):
                return False
        return True

    def folga(self) -> list[int]:
        """A quantos quadrados de parede está cada quadrado."""
        if self._folga is not None:
            return self._folga
        n = self.cols * self.rows
        d = [9999] * n
        fila = []
        for i in range(n):
            if self.parede[i]:
                d[i] = 0
                fila.append(i)
        cab = 0
        while cab < len(fila):
            i = fila[cab]
            cab += 1
            x, y = i % self.cols, i // self.cols
            for dx, dy in VIZINHOS4:
                nx, ny = x + dx, y + dy
                if not self.dentro(nx, ny):
                    continue
                j = self.i(nx, ny)
                if d[j] > d[i] + 1:
                    d[j] = d[i] + 1
                    fila.append(j)
        self._folga = d
        return d

    # -- o campo de distância ---------------------------------------------
    def ponto_da_divisao(self, divisao: int) -> tuple[int, int] | None:
        """O quadrado mais «no meio» de uma divisão — o mais longe das paredes.

        ⚠️ «Vai à sala» não quer dizer «encosta-te à ombreira da sala». Com o
        destino a ser a divisão inteira, o quadrado logo a seguir à porta já
        contava como chegada, e a Lylla parava com meio corpo no corredor a
        dizer que tinha chegado. Agora há um ponto lá dentro, e é a esse que
        ela vai.

        ⚠️ E não vale escolher um quadrado onde ela JÁ SABE que está alguma
        coisa. Com a planta desenhada isto quase nunca muda nada — o meio da
        sala está livre. Mas no modo descoberta a planta vem sem paredes
        nenhumas (as paredes são as que ela desenhou com o ultrassom), e aí o
        «meio da divisão» calculado só pela planta cai muitas vezes dentro de
        uma parede a sério: o destino ficava num sítio onde ela nunca podia
        chegar, e a missão não tinha fim possível. Por isso a camada aprendida
        também conta — e se não sobrar nada, volta-se à regra antiga em vez de
        devolver «não há destino».
        """
        folga = self.folga()
        melhor, melhor_f = None, -1
        reserva, reserva_f = None, -1
        for i, z in enumerate(self.zona):
            if z != divisao or self.parede[i]:
                continue
            if folga[i] > reserva_f:
                reserva_f, reserva = folga[i], i
            if self.aprendido is not None and self.aprendido[i] == 1:
                continue
            if folga[i] > melhor_f:
                melhor_f, melhor = folga[i], i
        if melhor is None:
            melhor = reserva
        return None if melhor is None else (melhor % self.cols, melhor // self.cols)

    def campo_de_celula(self, cx: int, cy: int) -> list[float]:
        """O campo de distância a partir de UM quadrado (ver ponto_da_divisao)."""
        chave = -(self.i(cx, cy) + 1)
        if chave in self._campos:
            return self._campos[chave]
        n = self.cols * self.rows
        dist = [math.inf] * n
        folga = self.folga()
        inicio = self.i(cx, cy)
        dist[inicio] = 0.0
        monte: list[tuple[float, int]] = [(0.0, inicio)]
        while monte:
            d, i = heapq.heappop(monte)
            if d > dist[i]:
                continue
            x, y = i % self.cols, i // self.cols
            for dx, dy, custo in VIZINHOS:
                nx, ny = x + dx, y + dy
                if not self.dentro(nx, ny) or self.eh_parede(nx, ny):
                    continue
                if dx and dy and (self.eh_parede(x + dx, y) or self.eh_parede(x, y + dy)):
                    continue
                j = self.i(nx, ny)
                f = folga[j]
                castigo = 2.6 if f <= 1 else (0.7 if f == 2 else 0.0)
                nd = d + (custo + castigo) * self.cm
                if nd < dist[j]:
                    dist[j] = nd
                    heapq.heappush(monte, (nd, j))
        self._campos[chave] = dist
        return dist

    def campo_ate(self, divisao: int) -> list[float]:
        """Quantos centímetros faltam, de cada quadrado, até àquela divisão.

        Dijkstra a partir do destino, para trás. Calcula-se UMA vez por
        destino e serve a partir de qualquer ponto da casa — é por isso que
        a Lylla pode ser empurrada, dar uma volta a fugir do gato, e continuar
        a saber para onde ir sem voltar a planear nada.
        """
        if divisao in self._campos:
            return self._campos[divisao]
        n = self.cols * self.rows
        dist = [math.inf] * n
        folga = self.folga()
        monte: list[tuple[float, int]] = []
        for i in range(n):
            if self.parede[i] or self.zona[i] != divisao:
                continue
            dist[i] = 0.0
            heapq.heappush(monte, (0.0, i))
        while monte:
            d, i = heapq.heappop(monte)
            if d > dist[i]:
                continue
            x, y = i % self.cols, i // self.cols
            for dx, dy, custo in VIZINHOS:
                nx, ny = x + dx, y + dy
                if not self.dentro(nx, ny) or self.eh_parede(nx, ny):
                    continue
                if dx and dy and (self.eh_parede(x + dx, y) or self.eh_parede(x, y + dy)):
                    continue
                j = self.i(nx, ny)
                f = folga[j]
                castigo = 2.6 if f <= 1 else (0.7 if f == 2 else 0.0)
                nd = d + (custo + castigo) * self.cm
                if nd < dist[j]:
                    dist[j] = nd
                    heapq.heappush(monte, (nd, j))
        self._campos[divisao] = dist
        return dist

    def distancia_em(self, campo: list[float], x: float, y: float) -> float:
        cx, cy = int(x // self.cm), int(y // self.cm)
        if not self.dentro(cx, cy):
            return math.inf
        return campo[self.i(cx, cy)]

    def na_divisao(self, divisao: int, x: float, y: float) -> bool:
        cx, cy = int(x // self.cm), int(y // self.cm)
        return self.dentro(cx, cy) and self.zona[self.i(cx, cy)] == divisao

    def descer(self, campo: list[float], x: float, y: float, limite: int = 400) -> list[tuple[float, float]]:
        """O caminho, quadrado a quadrado, sempre para quem está mais perto."""
        cx, cy = int(x // self.cm), int(y // self.cm)
        if not self.dentro(cx, cy) or not math.isfinite(campo[self.i(cx, cy)]):
            return []
        pontos = [(x, y)]
        visto = set()
        for _ in range(limite):
            aqui = self.i(cx, cy)
            if campo[aqui] == 0 or aqui in visto:
                break
            visto.add(aqui)
            melhor, melhor_d = None, campo[aqui]
            for dx, dy, _c in VIZINHOS:
                nx, ny = cx + dx, cy + dy
                if not self.dentro(nx, ny) or self.eh_parede(nx, ny):
                    continue
                if dx and dy and (self.eh_parede(cx + dx, cy) or self.eh_parede(cx, cy + dy)):
                    continue
                d = campo[self.i(nx, ny)]
                if d < melhor_d:
                    melhor_d, melhor = d, (nx, ny)
            if melhor is None:
                break
            cx, cy = melhor
            pontos.append(self.centro(cx, cy))
        return pontos

    def celula_util(self, campo: list[float], x: float, y: float, raio: int = 3):
        """A célula mais próxima daqui de onde SE SABE ir para o destino.

        ╔══════════════════════════════════════════════════════════════════╗
        ║  ⚠️ ISTO EXISTE POR CAUSA DE UM BUG QUE CUSTOU UMA MANHÃ.        ║
        ║                                                                  ║
        ║  A Lylla persegue um ponto da rota calculado a partir de onde    ║
        ║  ELA JULGA ESTAR. E ela julga-se 20 ou 30 cm ao lado — o que num ║
        ║  quadrado de 20 cm quer dizer que, sempre que passa perto de uma ║
        ║  parede, a posição em que ela acredita cai DENTRO da parede.     ║
        ║                                                                  ║
        ║  Dentro de uma parede não há caminho: o campo de distância vale  ║
        ║  infinito, a descida não sai do sítio, e a função devolvia... a  ║
        ║  própria posição dela. O piloto recebia «o teu alvo é onde já    ║
        ║  estás», o ângulo dava zero, e ele virava-se para o mesmo ponto  ║
        ║  cardeal e ficava a rodar. Era isso que se via no corredor:      ║
        ║  «está sempre a rodar para o mesmo lado». Acontecia em 30% dos   ║
        ║  passos.                                                         ║
        ║                                                                  ║
        ║  A correção é esta: se onde ela julga estar não serve, procura-se║
        ║  o quadrado livre mais próximo que sirva. Ela está a 20 cm dali. ║
        ╚══════════════════════════════════════════════════════════════════╝
        """
        cx, cy = int(x // self.cm), int(y // self.cm)
        if self.dentro(cx, cy) and math.isfinite(campo[self.i(cx, cy)]) \
                and not self.eh_parede(cx, cy):
            return (cx, cy)
        melhor, melhor_d = None, math.inf
        for r in range(1, raio + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    nx, ny = cx + dx, cy + dy
                    if not self.dentro(nx, ny) or self.eh_parede(nx, ny):
                        continue
                    d = campo[self.i(nx, ny)]
                    if math.isfinite(d) and d < melhor_d:
                        melhor_d, melhor = d, (nx, ny)
            if melhor is not None:
                return melhor
        return None

    def alvo_local(self, campo: list[float], x: float, y: float,
                   lookahead_cm: float, raio_cm: float) -> tuple[float, float]:
        """O ponto que a Lylla persegue: o mais longe da rota que ainda vê.

        Não é o destino — é um ponto a ~meio metro à frente, na rota. É isto
        que faz uma curva parecer uma curva e não uma sucessão de correções.

        ⚠️ NUNCA devolve a posição de quem pergunta: ver celula_util().
        """
        celula = self.celula_util(campo, x, y)
        if celula is None:
            return (x, y)                      # a casa toda é inalcançável daqui
        partida = self.centro(*celula)
        acumulado = 0.0
        melhor = None
        ultimo = partida
        for p in self.descer(campo, partida[0], partida[1], limite=60)[1:]:
            acumulado += math.hypot(p[0] - ultimo[0], p[1] - ultimo[1])
            ultimo = p
            if self.linha_de_vista((x, y), p, raio_cm + 1):
                melhor = p
            if acumulado >= lookahead_cm:
                break
        if melhor is not None:
            return melhor
        # nem o primeiro ponto da rota se vê daqui (há uma parede pelo meio,
        # porque ela não está onde julga) — segue-se para lá à mesma, que é o
        # que faz sair do buraco; os sensores tratam do resto.
        return ultimo if math.hypot(ultimo[0] - x, ultimo[1] - y) > 1.0 else partida


def _normalizar(s: str) -> str:
    """Sem maiúsculas, sem acentos, sem artigos — «à Sala» e «sala» é o mesmo."""
    s = s.strip().lower()
    for a, b in (("á", "a"), ("à", "a"), ("ã", "a"), ("â", "a"), ("é", "e"), ("ê", "e"),
                 ("í", "i"), ("ó", "o"), ("õ", "o"), ("ô", "o"), ("ú", "u"), ("ç", "c")):
        s = s.replace(a, b)
    mudou = True
    while mudou:                     # «para o quarto» tem DOIS artigos a tirar
        mudou = False
        for artigo in ("para ", "ate ", "ao ", "no ", "na ", "do ", "da ", "a ", "o "):
            if s.startswith(artigo):
                s = s[len(artigo):]
                mudou = True
                break
    return s.strip()
