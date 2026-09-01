#!/usr/bin/env python3
"""O ENSAIO — a viagem toda, com um ultrassom que mente como o verdadeiro.

    ROBO_SIMULAR=1 python scripts/ensaio_navegacao.py
    ROBO_SIMULAR=1 python scripts/ensaio_navegacao.py --de sala --para escritório
    ROBO_SIMULAR=1 python scripts/ensaio_navegacao.py --sem-varrimento   # comparar

Porque é que isto existe e o `check_health.py` não chega: a simulação normal
devolve sempre «100 cm» ao ultrassom e nunca faz as rodas patinar, por isso
não consegue mostrar a única coisa que interessa aqui — que a posição que ela
julga ter se afasta da verdadeira, e que o varrimento a volta a pôr no sítio.

Aqui há DUAS posições:

    a VERDADEIRA   que este ensaio conhece e o robô nunca vê
    a QUE ELA JULGA que sai da odometria, e que se engana um bocadinho a cada
                    passo — porque uma roda patina 6% mais do que a outra

e um ultrassom que espelha em paredes oblíquas (70% dos ecos rasos perdem-se)
e mede com 6 cm de ruído. É o robô a sério, sem o robô.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robot.hardware import sensors          # noqa: E402
from robot.navigation import ir_para        # noqa: E402
from robot.navigation.pose import Pose      # noqa: E402


class Mundo:
    """A casa como ela é mesmo, e a Lylla como ela está mesmo."""

    def __init__(self, casa, semente: int, patinagem: float = 0.06, ruido: float = 6.0):
        self.casa = casa
        self.rnd = random.Random(semente)
        self.patinagem = patinagem
        self.ruido = ruido
        self.verdadeira = Pose()
        self.percorrido = 0.0
        self.embates = 0

    def por_em(self, x: float, y: float, rumo: float) -> None:
        self.verdadeira.definir(x, y, rumo)

    def distancia_cm(self) -> float:
        """O ultrassom, com os dois defeitos que ele tem mesmo."""
        casa, cm = self.casa, self.casa.cm
        x, y, ang = self.verdadeira.x, self.verdadeira.y, self.verdadeira.rumo
        dx, dy = math.cos(ang), math.sin(ang)
        cx, cy = int(x // cm), int(y // cm)
        px, py = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
        ddx = abs(cm / dx) if dx else math.inf
        ddy = abs(cm / dy) if dy else math.inf
        tx = (((cx + 1) * cm if dx > 0 else cx * cm) - x) / dx if dx else math.inf
        ty = (((cy + 1) * cm if dy > 0 else cy * cm) - y) / dy if dy else math.inf
        while True:
            if tx < ty:
                cx += px; t = tx; tx += ddx; normal = (1.0, 0.0)
            else:
                cy += py; t = ty; ty += ddy; normal = (0.0, 1.0)
            if t > 200:
                return 999.0
            if casa.eh_parede(cx, cy):
                # incidência rasa: o eco vai-se embora e ela «não vê nada»
                if abs(dx * normal[0] + dy * normal[1]) < math.cos(math.radians(40)) \
                        and self.rnd.random() < 0.7:
                    return 999.0
                return max(4.0, t + self.rnd.gauss(0, self.ruido))

    def avancar(self, esq: float, dir_: float, dt: float, v_max: float, entre_eixos: float) -> None:
        """O que as rodas fizeram MESMO — e a parede que não deixa passar.

        Sem esta segunda parte o ensaio mentia a favor: um robô convencido no
        sítio errado atravessava as paredes e chegava à mesma.
        """
        antes = (self.verdadeira.x, self.verdadeira.y, self.verdadeira.rumo)
        self.verdadeira.avancar(esq * (1 - self.patinagem), dir_, dt, v_max, entre_eixos)
        if not self.casa.livre(self.verdadeira.x, self.verdadeira.y, 12.0):
            self.verdadeira.x, self.verdadeira.y = antes[0], antes[1]   # bateu: fica
            self.embates += 1
            return
        self.percorrido += math.hypot(self.verdadeira.x - antes[0], self.verdadeira.y - antes[1])

    def erro_cm(self, pose: Pose) -> float:
        return math.hypot(pose.x - self.verdadeira.x, pose.y - self.verdadeira.y)


def main() -> int:
    p = argparse.ArgumentParser(description="Ensaiar uma viagem com um ultrassom realista.")
    p.add_argument("--de", default=None, help="divisão de partida (por omissão: onde a planta a põe)")
    p.add_argument("--para", default="escritório", help="divisão de destino")
    p.add_argument("--sem-varrimento", action="store_true",
                   help="desliga a correção pelo mapa, para se ver a diferença")
    p.add_argument("--sem-mapa", action="store_true", help="não aprende mobília nenhuma")
    p.add_argument("--patinagem", type=float, default=0.06, help="quanto uma roda anda a menos")
    p.add_argument("--semente", type=int, default=7)
    p.add_argument("--varrer", type=float, default=None, help="velocidade do varrimento")
    p.add_argument("--gatilho", type=float, default=None, help="deriva a que vai ver onde está")
    p.add_argument("--silencio", action="store_true", help="só o resultado")
    p.add_argument("--piloto", default=None, help="outro piloto.json (ex.: data/piloto-1feixe.json)")
    args = p.parse_args()

    base = ir_para._cfg
    trocas: dict[str, float] = {}
    if args.varrer:
        trocas["velocidade_varrer"] = args.varrer
    if args.gatilho:
        trocas["deriva_para_varrer"] = args.gatilho
    if args.sem_varrimento:
        # números altos que nunca se alcançam = nunca vai ver onde está
        trocas["deriva_para_varrer"] = 10_000.0
        trocas["metros_entre_varrimentos"] = 10_000.0
    if args.piloto:
        trocas["piloto"] = args.piloto
    if trocas:
        ir_para._cfg = lambda c, o: trocas.get(c, base(c, o))

    erro = ir_para.carregar(forcar=True)
    if erro:
        print(f"❌ {erro}")
        return 1
    casa = ir_para._casa
    if args.sem_mapa:
        ir_para._memoria = None

    if args.de:
        if ir_para.assumir(args.de):
            print(f"❌ não conheço «{args.de}»")
            return 1

    mundo = Mundo(casa, args.semente, args.patinagem)
    mundo.por_em(ir_para._pose.x, ir_para._pose.y, ir_para._pose.rumo)
    sensors.distancia_cm = mundo.distancia_cm
    sensors.ha_precipicio = lambda: False

    estado, mensagem = ir_para.comecar(args.para)
    print(f"\n🤖  {mensagem}")
    if estado == "recusa":
        return 1

    piloto = ir_para._piloto
    print(f"    de ({mundo.verdadeira.x:.0f}, {mundo.verdadeira.y:.0f}) cm\n")

    ultima_razao, varrimentos, pior_erro = "", 0, 0.0
    for passo in range(3000):
        antes = (ir_para._pose.x, ir_para._pose.y, ir_para._pose.rumo)
        comando = ir_para.um_passo(dt=0.1)
        # o que as rodas fizeram mesmo — a partir do que o robô mandou fazer
        if (ir_para._pose.x, ir_para._pose.y, ir_para._pose.rumo) != antes or comando.esquerdo or comando.direito:
            mundo.avancar(comando.esquerdo, comando.direito, 0.1,
                          piloto.v_max_cm_s, piloto.entre_eixos_cm)
        pior_erro = max(pior_erro, mundo.erro_cm(ir_para._pose))

        if comando.razao != ultima_razao:
            mudou, ultima_razao = True, comando.razao
            if comando.razao == "a ver onde estou":
                varrimentos += 1
        else:
            mudou = False
        if mudou and not args.silencio:
            print(f"    {passo*0.1:6.1f}s · {comando.razao:22s} "
                  f"· julga-se enganada em {ir_para._pose.deriva_cm:4.0f} cm "
                  f"· está mesmo a {mundo.erro_cm(ir_para._pose):4.0f} cm")
            c = ir_para._ultima_correcao
            if comando.razao in ("já sei onde estou", "perdi-me") and c is not None:
                print(f"             └ {c.amostras_usadas} ecos · erro {c.erro_cm:.1f} cm "
                      f"· rival {c.erro_rival_cm:.1f} · salto {c.salto_cm:.0f} cm "
                      f"· {'ambígua' if c.ambigua else 'clara'}")
        if comando.terminou:
            break

    # A verdade: ela chegou MESMO à divisão, ou só julga que chegou?
    idx = casa.indice_divisao(args.para)
    mesmo = casa.na_divisao(idx, mundo.verdadeira.x, mundo.verdadeira.y)
    cx = int(mundo.verdadeira.x // casa.cm)
    cy = int(mundo.verdadeira.y // casa.cm)
    onde = casa.zona[casa.i(cx, cy)] if casa.dentro(cx, cy) else -1
    nome = casa.divisoes[onde].nome if onde >= 0 else "no meio de nada"

    if args.silencio:
        print(f"  varrer={args.varrer or 0.32} gatilho={args.gatilho or 20} semente={args.semente}: "
              f"{'CHEGOU  ' if mesmo else 'falhou  '} {comando.razao:12s} "
              f"· {mundo.percorrido/100:4.1f} m · {varrimentos} voltas "
              f"· pior erro {pior_erro:3.0f} cm · {mundo.embates} embates "
              f"· {Path(str(ir_para._cfg('piloto', 'data/piloto.json'))).stem}")
        ir_para.parar()
        return 0 if mesmo else 2

    print(f"\n    ┌─ {comando.razao}")
    print(f"    │  andou {mundo.percorrido/100:.1f} m · {varrimentos} varrimento(s) "
          f"· {mundo.embates} embates em paredes")
    print(f"    │  está MESMO {'' if mesmo else 'em ' + nome + ' — '}"
          f"{'na divisão certa ✅' if mesmo else 'NÃO chegou ❌'}")
    print(f"    │  erro final {mundo.erro_cm(ir_para._pose):.0f} cm · pior momento {pior_erro:.0f} cm")
    if ir_para._memoria:
        r = ir_para._memoria.resumo()
        print(f"    └─ mapa: {r.leituras} leituras · {round(r.explorado*100)}% da casa conhecida "
              f"· {casa.celulas_aprendidas()} quadrados de mobília\n")
    else:
        print("    └─ sem mapa\n")
    ir_para.parar()
    return 0 if mesmo else 2


if __name__ == "__main__":
    raise SystemExit(main())
