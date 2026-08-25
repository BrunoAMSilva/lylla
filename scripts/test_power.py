#!/usr/bin/env python3
"""TESTAR E CALIBRAR A LEITURA DA BATERIA.

    python scripts/test_power.py             leitura contínua
    python scripts/test_power.py --calibrar  ajusta o divisor com o multímetro

CALIBRAÇÃO (fase 7) — é isto que faz o número ficar certo:

  1. Mede a tensão real da bateria com o multímetro.
  2. Corre `--calibrar` e escreve o valor que mediste.
  3. O script calcula o `energia.divisor` correto e diz-te qual é.
  4. Escreve esse número no config/robot.yaml.

Porque é preciso: as resistências do divisor têm tolerância de 1-5%, por isso
o valor teórico (100k + 22k → 5,545) nunca é exatamente o real.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402
from robot.hardware import power  # noqa: E402


def barra(pct: int) -> str:
    n = int(pct / 100 * 30)
    return "█" * n + "░" * (30 - n)


def continuo() -> int:
    print("\n" + "=" * 62)
    print("  BATERIA EM TEMPO REAL   (Ctrl+C para sair)")
    print("=" * 62)
    print(f"\n  divisor atual: {config.obter('energia.divisor', 5.545)}")
    print(f"  aviso a {config.obter('energia.aviso_pct', 20)}% · "
          f"crítico a {config.obter('energia.critico_pct', 5)}%\n")

    try:
        while True:
            v = power.tensao()
            pct = power.percentagem()
            if v is None:
                print("  ❌ sem leitura — o ADS1115 responde em i2cdetect -y 1 (0x48)?")
                time.sleep(2)
                continue

            if power.critico():
                estado = "🛑 CRÍTICO"
            elif power.tem_fome():
                estado = "🟡 com fome"
            else:
                estado = "🟢 ok"

            print(f"  {barra(pct or 0)}  {v:5.2f} V   {pct or 0:3d}%   {estado}     ",
                  end="\r", flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\n  parado.\n")
    return 0


def calibrar() -> int:
    print("\n" + "=" * 62)
    print("  CALIBRAÇÃO DA LEITURA DE BATERIA")
    print("=" * 62)

    if config.a_simular():
        print("\n  ⚠️  Modo simulação — não há ADC para calibrar.\n")
        return 1

    print("\n  1. Mede a tensão da bateria com o multímetro.")
    try:
        real = float(input("  2. Escreve aqui o valor em volts (ex.: 13.24): ").strip())
    except (ValueError, EOFError, KeyboardInterrupt):
        print("\n  Valor inválido.\n")
        return 1

    divisor_atual = float(config.obter("energia.divisor", 5.545))
    lido = power.tensao()
    if lido is None or lido <= 0:
        print("\n  ❌ Não consigo ler o ADS1115. Verifica o I2C (0x48) e o divisor.\n")
        return 1

    novo = divisor_atual * (real / lido)

    print(f"\n     multímetro diz:  {real:.2f} V")
    print(f"     o robô lê:       {lido:.2f} V")
    print(f"     erro:            {abs(real - lido):.2f} V")
    print(f"\n  ✅ Escreve isto no config/robot.yaml:\n")
    print(f"     energia:")
    print(f"       divisor: {novo:.3f}\n")
    print(f"     (era {divisor_atual:.3f})\n")
    return 0


def main() -> int:
    if not power.disponivel():
        print("\n  ❌ Sem leitura de bateria. i2cdetect -y 1 mostra 0x48?\n")
        return 1
    if sys.argv[1:] and sys.argv[1] == "--calibrar":
        return calibrar()
    return continuo()


if __name__ == "__main__":
    sys.exit(main())
