#!/usr/bin/env python3
"""TESTAR OS MOTORES — cada um isoladamente, depois em conjunto.

    python scripts/test_motors.py

⚠️  PÕE O ROBÔ EM CIMA DE UM LIVRO, com as rodas no ar, da primeira vez.

O que vamos descobrir aqui (acontece SEMPRE): um dos motores anda ao
contrário, porque estão montados em espelho. Corrige-se de duas maneiras —
trocar os dois fios do motor, ou pôr um sinal negativo no código. Vale a
pena discutir qual é a melhor e porquê.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402
from robot.hardware import motors  # noqa: E402


def passo(descricao: str, acao, segundos: float = 1.2) -> None:
    print(f"\n▶ {descricao}")
    input("  (Enter para começar, Ctrl+C para sair) ")
    acao()
    time.sleep(segundos)
    motors.parar()
    print("  ⏹  parado")


def main() -> int:
    print("\n" + "=" * 58)
    print("  TESTE DOS MOTORES")
    print("=" * 58)
    if config.a_simular():
        print("\n  ⚠️  MODO SIMULAÇÃO — nada se vai mexer a sério.\n")
    else:
        print("\n  ⚠️  PÕE O ROBÔ COM AS RODAS NO AR (em cima de um livro).\n")

    try:
        # 1 · cada motor sozinho — é aqui que se descobre a inversão
        passo("MOTOR ESQUERDO para a frente", lambda: motors.mover(0.5, 0))
        print("     A roda ESQUERDA andou para a FRENTE? Se não, está invertida.")

        passo("MOTOR DIREITO para a frente", lambda: motors.mover(0, 0.5))
        print("     A roda DIREITA andou para a FRENTE? Se não, está invertida.")

        # 2 · os dois juntos
        passo("os DOIS para a frente", motors.frente)
        passo("os DOIS para trás", motors.tras)
        passo("virar à ESQUERDA", motors.esquerda)
        passo("virar à DIREITA", motors.direita)

        # 3 · velocidades
        print("\n▶ rampa de velocidade (25% → 70%)")
        input("  (Enter) ")
        for v in (0.25, 0.4, 0.55, 0.7):
            print(f"     {v * 100:.0f}%")
            motors.mover(v, v)
            time.sleep(0.7)
        motors.parar()

        # 4 · distâncias calibradas
        print("\n▶ agora com o robô NO CHÃO, para calibrar")
        input("  (põe o robô no chão e carrega Enter) ")
        print("     a andar 30 cm…")
        motors.andar_cm(30)
        time.sleep(0.5)
        print("     a rodar 90°…")
        motors.virar_graus(90)

        print("\n" + "=" * 58)
        print("  CALIBRAÇÃO — ajusta o config/robot.yaml:")
        print("=" * 58)
        print("   andou menos de 30 cm?  → baixa  motores.cm_por_segundo")
        print("   andou mais de 30 cm?   → sobe   motores.cm_por_segundo")
        print("   rodou menos de 90°?    → sobe   motores.tempo_90_graus")
        print("   rodou mais de 90°?     → baixa  motores.tempo_90_graus")
        print("   foge para a direita?   → sobe   motores.compensacao_esq")
        print("   foge para a esquerda?  → sobe   motores.compensacao_dir")
        print()

    except KeyboardInterrupt:
        pass
    finally:
        motors.parar()
        print("\n⏹  motores parados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
