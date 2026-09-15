"""Renderiza o DSP do Teensy no computador. Requer Python 3 e clang++ ou g++.

    python3 previsao_respiracao.py
    python3 previsao_respiracao.py --input voz.wav --mode full
    python3 previsao_respiracao.py --test

O WAV de entrada deve ser PCM de 16 bits, mono, a 44100 Hz. O nível da gravação
é ajustado para simular um microfone com RMS de fala igual a --mic-rms.
Os filtros, a respiração e o pitch vêm de vader_dsp.h, sem uma cópia em Python.
"""

import argparse
import array
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parent


def compile_cpp(source, output, sanitize=False):
    compiler = shutil.which("clang++") or shutil.which("g++")
    if not compiler:
        raise RuntimeError("Instala clang++ ou g++ para renderizar o DSP.")
    command = [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror"]
    if sanitize:
        command.append("-fsanitize=address,undefined")
    subprocess.run(command + [str(source), "-o", str(output)], check=True)


def read_voice(path, mic_rms):
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 44100):
            raise ValueError("Exporta a voz como WAV PCM de 16 bits, mono, a 44100 Hz.")
        pcm = array.array("h", wav.readframes(wav.getnframes()))
    if sys.byteorder != "little":
        pcm.byteswap()
    if not pcm:
        raise ValueError("O WAV está vazio.")
    values = [sample / 32768.0 for sample in pcm]
    windows = sorted(math.sqrt(sum(x * x for x in values[i:i + 882]) / len(values[i:i + 882]))
                     for i in range(0, len(values), 882))
    active = [rms for rms in windows if rms > windows[-1] * 0.1]
    if not active:
        raise ValueError("A gravação de voz só contém silêncio.")
    reference = active[min(len(active) - 1, int(len(active) * 0.85))]
    gain = mic_rms / max(reference, 1e-6)
    peak = max(abs(x * gain) for x in values)
    if peak > 1:
        raise ValueError("O nível pedido satura a entrada. Reduz --mic-rms.")
    samples = array.array("f", (x * gain for x in values))
    samples.extend([0.0] * 22050)  # Escoar os atrasos sem cortar a última palavra.
    return samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Gravação de voz limpa")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=["breath", "voice", "full"])
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--compare", action="store_true", help="Original e resultado, com RMS igual")
    parser.add_argument("--mic-rms", type=float, default=0.020)
    parser.add_argument("--test", action="store_true", help="Verifica o DSP com sanitizadores")
    args = parser.parse_args()
    if not 0 < args.mic_rms <= 1:
        parser.error("--mic-rms deve estar entre 0 e 1.")
    if args.compare and not args.input:
        parser.error("--compare requer --input.")
    with tempfile.TemporaryDirectory(prefix="vader-") as folder:
        temporary = Path(folder)
        executable = temporary / "render"
        if args.test:
            compile_cpp(ROOT / "tools/test_dsp.cpp", executable, sanitize=True)
            subprocess.run([str(executable)], check=True)
            return
        compile_cpp(ROOT / "tools/render.cpp", executable)
        input_path = "-"
        if args.input:
            input_path = str(temporary / "input.f32")
            input_samples = read_voice(args.input, args.mic_rms)
            Path(input_path).write_bytes(input_samples.tobytes())
        raw = temporary / "output.f32"
        mode = args.mode or ("voice" if args.input else "breath")
        subprocess.run([str(executable), mode, "child" if args.child else "adult",
                        input_path, str(raw)], check=True)
        samples = array.array("f")
        samples.frombytes(raw.read_bytes())
        if args.compare:
            dry_power = sum(x * x for x in input_samples)
            wet_power = sum(x * x for x in samples)
            gain = math.sqrt(wet_power / max(dry_power, 1e-12))
            peak = max(max(abs(x) for x in samples),
                       gain * max(abs(x) for x in input_samples))
            level = min(1.0, 0.88 / max(peak, 1e-12))
            comparison = array.array("f", (x * gain * level for x in input_samples))
            comparison.extend([0.0] * 33075)
            comparison.extend(x * level for x in samples)
            samples = comparison
            print("Comparação: original, pausa, voz processada. RMS igual nos dois trechos.")
        pcm = array.array("h", (round(max(-1, min(1, x)) * 32767) for x in samples))
        if sys.byteorder != "little":
            pcm.byteswap()
        output = args.output or ROOT / ("voz-vader.wav" if args.input else "respiracao-vader.wav")
        with wave.open(str(output), "wb") as wav:
            wav.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
            wav.writeframes(pcm.tobytes())
        print(output.resolve())


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, wave.Error, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
