#!/usr/bin/env python3
"""O QUE JÁ ESTÁ PRONTO NO MAC, enquanto o Raspberry Pi não chega.

    python scripts/check_mac.py

Verifica só a parte que não precisa do robô: a voz, o cérebro, o código e o
ESP32. Cada linha diz o que falta e o comando exato para resolver.

O irmão deste script é o scripts/check_health.py, que corre no Pi e verifica o
hardware todo. Este só olha para o Mac.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

VERDE, AMARELO, VERMELHO, FIM, NEGRITO = "\033[32m", "\033[33m", "\033[31m", "\033[0m", "\033[1m"

_falhas: list[str] = []


def linha(ok: bool | None, texto: str, detalhe: str = "", comando: str = "") -> None:
    marca = {True: f"{VERDE}✅{FIM}", False: f"{VERMELHO}❌{FIM}", None: f"{AMARELO}⚠️ {FIM}"}[ok]
    print(f"  {marca} {texto:<38} {detalhe}")
    if ok is False and comando:
        print(f"      → {comando}")
        _falhas.append(texto)


def seccao(titulo: str) -> None:
    print(f"\n{NEGRITO}{titulo}{FIM}")


def _tem(modulo: str) -> bool:
    return importlib.util.find_spec(modulo) is not None


# ---------------------------------------------------------------------------

def verificar_codigo() -> None:
    seccao("O código")
    linha(sys.version_info >= (3, 9), "Python 3.9+",
          f"tens {sys.version_info.major}.{sys.version_info.minor}")
    for modulo, pacote in (("yaml", "PyYAML"), ("numpy", "numpy"),
                           ("cv2", "opencv-python"), ("pytest", "pytest")):
        linha(_tem(modulo), pacote, comando=f"pip install {pacote}")

    try:
        from robot.expressions import ANIMACOES, EXPRESSOES, validar_todas
        validar_todas()
        linha(True, "config/expressoes.yaml",
              f"{len(EXPRESSOES)} caras, {len(ANIMACOES)} animações")
    except Exception as erro:  # noqa: BLE001
        linha(False, "config/expressoes.yaml", str(erro)[:40])


def _vozes_pt() -> list[str]:
    if not shutil.which("say"):
        return []
    saida = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=False).stdout
    return [l.split("pt_PT")[0].strip() for l in saida.splitlines() if "pt_PT" in l]


def _servidor_de_voz_de_pe(porta: int = 8420) -> bool:
    from urllib.request import urlopen
    for caminho in ("/v1/saude", "/saude"):     # o cérebro, ou o antigo servidor de voz
        try:
            with urlopen(f"http://127.0.0.1:{porta}{caminho}", timeout=2):  # noqa: S310
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _cerebro_de_pe(porta: int = 8420) -> dict | None:
    import json
    from urllib.request import urlopen

    try:
        with urlopen(f"http://127.0.0.1:{porta}/v1/saude", timeout=2) as r:  # noqa: S310
            return json.load(r)
    except Exception:  # noqa: BLE001
        return None


def verificar_voz() -> None:
    seccao("A voz — a Joana vive aqui no Mac")

    escolhida = "Joana"  # a que a Lara escolheu no teste cego
    try:
        from robot import config
        escolhida = config.obter("voz.voz_mac", "Joana")
    except Exception:  # noqa: BLE001
        pass

    vozes = _vozes_pt()
    linha(
        escolhida in vozes,
        f"voz {escolhida} instalada",
        f"{len(vozes)} vozes pt-PT: " + ", ".join(vozes) if vozes else "nenhuma",
        comando="Definições → Acessibilidade → Conteúdo falado → Voz do sistema"
                " → Português (Portugal) → Gerir vozes",
    )

    de_pe = _servidor_de_voz_de_pe()
    linha(de_pe, "serviço de voz a correr",
          "http://localhost:8420" if de_pe else "",
          comando="python -m cerebro.servidor")

    linha(shutil.which("afplay") is not None, "afplay (para ouvir aqui)",
          comando="(vem com o macOS — se falta, algo está muito errado)")

    if vozes and not de_pe:
        print("\n      Ouve-a já, sem servidor nenhum:")
        print(f'        say -v {escolhida} "Olá Lara, eu sou a Lylla."')
        print("\n      E para comparar com as outras candidatas:")
        print("        python scripts/testar_vozes.py --cego")


def verificar_o_servico_do_cerebro() -> None:
    seccao("O cérebro — o serviço de IA deste Mac")

    saude = _cerebro_de_pe()
    linha(bool(saude), "serviço do cérebro a correr",
          f"http://localhost:8420  ({saude['nome']})" if saude else "",
          comando="python -m cerebro.servidor        # ou ./cerebro/instalar.sh --servico")
    if saude:
        for parte, etiqueta in (("ouvir", "ouvir "), ("pensar", "pensar"), ("falar", "falar ")):
            d = saude[parte]
            ok = d.get("ligado", True)
            linha(ok, f"{etiqueta} {d['motor']}", d.get("modelo") or d.get("voz", ""))
        print("\n      Experimenta já, sem microfone nenhum:")
        print('        python scripts/test_cerebro.py "segue-me!"')
    else:
        print("\n      Sem modelos instalados, para ver a API a andar:")
        print("        python -m cerebro.servidor --teste")
        print('        python scripts/test_cerebro.py "olá"')

    import importlib.util
    for pacote, porque in (("fastapi", "o serviço"),
                           ("websockets", "escutar em contínuo"),
                           ("parakeet_mlx", "ouvir (só em Apple Silicon)"),
                           ("piper", "falar")):
        linha(importlib.util.find_spec(pacote) is not None, f"{pacote} — {porque}",
              comando="./cerebro/instalar.sh")


def verificar_cerebro() -> None:
    seccao("O cérebro — o passo 4")
    tem_ollama = shutil.which("ollama") is not None
    linha(tem_ollama, "ollama instalado", comando="brew install ollama")
    if not tem_ollama:
        return

    try:
        saida = subprocess.run(["ollama", "list"], capture_output=True,
                               text=True, timeout=10).stdout
    except Exception:  # noqa: BLE001
        linha(False, "ollama a correr", comando="ollama serve &")
        return
    linha(True, "ollama a correr")

    from robot import config
    modelo = str(config.obter("llm.modelo", "gemma4:12b"))
    curto = modelo.split(":")[0]
    tem = modelo in saida or curto in saida
    linha(tem, f"modelo {modelo}",
          "descarregado" if tem else "em falta",
          comando=f"ollama pull {modelo}   # 7,6 GB, quer 16 GB de RAM")

    # Acessível na rede? É isto que falha quase sempre.
    host = config.obter("llm.host", "mac.local")
    porta = config.obter("llm.porta", 11434)
    try:
        import requests
        requests.get(f"http://{host}:{porta}/api/tags", timeout=3)
        linha(True, f"acessível em {host}:{porta}", "o robô vai conseguir chegar cá")
    except Exception:  # noqa: BLE001
        linha(
            None, f"acessível em {host}:{porta}", "só responde em localhost",
            comando="launchctl setenv OLLAMA_HOST 0.0.0.0:11434  # e reiniciar o ollama",
        )


def verificar_esp32() -> None:
    seccao("O ESP32 — o passo 5")
    portas: list[str] = []
    if _tem("serial"):
        try:
            from serial.tools import list_ports
            portas = [p.device for p in list_ports.comports()
                      if "usb" in p.device.lower() or "USB" in p.device]
        except Exception:  # noqa: BLE001
            pass
    else:
        linha(None, "pyserial", "não instalado (só é preciso no Pi)")

    linha(bool(portas), "ESP32 ligado por USB",
          ", ".join(portas) if portas else "nenhuma porta USB série",
          comando="liga o ESP32 e volta a correr (ou ignora — só é preciso na fase 3)")

    sketch = RAIZ / "firmware/bot_face_esp32/bot_face_esp32.ino"
    linha(sketch.exists(), "firmware da cara", str(sketch.relative_to(RAIZ)))


def verificar_o_robo_todo() -> None:
    seccao("O robô inteiro, em simulação")
    print("      ROBO_SIMULAR=1 python -m robot.main")
    print("      ROBO_SIMULAR=1 python scripts/test_eyes.py")
    print("      ROBO_SIMULAR=1 python scripts/test_companion.py")
    print("      ROBO_SIMULAR=1 python -m pytest -q")


def main() -> int:
    print(f"\n{NEGRITO}🤖 Enquanto o Pi não chega — o que já está pronto no Mac{FIM}")
    verificar_codigo()
    verificar_voz()
    verificar_o_servico_do_cerebro()
    verificar_cerebro()
    verificar_esp32()
    verificar_o_robo_todo()

    print()
    if _falhas:
        print(f"  {AMARELO}Faltam {len(_falhas)} coisas. Os comandos estão acima.{FIM}")
        print(f"  O guia completo está em ENQUANTO-ESPERAS.md\n")
        return 1
    print(f"  {VERDE}Está tudo pronto do lado do Mac. Falta o Pi chegar.{FIM}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
