"""A MEMÓRIA DO ESPAÇO — o que ela foi aprendendo sobre onde há coisas.

╔══════════════════════════════════════════════════════════════════════════╗
║  A IDEIA, EM UMA LINHA                                                   ║
║                                                                          ║
║  Uma parede vista cem vezes vale muito. Um saco visto duas vezes vale    ║
║  pouco. Cada leitura do ultrassom soma ou subtrai um bocadinho de        ║
║  evidência a cada quadrado, e o mapa é a soma.                           ║
║                                                                          ║
║  Isto tem nome — mapa de ocupação em *log-odds*, de 1985 — e há duas     ║
║  peças que não são óbvias e sem as quais NÃO FUNCIONA:                   ║
║                                                                          ║
║  1. MARCAR TAMBÉM O VAZIO. Uma leitura de 120 cm não é um facto, são     ║
║     dois: «há alguma coisa a 120 cm» E «não há NADA entre 0 e 120».      ║
║     Sem o segundo, o saco que já saiu do corredor fica no mapa para      ║
║     sempre — ninguém o apaga. Com ele, os raios que passam por onde o    ║
║     saco estava apagam-no sozinhos. É esta metade que faz o mapa         ║
║     corrigir-se em vez de encher de fantasmas.                           ║
║                                                                          ║
║  2. UM TETO NA EVIDÊNCIA (±5). Sem limite, uma parede vista mil vezes    ║
║     precisava de mil leituras contrárias para desaparecer — e no dia em  ║
║     que se muda a estante, ela ficava no mapa durante uma semana. Com    ║
║     teto, o mapa muda de ideias em segundos e continua a distinguir a    ║
║     parede do saco.                                                      ║
╚══════════════════════════════════════════════════════════════════════════╝

⚠️ O ULTRASSOM VÊ MAL PAREDES, e isso está desenhado nas contas aqui.

   · O som reflete como um espelho. Uma parede que não esteja quase
     perpendicular ao feixe devolve o eco para o lado, e o sensor diz «não há
     nada» — e marcar vazio através de uma parede é o erro que estraga um
     mapa. Por isso uma leitura SEM eco só marca vazio até 70% do alcance, e
     com metade do peso: a ausência de eco é uma pista fraca, não um facto.
   · O feixe tem ~15° de abertura. A 2 m, o eco pode vir de meio metro de
     largura e não se sabe de onde. Por isso o vazio marca-se no CONE TODO
     (isso é seguro: se o eco veio a 120 cm, não há nada mais perto em lado
     nenhum do cone) e o obstáculo marca-se espalhado pelo arco, com o peso
     dividido. São muitas leituras de sítios diferentes que o afiam.

A planta (casa.json) e isto não competem: a planta dá as PAREDES, que o sonar
mapeia mal; isto dá a MOBÍLIA, que a planta não sabe. Cada um no que é bom.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

# A escada de caracteres com que o mapa se grava. Vê-se num editor de texto:
#   'e' = de certeza vazio  ·  '.' = não sei  ·  '#' = de certeza ocupado
# (o '#' é de propósito o mesmo símbolo do casa.json)
ESCADA = "edcba.1234#"
TETO = 5.0                      # o log-odds nunca passa de ±isto

# Quanto vale cada leitura. Positivo = «está aqui alguma coisa».
PESO_OCUPADO = 0.85
PESO_LIVRE = -0.40
PESO_LIVRE_SEM_ECO = -0.20      # sem eco é pista fraca: metade do peso
# ⚠️ E SÓ ATÉ AQUI. Um silêncio de sonar tem duas causas que se não
# distinguem: não há nada, ou há uma parede de lado que devolveu o eco para
# longe. Encurtar isto para 70 cm parecia a correção óbvia — mediu-se e não
# muda praticamente nada (48% das paredes encontradas nos dois casos), porque
# o que aqui protege as paredes é o `tocadas` lá em baixo: dentro de UMA
# leitura, o «está aqui» ganha ao «está vazio». Era ISSO que faltava no
# browser, e era por isso que lá o mapa se apagava a si próprio.
FRACAO_SEM_ECO = 0.70           # e só até 70% do alcance

TOLERANCIA_CM = 12.0            # a espessura da banda «está aqui»
SUB_RAIOS = 5                   # em quantas fatias se parte o cone
# ⚠️ A partir daqui o PLANEAMENTO trata a célula como parede — e desviar a
# rota por causa de um eco falso é pior do que passar lá e travar com os
# sensores. 2.5 quer dizer, na prática, «visto muitas vezes, de sítios
# diferentes»: o sofá que está sempre ali entra na rota, o saco visto duas
# vezes não. É este número que faz o que o Bruno queria — a média.
LIMIAR_OCUPADO = 2.5
LIMIAR_LIVRE = -1.0


@dataclass
class Resumo:
    ocupadas: int = 0
    livres: int = 0
    desconhecidas: int = 0
    leituras: int = 0

    @property
    def explorado(self) -> float:
        total = self.ocupadas + self.livres + self.desconhecidas
        return (self.ocupadas + self.livres) / total if total else 0.0


class MemoriaDoEspaco:
    """Uma grelha de evidência, do mesmo tamanho e escala que a planta."""

    def __init__(self, cols: int, rows: int, cm: float, abertura_graus: float = 15.0) -> None:
        self.cols, self.rows, self.cm = int(cols), int(rows), float(cm)
        self.abertura = math.radians(abertura_graus)
        self.valores = [0.0] * (self.cols * self.rows)
        self.leituras = 0

    # -- criar e guardar ---------------------------------------------------
    @classmethod
    def de_casa(cls, casa, abertura_graus: float = 15.0) -> "MemoriaDoEspaco":
        return cls(casa.cols, casa.rows, casa.cm, abertura_graus)

    @classmethod
    def de_ficheiro(cls, caminho: str | Path) -> "MemoriaDoEspaco":
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        if dados.get("formato") != "lylla-mapa-1":
            raise ValueError("Isto não é um mapa da Lylla (falta formato: lylla-mapa-1).")
        m = cls(dados["colunas"], dados["linhas"], dados["cm_por_celula"])
        m.leituras = int(dados.get("leituras", 0))
        passo = 2 * TETO / (len(ESCADA) - 1)
        for y in range(m.rows):
            linha = dados["celulas"][y]
            for x in range(m.cols):
                pos = ESCADA.find(linha[x])
                if pos >= 0:
                    m.valores[y * m.cols + x] = -TETO + pos * passo
        return m

    def guardar(self, caminho: str | Path, casa_nome: str = "") -> None:
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        Path(caminho).write_text(json.dumps({
            "formato": "lylla-mapa-1",
            "casa": casa_nome,
            "colunas": self.cols, "linhas": self.rows, "cm_por_celula": self.cm,
            "leituras": self.leituras,
            "legenda": "e=vazio · .=desconhecido · #=ocupado (escada: " + ESCADA + ")",
            "celulas": self.linhas_de_texto(),
        }, ensure_ascii=False, indent=1), encoding="utf-8")

    def linhas_de_texto(self) -> list[str]:
        passo = 2 * TETO / (len(ESCADA) - 1)
        linhas = []
        for y in range(self.rows):
            linha = []
            for x in range(self.cols):
                v = max(-TETO, min(TETO, self.valores[y * self.cols + x]))
                linha.append(ESCADA[int(round((v + TETO) / passo))])
            linhas.append("".join(linha))
        return linhas

    # -- ler ---------------------------------------------------------------
    def i(self, x: int, y: int) -> int:
        return y * self.cols + x

    def dentro(self, x: int, y: int) -> bool:
        return 0 <= x < self.cols and 0 <= y < self.rows

    def valor(self, cx: int, cy: int) -> float:
        return self.valores[self.i(cx, cy)] if self.dentro(cx, cy) else 0.0

    def probabilidade(self, cx: int, cy: int) -> float:
        """0 = de certeza livre · 0,5 = não sei · 1 = de certeza ocupado."""
        return 1.0 / (1.0 + math.exp(-self.valor(cx, cy)))

    def ocupadas(self, limiar: float = LIMIAR_OCUPADO) -> bytearray:
        """A camada que o planeamento usa: 1 onde há evidência a sério."""
        return bytearray(1 if v >= limiar else 0 for v in self.valores)

    def resumo(self) -> Resumo:
        r = Resumo(leituras=self.leituras)
        for v in self.valores:
            if v >= LIMIAR_OCUPADO:
                r.ocupadas += 1
            elif v <= LIMIAR_LIVRE:
                r.livres += 1
            else:
                r.desconhecidas += 1
        return r

    def limpar(self) -> None:
        self.valores = [0.0] * (self.cols * self.rows)
        self.leituras = 0

    # -- escrever ----------------------------------------------------------
    def atualizar(self, x: float, y: float, rumo: float,
                  distancia_cm: float, alcance_cm: float) -> None:
        """Uma leitura do ultrassom, feita de (x, y) a olhar para `rumo`.

        `distancia_cm` >= `alcance_cm` quer dizer «não voltou eco nenhum».
        """
        self.leituras += 1
        sem_eco = distancia_cm >= alcance_cm * 0.99
        alcance_livre = alcance_cm * FRACAO_SEM_ECO if sem_eco else max(0.0, distancia_cm - TOLERANCIA_CM)
        peso_livre = PESO_LIVRE_SEM_ECO if sem_eco else PESO_LIVRE
        passo = self.cm * 0.5
        meio = self.abertura / 2
        tocadas: dict[int, float] = {}

        for k in range(SUB_RAIOS):
            ang = rumo + (-meio + self.abertura * k / (SUB_RAIOS - 1) if SUB_RAIOS > 1 else 0.0)
            cos_a, sin_a = math.cos(ang), math.sin(ang)

            # ---- o vazio: o cone TODO, até onde o eco garante que não há nada
            d = passo
            while d < alcance_livre:
                cx = int((x + cos_a * d) // self.cm)
                cy = int((y + sin_a * d) // self.cm)
                if not self.dentro(cx, cy):
                    break
                chave = self.i(cx, cy)
                if chave not in tocadas or tocadas[chave] > peso_livre:
                    tocadas[chave] = peso_livre
                d += passo

            # ---- o obstáculo: espalhado pelo arco, com o peso dividido
            if sem_eco:
                continue
            peso = PESO_OCUPADO / SUB_RAIOS
            d = max(0.0, distancia_cm - TOLERANCIA_CM)
            while d <= distancia_cm + TOLERANCIA_CM:
                cx = int((x + cos_a * d) // self.cm)
                cy = int((y + sin_a * d) // self.cm)
                if self.dentro(cx, cy):
                    chave = self.i(cx, cy)
                    # ⚠️ o «está aqui» ganha sempre ao «está vazio» da mesma
                    #    leitura: a banda do eco é a única coisa que aquele
                    #    eco realmente afirma.
                    tocadas[chave] = max(tocadas.get(chave, -9.9), peso)
                d += passo

        for chave, delta in tocadas.items():
            self.valores[chave] = max(-TETO, min(TETO, self.valores[chave] + delta))
