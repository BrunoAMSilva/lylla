#!/usr/bin/env python3
"""TESTAR OS LEDs AZUIS DA SONDA.

    python scripts/test_glow.py            passa por todos os grupos e animações
    python scripts/test_glow.py base       acende só um grupo
    python scripts/test_glow.py --respirar

⚠️ Cada grupo de LEDs precisa da SUA resistência em série. Para LEDs azuis
   (~3,2 V) alimentados a 5 V com ~15 mA: 120 Ω. Sem ela o LED dura segundos.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402
from robot.hardware import glow  # noqa: E402


def main() -> int:
    canais = config.obter("brilho.canais", {}) or {}
    if not canais:
        print("\n  ❌ Não há grupos de luz em config/robot.yaml (secção brilho.canais)\n")
        return 1

    print(f"\n💡 {len(canais)} grupo(s): {', '.join(canais)}\n")
    args = sys.argv[1:]

    if args and args[0] == "--respirar":
        print("   a respirar… Ctrl+C para parar")
        glow.respirar("base")
        try:
            time.sleep(30)
        except KeyboardInterrupt:
            pass
        glow.apagar()
        return 0

    if args:
        if args[0] not in canais:
            print(f"   ❌ '{args[0]}' não existe. Existem: {', '.join(canais)}\n")
            return 1
        for v in (0.25, 0.5, 0.75, 1.0, 0.0):
            print(f"   {args[0]} → {v * 100:.0f}%")
            glow.brilho(args[0], v)
            time.sleep(0.8)
        return 0

    for grupo in canais:
        print(f"   ▶ {grupo}: rampa 0 → 100%")
        for i in range(0, 21):
            glow.brilho(grupo, i / 20)
            time.sleep(0.06)
        glow.brilho(grupo, 0.0)
        time.sleep(0.3)

    print("\n   ▶ respirar (5 s)")
    glow.respirar("base")
    time.sleep(5)
    print("   ▶ pulsar (3 s)")
    glow.pulsar("base")
    time.sleep(3)
    glow.apagar()
    print("\n   ✅ Feito.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
