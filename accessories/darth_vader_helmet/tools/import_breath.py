"""Converte um ciclo de respiração gravado num cabeçalho para a flash do Teensy.

Entrada: WAV PCM de 16 bits, mono, a 22050 Hz, com 0,5 a 12 segundos.
Começa e termina o recorte numa pausa. Inclui a inspiração e a expiração.
"""

import argparse
import array
from pathlib import Path
import sys
import wave


def convert(source, output):
    with wave.open(str(source), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 22050):
            raise ValueError("Usa WAV PCM de 16 bits, mono, a 22050 Hz.")
        if not 11025 <= wav.getnframes() <= 264600:
            raise ValueError("O ciclo deve durar entre 0,5 e 12 segundos.")
        pcm = array.array("h", wav.readframes(wav.getnframes()))
    if sys.byteorder != "little":
        pcm.byteswap()
    mean = sum(pcm) / len(pcm)
    values = [sample - mean for sample in pcm]
    peak = max(abs(sample) for sample in values)
    if peak < 1:
        raise ValueError("O ficheiro só contém silêncio.")
    # Pico a -6,9 dBFS e transições de 10 ms nas pontas do ciclo.
    gain = 0.45 * 32767 / peak
    for i in range(len(values)):
        edge = min(1.0, i / 220.0, (len(values) - 1 - i) / 220.0)
        values[i] = round(values[i] * gain * edge * edge * (3 - 2 * edge))
    rows = [", ".join(str(sample) for sample in values[i:i + 16])
            for i in range(0, len(values), 16)]
    header = ("#pragma once\n#include <stdint.h>\n\n"
              "// Gerado por tools/import_breath.py. PCM mono a 22050 Hz.\n"
              f"constexpr uint32_t VADER_BREATH_SAMPLES = {len(values)};\n"
              "const int16_t VADER_BREATH_PCM[] PROGMEM = {\n  "
              + ",\n  ".join(rows) + "\n};\n")
    output.write_text(header, encoding="utf-8")
    print(f"{output}: {len(values) / 22050:.2f} s, {len(values) * 2} bytes de PCM na flash")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parents[1] / "breath_sample.h")
    args = parser.parse_args()
    convert(args.input, args.output)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, wave.Error) as error:
        sys.exit(str(error))
