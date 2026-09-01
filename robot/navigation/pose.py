"""ONDE É QUE ELA ACHA QUE ESTÁ.

╔══════════════════════════════════════════════════════════════════════════╗
║  ESTA É A PARTE FRACA DO SISTEMA, E É DE PROPÓSITO QUE ESTÁ ESCRITO      ║
║  AQUI EM CIMA.                                                           ║
║                                                                          ║
║  A Lylla não tem GPS dentro de casa. O que tem é conta de merceeiro:     ║
║  «mandei as rodas a esta velocidade durante um décimo de segundo, logo   ║
║  andei tanto». Isto chama-se odometria, e tem um problema conhecido:     ║
║  o erro SOMA-SE. Uma roda que patina meio centímetro num tapete nunca    ║
║  mais é recuperada. Ao fim de dez metros, ela pode julgar-se meio metro  ║
║  ao lado — e meio metro chega para tentar passar por uma parede.         ║
║                                                                          ║
║  O que este módulo faz de diferente é NÃO FINGIR. Vai somando o erro     ║
║  provável (`deriva_cm`), e quando esse erro passa do que uma porta        ║
║  perdoa, o ir_para.py PÁRA e diz que já não sabe onde está — em vez de   ║
║  continuar a andar com confiança contra o rodapé.                        ║
║                                                                          ║
║  Como se corrige, por ordem de esforço:                                  ║
║    1. dizer-lhe: «estás na cozinha» → pose.assumir("cozinha")            ║
║    2. encoders nas rodas (a mecânica do mBot2 já os tem) — corta o erro  ║
║       de patinagem, que é o maior;                                       ║
║    3. um marcador ArUco impresso em cada ombreira de porta: a câmara já  ║
║       lá está, o OpenCV já sabe lê-los, e cada porta passa a repor a     ║
║       posição a zero.                                                    ║
║  Nada disto é preciso para a Lara ver o robô ir da sala à cozinha hoje.  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ⚠️ O ERRO DE ODOMETRIA NÃO CRESCE COM A DISTÂNCIA — CRESCE COM O QUADRADO
#    DELA, e perceber isto é a diferença entre um robô que sabe que está
#    perdido e um que se julga bem.
#
#    A razão: o erro que interessa não é «andei 3 cm a mais», é «fiquei meio
#    grau torto». Uma roda que ande 1,5% menos do que a outra faz o robô
#    curvar de leve para sempre; ao fim de um metro isso é meio grau e não se
#    nota, ao fim de cinco metros são dez graus e ela está a um metro de onde
#    julga. O desvio lateral é o ângulo VEZES a distância que se anda DEPOIS
#    de o ganhar — por isso soma-se, e por isso acelera.
#
#    Medir estes números: manda-se andar 3 m em frente e mede-se com a fita
#    quanto andou (dá o ERRO_POR_CM) e quanto se desviou para o lado (dá o
#    ERRO_RUMO_POR_CM). Depois compensa-se o grosso em motores.compensacao_*,
#    e o que fica é isto.
ERRO_POR_CM = 0.02              # o que ela erra a andar a direito
ERRO_RUMO_POR_CM = 0.001        # radianos de torto ganhos por cm andado (~1,5% de roda)
ERRO_POR_RADIANO_CM = 0.8       # e o que erra em cada rotação que faz de propósito
ERRO_RUMO_POR_RADIANO = 0.03    # ... que também deixa o rumo mais incerto


@dataclass
class Pose:
    x: float = 0.0             # centímetros, no referencial da planta
    y: float = 0.0
    rumo: float = 0.0          # radianos; 0 = para a direita na planta
    deriva_cm: float = 0.0     # quanto é que ela pode estar enganada
    incerteza_rumo: float = 0.0  # ... e quão torta pode estar (radianos)
    percorrido_cm: float = 0.0   # quanto andou desde a última correção

    def definir(self, x: float, y: float, rumo: float, deriva_cm: float = 0.0) -> None:
        self.x, self.y, self.rumo = x, y, rumo
        self.deriva_cm = deriva_cm
        self.incerteza_rumo = deriva_cm * ERRO_RUMO_POR_CM
        self.percorrido_cm = 0.0

    def avancar(self, esquerdo: float, direito: float, dt: float,
                v_max_cm_s: float, entre_eixos_cm: float) -> tuple[float, float]:
        """Integra um passo. Devolve (velocidade cm/s, rotação rad/s).

        `esquerdo` e `direito` são frações da velocidade máxima, que é o que
        o piloto produz — e não a potência do motor. A tradução entre as duas
        vive no ir_para.py, e é a única aproximação grosseira do sistema.
        """
        vl = esquerdo * v_max_cm_s
        vr = direito * v_max_cm_s
        v = (vl + vr) / 2.0
        w = (vr - vl) / entre_eixos_cm
        self.x += v * math.cos(self.rumo) * dt
        self.y += v * math.sin(self.rumo) * dt
        self.rumo = _normalizar_angulo(self.rumo + w * dt)

        andado = abs(v) * dt
        rodado = abs(w) * dt
        self.percorrido_cm += andado
        # primeiro o rumo fica mais incerto...
        self.incerteza_rumo += andado * ERRO_RUMO_POR_CM + rodado * ERRO_RUMO_POR_RADIANO
        # ... e só depois esse rumo torto é multiplicado pelo que se anda com ele
        self.deriva_cm += andado * (ERRO_POR_CM + self.incerteza_rumo) + rodado * ERRO_POR_RADIANO_CM
        return v, w

    def confianca(self, limite_cm: float) -> float:
        """1.0 = acabou de ser corrigida · 0.0 = já não vale nada."""
        if limite_cm <= 0:
            return 0.0
        return max(0.0, 1.0 - self.deriva_cm / limite_cm)


def _normalizar_angulo(a: float) -> float:
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a
