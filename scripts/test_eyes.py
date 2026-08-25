#!/usr/bin/env python3
"""TESTAR A CARA.

    python scripts/test_eyes.py               passa por todas as caras
    python scripts/test_eyes.py coracao       mostra só uma
    python scripts/test_eyes.py --animacoes
    python scripts/test_eyes.py --ping        o ESP32 responde?

A cara é desenhada pelo ESP32, não pelo Pi. Se nada aparecer no painel,
a primeira pergunta é sempre: o ESP32 está ligado por USB?
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402
from robot.expressions import (  # noqa: E402
    ANIMACOES, EXPRESSOES, cor_base, parametros, validar_todas,
)
from robot.hardware import eyes  # noqa: E402


def _resumo(nome: str) -> str:
    p = parametros(nome)
    if p["forma"] != "olhos":
        return f"forma especial: {p['forma']}  ·  #{p['cor']}"
    return (f"rx={p['rx']} ry={p['ry']} abertura={p['abertura_esq']}/{p['abertura_dir']} "
            f"arco={p['arco']} rot={p['rotacao']}  ·  #{p['cor']}")


def main() -> int:
    print("\n🔍 A validar o config/expressoes.yaml…")
    try:
        validar_todas()
        print(f"   ✅ {len(EXPRESSOES)} caras e {len(ANIMACOES)} animações, todas válidas.")
        print(f"   cor base: #{cor_base()}")
    except (ValueError, FileNotFoundError) as erro:
        print(f"\n   ❌ {erro}\n")
        return 1

    args = sys.argv[1:]

    if args and args[0] == "--ping":
        ok = eyes.disponivel()
        print(f"\n   {'✅ o ESP32 respondeu' if ok else '❌ sem resposta do ESP32'}")
        if not ok and not config.a_simular():
            print(f"      porta configurada: {config.obter('cara.porta')}")
            print("      ls /dev/ttyUSB* /dev/ttyACM*\n")
        return 0 if ok else 1

    if args and args[0] == "--animacoes":
        for nome in ANIMACOES:
            print(f"\n   ▶ {nome}")
            eyes.animar(nome)
            time.sleep(0.5)
        eyes.expressao("neutro")
        return 0

    if args:
        nome = args[0]
        if nome not in EXPRESSOES:
            print(f"\n   ❌ Não existe a cara '{nome}'.")
            print(f"      Existem: {', '.join(sorted(EXPRESSOES))}\n")
            return 1
        print(f"\n   ▶ {nome}   {_resumo(nome)}\n")
        eyes.expressao(nome)
        time.sleep(4)
        return 0

    print()
    for nome in sorted(EXPRESSOES):
        print(f"   ▶ {nome:16} {_resumo(nome)}")
        eyes.expressao(nome)
        time.sleep(1.6)

    print("\n   ▶ e agora as animações…")
    for nome in ANIMACOES:
        print(f"      {nome}")
        eyes.animar(nome)
        time.sleep(0.4)

    eyes.expressao("neutro")
    print("\n   ✅ Feito.")
    if config.a_simular():
        print("      (modo simulação — no robô isto aparece no painel)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
