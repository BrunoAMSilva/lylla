#!/usr/bin/env python3
"""TESTAR A VOZ E OS OUVIDOS.

    python scripts/test_voz.py                 diz umas frases
    python scripts/test_voz.py "olá mundo"     diz o que quiseres
    python scripts/test_voz.py --ouvir         grava e transcreve
    python scripts/test_voz.py --palavra       testa a palavra-chave
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402
from robot.voice import listen, speak, wakeword  # noqa: E402

FRASES = [
    "Olá! Eu sou o robô da Lara.",
    "Hoje aprendi a falar português de Portugal.",
    "A minha voz chama-se Joana, e foste tu que a escolheste.",
    "Um, dois, três, quatro, cinco.",
]


def testar_falar(texto: str | None) -> int:
    nome = config.nome_do_robo()
    print(f"\n🔊 {nome} — a testar a voz…")
    servidor = config.obter("voz.servidor")
    if servidor:
        print(f"   voz: {config.obter('voz.voz_mac', 'Joana')} · vinda de {servidor}")
        print(f"   já guardadas no Pi: {speak.frases_em_cache()} frases\n")
    else:
        print(f"   modelo local: {config.obter('voz.modelo_tts') or '(nenhum)'}\n")

    for frase in ([texto] if texto else FRASES):
        print(f'   "{frase}"')
        inicio = time.monotonic()
        speak.falar(frase)
        print(f"      ({time.monotonic() - inicio:.2f} s)\n")

    print("   Ouviste tudo em português de Portugal?")
    print("   Se não ouviste nada:")
    print("     · aplay -l                       aparece 'Array [reSpeaker XVF3800 ...]'?")
    print("     · a coluna está na ficha JST do reSpeaker? (não é no Pi — o Pi não tem saída de som)")
    print("     · /etc/asound.conf               tem 'defaults.pcm.card Array'?")
    print("     · o servidor de voz está a correr no Mac?\n       python scripts/servidor_voz.py\n")
    return 0


def testar_ouvir() -> int:
    print(f"\n🎤 A testar os ouvidos (Whisper '{config.obter('voz.modelo_stt')}')…\n")
    for i in range(3):
        print(f"   [{i + 1}/3] Diz alguma coisa (para quando fizeres silêncio)…")
        inicio = time.monotonic()
        texto = listen.ouvir()
        decorrido = time.monotonic() - inicio
        if texto:
            print(f'         👉 "{texto}"   ({decorrido:.1f} s)\n')
        else:
            print("         (não ouvi nada)\n")
    print("   Escreve as latências no caderno — é a medição da fase 7.\n")
    return 0


def testar_palavra() -> int:
    print("\n👂 A testar a palavra-chave…")
    print(f"   modelo: {config.obter('voz.palavra_chave')}")
    print("   Diz «Olá robô». 60 segundos. Ctrl+C para sair.\n")
    inicio = time.monotonic()
    contagem = 0
    try:
        while time.monotonic() - inicio < 60:
            if wakeword.esperar_pela_palavra(timeout=10):
                contagem += 1
                print(f"   ✅ ouvi! (#{contagem} aos {time.monotonic() - inicio:.0f}s)")
                speak.falar("Sim?")
    except KeyboardInterrupt:
        pass
    print(f"\n   Total: {contagem} ativações em 60 segundos.")
    print("   Se ativou sozinho, sobe o voz.limiar_palavra_chave no robot.yaml.\n")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--ouvir":
        return testar_ouvir()
    if args and args[0] == "--palavra":
        return testar_palavra()
    return testar_falar(args[0] if args else None)


if __name__ == "__main__":
    sys.exit(main())
