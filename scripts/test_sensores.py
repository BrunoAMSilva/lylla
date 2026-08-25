#!/usr/bin/env python3
"""TESTAR OS SENSORES — distância e precipício, em tempo real.

    python scripts/test_sensores.py

Aproxima a mão do sensor da frente e vê o número descer. Levanta o robô e
vê o alarme de precipício disparar. Ctrl+C para sair.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402
from robot.hardware import sensors  # noqa: E402


def barra(cm: float, maximo: float = 100) -> str:
    n = int(min(cm, maximo) / maximo * 30)
    return "█" * n + "░" * (30 - n)


def main() -> int:
    minimo = float(config.obter("seguranca.distancia_min_cm", 25))
    print("\n" + "=" * 62)
    print("  SENSORES EM TEMPO REAL   (Ctrl+C para sair)")
    print("=" * 62)
    print(f"\n  distância mínima de segurança: {minimo:.0f} cm\n")

    try:
        while True:
            cm = sensors.distancia_cm()
            queda = sensors.ha_precipicio()

            if cm > 900:
                estado = "sem sensor"
            elif queda:
                estado = "⚠️  PRECIPÍCIO!"
            elif cm < minimo:
                estado = "🛑 PARA!"
            elif sensors.deve_abrandar():
                estado = "🟡 devagar"
            else:
                estado = "🟢 livre"

            print(f"  {barra(cm)}  {cm:6.1f} cm   {estado}          ",
                  end="\r", flush=True)
            time.sleep(0.15)
    except KeyboardInterrupt:
        print("\n\n  parado.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
