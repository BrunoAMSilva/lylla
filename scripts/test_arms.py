#!/usr/bin/env python3
"""TESTAR OS BRAÇOS.

    python scripts/test_arms.py                  passa por todas as poses
    python scripts/test_arms.py acenar           corre um gesto
    python scripts/test_arms.py --juntas         move cada junta uma a uma
    python scripts/test_arms.py --limites ombro_dir
                                                 encontra os limites de uma junta

⚠️  A PRIMEIRA VEZ: monta os servos SEM os braços colados, e corre
    `--juntas` para confirmar que cada canal do PCA9685 corresponde à junta
    certa. Um servo com o horn na posição errada bate no corpo à primeira.

Como descobrir os limites (fase 8): corre `--limites`, vê onde o braço bate
no corpo, e escreve esses números no config/robot.yaml.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402
from robot.gestures import GESTOS, POSES, validar_todos  # noqa: E402
from robot.hardware import arms  # noqa: E402


def _juntas() -> dict:
    return config.obter("bracos.juntas", {}) or {}


def todas_as_poses() -> int:
    print("\n🦾 A passar por todas as poses…\n")
    arms.pose("descanso")
    time.sleep(1)
    for nome in POSES:
        print(f"   ▶ {nome}")
        arms.pose(nome)
        time.sleep(1.2)
    arms.pose("descanso")

    print("\n🦾 E agora os gestos…\n")
    for nome in GESTOS:
        print(f"   ▶ {nome}")
        arms.gesto(nome)
        time.sleep(0.6)

    arms.relaxar()
    print("\n✅ Feito. Servos relaxados.\n")
    return 0


def uma_junta_de_cada_vez() -> int:
    juntas = _juntas()
    print(f"\n🔍 {len(juntas)} juntas configuradas.")
    print("   Vê qual se mexe e confirma que é a que diz o nome.\n")
    for nome, cfg in juntas.items():
        print(f"   ▶ {nome}  (canal {cfg['canal']}, limites {cfg['min']}-{cfg['max']}°)")
        input("     Enter para mover… ")
        meio = (float(cfg["min"]) + float(cfg["max"])) / 2
        for graus in (meio, float(cfg["min"]), meio, float(cfg["max"]), meio):
            arms.angulo(nome, graus)
            time.sleep(0.6)
    arms.relaxar()
    print("\n✅ Feito.\n")
    return 0


def encontrar_limites(junta: str) -> int:
    juntas = _juntas()
    if junta not in juntas:
        print(f"\n❌ Não existe a junta '{junta}'.")
        print(f"   Existem: {', '.join(sorted(juntas))}\n")
        return 1

    print(f"\n🔍 A varrer '{junta}' de 5 em 5 graus.")
    print("   Carrega Ctrl+C ASSIM QUE o braço tocar no corpo.")
    print("   O último ângulo mostrado é o limite — escreve-o no robot.yaml.\n")

    try:
        for graus in range(0, 181, 5):
            print(f"   {graus:3d}°", end="\r", flush=True)
            arms.angulo(junta, graus)
            time.sleep(0.4)
    except KeyboardInterrupt:
        print(f"\n\n   ⏹  Parou aos {graus}°. É este o limite.\n")
    finally:
        arms.relaxar()
    return 0


def main() -> int:
    print("\n🔍 A validar as poses e os gestos…")
    try:
        validar_todos()
        print(f"   ✅ {len(POSES)} poses e {len(GESTOS)} gestos, todos válidos.")
    except ValueError as erro:
        print(f"\n   ❌ {erro}\n")
        return 1

    if config.a_simular():
        print("   ⚠️  MODO SIMULAÇÃO — nada se vai mexer a sério.")
    else:
        print("   ⚠️  Confirma que o barramento de 6 V dos servos está ligado,")
        print("      e que os servos NÃO estão nos pinos de 5 V do Pi.")

    args = sys.argv[1:]
    if args and args[0] == "--juntas":
        return uma_junta_de_cada_vez()
    if args and args[0] == "--limites":
        if len(args) < 2:
            print("\n   Falta o nome da junta. Ex.: --limites ombro_dir\n")
            return 1
        return encontrar_limites(args[1])
    if args:
        nome = args[0]
        if nome in GESTOS:
            print(f"\n   ▶ gesto: {nome}\n")
            arms.gesto(nome)
        elif nome in POSES:
            print(f"\n   ▶ pose: {nome}\n")
            arms.pose(nome)
        else:
            print(f"\n   ❌ '{nome}' não é uma pose nem um gesto.")
            print(f"      Poses:  {', '.join(sorted(POSES))}")
            print(f"      Gestos: {', '.join(sorted(GESTOS))}\n")
            return 1
        time.sleep(1)
        arms.relaxar()
        return 0
    return todas_as_poses()


if __name__ == "__main__":
    sys.exit(main())
