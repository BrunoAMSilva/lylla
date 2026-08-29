#!/usr/bin/env python3
"""VIGIAR A ENERGIA — apanhar a quebra de tensão que desliga o Pi.

    python scripts/vigiar_energia.py                     só observa
    python scripts/vigiar_energia.py --forcar 60         força o CPU 60 s
    python scripts/vigiar_energia.py --forcar 60 --nucleos 4
    python scripts/vigiar_energia.py --ficheiro /home/bruno/energia.csv

⚠️ PORQUE É QUE ISTO EXISTE, EM VEZ DE UM `vcgencmd` À MÃO

    Um `vcgencmd get_throttled` depois do Pi voltar a arrancar diz sempre
    `0x0` — e não quer dizer nada. Os bits de subtensão vivem no SoC e
    perdem-se quando a corrente falha: a avaria apaga a sua própria prova.
    E sem journal persistente também não fica nada no log.

    Por isso este script escreve cada amostra em disco com `fsync` — a linha
    chega ao cartão ANTES de ser preciso. Se o Pi se desligar, a última linha
    do ficheiro é a fotografia do instante anterior à queda.

COMO SE USA A SÉRIO
    Numa sessão SSH, com a fonte que se quer testar:

        python scripts/vigiar_energia.py --forcar 90

    Se o Pi aguentar, olha para o `EXT5V mínimo` no resumo. Abaixo de ~4,8 V
    a fonte está a ceder mesmo que nada se desligue — e vai ceder outra vez
    quando os motores entrarem (fase 6). Comparar o mínimo entre duas fontes
    vale mais do que "com esta não se desligou".
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import re
import subprocess
import sys
import time
from pathlib import Path

VALOR = re.compile(r"(\w+)\s+(?:current|volt)\((\d+)\)=([\d.]+)([AV])")


def vcgencmd(*args) -> str:
    try:
        r = subprocess.run(["vcgencmd", *args], capture_output=True,
                           text=True, timeout=5)
        return r.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def amostra() -> dict:
    """Uma leitura completa: tensões, correntes, bits de estrangulamento, temperatura."""
    dados: dict[str, float | int | None] = {}
    for nome, _, valor, unidade in VALOR.findall(vcgencmd("pmic_read_adc")):
        dados[nome] = float(valor)

    bruto = vcgencmd("get_throttled")
    bits = int(bruto.split("=")[1], 16) if "=" in bruto else None
    dados["throttled"] = bits

    temp = vcgencmd("measure_temp")
    dados["temp"] = float(temp.split("=")[1].split("'")[0]) if "=" in temp else None
    return dados


def explicar(bits: int | None) -> str:
    if not bits:
        return ""
    agora = {0: "SUBTENSÃO", 1: "freq limitada", 2: "estrangulado", 3: "temp limitada"}
    houve = {16: "houve subtensão", 17: "houve limite de freq",
             18: "houve estrangulamento", 19: "houve limite térmico"}
    partes = [t for b, t in agora.items() if bits & (1 << b)]
    partes += [t for b, t in houve.items() if bits & (1 << b)]
    return " · ".join(partes)


def queimar(ate: float) -> None:
    """Carga de CPU pura — sem câmara, sem OpenCV, sem nada do robô pelo meio."""
    x = 0.0
    while time.time() < ate:
        for _ in range(200000):
            x += 1.0000001
        x *= 0.5


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--intervalo", type=float, default=0.5)
    p.add_argument("--forcar", type=float, default=0.0,
                   help="segundos de carga de CPU (0 = só observar)")
    p.add_argument("--nucleos", type=int, default=multiprocessing.cpu_count())
    p.add_argument("--ficheiro", default="energia.csv")
    args = p.parse_args()

    if not vcgencmd("measure_temp"):
        print("\n  ❌ Não encontrei o `vcgencmd`. Isto só corre no Raspberry Pi.\n")
        return 1

    caminho = Path(args.ficheiro).expanduser()
    print(f"\n⚡ A vigiar. Cada linha vai para {caminho} com fsync —")
    print("   se o Pi se desligar, a última linha é o instante antes da queda.")

    filhos: list[multiprocessing.Process] = []
    if args.forcar > 0:
        ate = time.time() + args.forcar
        for _ in range(args.nucleos):
            f = multiprocessing.Process(target=queimar, args=(ate,), daemon=True)
            f.start()
            filhos.append(f)
        print(f"   🔥 {args.nucleos} núcleos em carga durante {args.forcar:.0f} s.")
    print("   Ctrl+C para parar.\n")

    minimo = float("inf")
    avisado = False
    ficheiro = caminho.open("a", encoding="utf-8")
    if ficheiro.tell() == 0:
        ficheiro.write("t,ext5v,vdd_core_v,vdd_core_a,throttled,temp\n")

    try:
        while True:
            d = amostra()
            ext5v = d.get("EXT5V_V")
            agora = time.strftime("%H:%M:%S")
            ficheiro.write(f"{agora},{ext5v},{d.get('VDD_CORE_V')},"
                           f"{d.get('VDD_CORE_A')},{d.get('throttled')},{d.get('temp')}\n")
            ficheiro.flush()
            os.fsync(ficheiro.fileno())   # ⚠️ é isto que faz a linha sobreviver

            if ext5v is not None:
                minimo = min(minimo, ext5v)
            nota = explicar(d.get("throttled"))
            print(f"  {agora}  EXT5V {ext5v:.3f} V  (mín {minimo:.3f})  "
                  f"CPU {d.get('VDD_CORE_A') or 0:.2f} A  {d.get('temp')}°C  {nota}",
                  flush=True)
            if nota and not avisado:
                avisado = True
                print("\n  ⚠️  A fonte está a ceder. É esta a causa — não é o código.\n",
                      flush=True)

            if filhos and all(not f.is_alive() for f in filhos):
                break
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        pass
    finally:
        for f in filhos:
            f.terminate()
        ficheiro.close()

    print(f"\n  EXT5V mínimo: {minimo:.3f} V")
    if minimo < 4.8:
        print("  ❌ Abaixo de 4,8 V — a fonte não chega, mesmo que nada se tenha desligado.")
    elif minimo < 4.95:
        print("  ⚠️  Aguenta, mas com pouca folga. Vai faltar quando os motores entrarem.")
    else:
        print("  ✅ Firme sob carga.")
    print(f"  Histórico em {caminho}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
