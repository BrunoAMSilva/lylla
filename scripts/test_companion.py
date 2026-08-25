#!/usr/bin/env python3
"""O ROBÔ NA SECRETÁRIA — ver se está tudo bem antes de o pôr lá.

    python scripts/test_companion.py             corre tudo
    python scripts/test_companion.py --custo     só quanto custa olhar
    python scripts/test_companion.py --olhar     só o seguir com os olhos
    python scripts/test_companion.py --sozinho   só as atividades

⚠️ ANTES DE O PÔR EM CIMA DA SECRETÁRIA, corre primeiro
   `python scripts/test_sensors.py` e confirma que os três sensores de
   precipício respondem. Uma queda de 75 cm parte o robô.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402
from robot.brain import comandos_diretos, companion  # noqa: E402
from robot.hardware import eyes, motors, sensors  # noqa: E402
from robot.perception import attention  # noqa: E402


def _titulo(texto: str) -> None:
    print(f"\n\033[1m{texto}\033[0m")
    print("─" * len(texto))


def seguranca() -> bool:
    _titulo("1 · Segurança — pode ir para a mesa?")
    motors.modo("secretaria")
    chao = float(config.obter("motores.velocidade_max", 0.6))
    mesa = float(config.obter("secretaria.velocidade_max", 0.25))
    print(f"   velocidade no chão .......... {chao}")
    print(f"   velocidade na secretária .... {mesa}   ({mesa / chao:.0%} da do chão)")
    print(f"   pedido de 100% dá ........... {motors._limitar(1.0):.2f}")

    ok = True
    if config.a_simular():
        print("   sensores de precipício ...... (simulação)")
    else:
        try:
            estado = sensors.estado()
            print(f"   sensores de precipício ...... {estado}")
            if not config.obter("seguranca.verificar_precipicio", True):
                print("   \033[31m❌ verificar_precipicio está DESLIGADO no robot.yaml\033[0m")
                ok = False
        except Exception as erro:  # noqa: BLE001
            print(f"   \033[31m❌ não consegui ler os sensores: {erro}\033[0m")
            ok = False
    print(f"   {'✅' if ok else '❌'} {'pode ir para a mesa' if ok else 'NÃO pôr na mesa ainda'}")
    return ok


def custo() -> None:
    _titulo("2 · Quanto custa olhar")
    fps = float(config.obter("secretaria.fps_deteccao", 10))
    largura, altura = config.obter("secretaria.resolucao_deteccao", [320, 240])
    print(f"   a detetar a {largura}×{altura}, {fps:.0f} vezes por segundo")
    print("   a medir 40 imagens…", end="", flush=True)

    t0 = time.perf_counter()
    for _ in range(40):
        attention.observar()
    total = time.perf_counter() - t0
    print(f" {total:.1f}s")

    c = attention.custo()
    if not c["amostras"]:
        print("\n   (simulação — no robô isto mede a sério)\n")
        return

    print(f"\n   detetar (YuNet) ............. {c['deteccao_ms']:.1f} ms")
    print(f"   reconhecer (SFace) .......... {c['reconhecimento_ms']:.1f} ms")
    print(f"   fatia de UM núcleo .......... {c['fracao_de_um_nucleo']:.1%}")
    print(f"   ≈ consumo ................... {c['watts_estimados']:.2f} W")
    print(f"\n   O Pi 5 tem 4 núcleos. Isto usa {c['fracao_de_um_nucleo'] / 4:.1%} do CPU total.")
    print("   Um acelerador Hailo gasta ~2,5 W só por estar ligado (D8b).")
    if c["watts_estimados"] < 2.5:
        print(f"   \033[32m✅ olhar custa-nos menos do que custaria a placa parada\033[0m")
    else:
        print("   \033[33m⚠️  acima dos 2,5 W — vale a pena baixar os fps ou a resolução\033[0m")


def olhar() -> None:
    _titulo("3 · Seguir com os olhos")
    print("   Põe-te à frente da câmara e anda de um lado para o outro.")
    print("   Ctrl+C para passar à frente.\n")
    try:
        fim = time.monotonic() + 15
        while time.monotonic() < fim:
            obs = companion.tick()
            if obs.presente:
                barra = int((obs.x + 1) * 15)
                quem = obs.nome or "alguém"
                print(f"\r   [{'·' * barra}O{'·' * (30 - barra)}]  {quem:12} "
                      f"área {obs.area:.1%}  ", end="", flush=True)
            time.sleep(0.05)
        print()
    except KeyboardInterrupt:
        print("\n   (saltado)")


def sozinho() -> None:
    _titulo("4 · O que ele faz quando ninguém lhe liga")
    for nome, funcao in companion.ATIVIDADES:
        print(f"   ▶ {nome}")
        funcao()
        time.sleep(0.4)
    eyes.expressao("neutro", olhar=(0.0, 0.0))
    print(f"\n   {len(companion.ATIVIDADES)} atividades, uma de "
          f"{config.obter('secretaria.intervalo_atividades_s', 45)} em "
          f"{config.obter('secretaria.intervalo_atividades_s', 45)} segundos.")


def privacidade() -> None:
    _titulo("5 · O interruptor da câmara")
    print("   Estas frases NÃO passam pelo LLM — são comparações de texto.")
    print("   Têm de funcionar 100% das vezes, não 90%.\n")
    for frase in ("para de olhar", "não olhes para mim", "modo privado", "podes olhar"):
        resposta = comandos_diretos.tentar(frase)
        marca = "✅" if resposta else "❌"
        print(f"   {marca} «{frase}» → {resposta}")
    companion.voltar_a_seguir()
    print(f"\n   frases reservadas ao todo: {len(comandos_diretos.frases_reservadas())}")


def main() -> int:
    args = sys.argv[1:]
    print(f"\n🤖 {config.nome_do_robo()} — modo secretária")
    if config.a_simular():
        print("   ⚠️  MODO SIMULAÇÃO — sem hardware.")

    if "--custo" in args:
        custo()
    elif "--olhar" in args:
        olhar()
    elif "--sozinho" in args:
        sozinho()
    else:
        pronto = seguranca()
        custo()
        sozinho()
        privacidade()
        if not pronto:
            print("\n\033[31m❌ Resolve a segurança antes de o pôr na secretária.\033[0m\n")
            return 1
        print("\n   ✅ Tudo pronto.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
