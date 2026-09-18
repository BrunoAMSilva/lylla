"""Porque é que a voz sai lenta e grave? Descobre a taxa a que a placa toca.

    python3 scripts/testar_taxa_voz.py            (no Pi, com o mini ligado)

Faz duas coisas:
  1. Toca uma frase e lê do kernel a taxa a que a placa está MESMO a tocar
     (/proc/asound/.../hw_params) — é esse o número para o voz.taxa_saida.
  2. Toca a mesma frase reamostrada para 16000, 22050, 24000 e 48000 Hz.
     A que soar normal (nem lenta nem esganiçada) é a certa.
"""

from __future__ import annotations

import glob
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robot import config  # noqa: E402
from robot.voice import speak  # noqa: E402

FRASE = "Hello Lara! One, two, three. Do I sound normal now?"


def taxa_real(wav: str) -> None:
    print("\n1) O que a placa está mesmo a fazer:")
    leitor = subprocess.Popen(["aplay", wav], stderr=subprocess.PIPE, text=True)
    time.sleep(0.6)
    for f in glob.glob("/proc/asound/card*/pcm*p/sub*/hw_params"):
        conteudo = Path(f).read_text().strip()
        if conteudo and conteudo != "closed":
            print(f"   {f}\n   " + conteudo.replace("\n", "\n   "))
    leitor.wait()
    erro = (leitor.stderr.read() or "").strip()
    if erro:
        print(f"   aplay disse: {erro}")


def main() -> None:
    wav = speak._pedir_ao_mac(FRASE)
    if wav is None:
        print("❌ O mini não deu a frase. Liga o cérebro e tenta outra vez.")
        return
    taxa_real(str(wav))

    print("\n2) A mesma frase a várias taxas — qual soa normal?")
    original = config.obter
    for taxa in (16000, 22050, 24000, 48000):
        config.obter = lambda c, o=None, t=taxa: t if c == "voz.taxa_saida" else original(c, o)
        print(f"   ▶ {taxa} Hz")
        speak._reproduzir_wav(wav)
        time.sleep(0.5)
    config.obter = original
    print("\nPõe o número que soou normal em voz.taxa_saida (config/robot.yaml).")


if __name__ == "__main__":
    main()
