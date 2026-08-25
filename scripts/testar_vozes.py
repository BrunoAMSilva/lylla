#!/usr/bin/env python3
"""OUVIR AS VOZES CANDIDATAS — e deixar a Lara escolher a da Lylla.

    pip install "piper-tts" phoonnx tugaphone
    python scripts/testar_vozes.py            # gera os ficheiros
    python scripts/testar_vozes.py --ouvir    # gera e toca, um a um
    python scripts/testar_vozes.py --cego     # toca por ordem aleatória, sem dizer qual é
    python scripts/testar_vozes.py --so-ouvir --cego   # só ouve o que já lá está

Porquê: a voz `tugão` do Piper foi treinada com 1,5 horas de áudio gravado pelo
browser (comprimido) e afinada a partir de uma voz INGLESA. Dá o que dá. Desde
o fim de 2025 há mais vozes de português europeu — e um fonemizador feito de
propósito para português, o `tugaphone`, que é a parte que decide QUE SONS sair
para cada palavra escrita. É por isso que às vezes se ouve uma palavra diferente
da que está escrita: não é a voz, é o fonemizador.

Os ficheiros ficam em data/vozes/. Ouçam os dois e escolham. Quem manda são os
ouvidos da Lara, não a tabela de especificações.

As vozes GRANDES (2 GB, só correm no Mac, clonam a tua voz) estão no irmão
deste script, o testar_vozes_neuronais.py. Escrevem na mesma pasta, por isso
o --so-ouvir daqui toca tudo o que houver — pequenas e grandes, à mistura e
sem dizer qual é qual. É assim que a comparação é honesta.
"""

from __future__ import annotations

import argparse
import platform
import random
import shutil
import subprocess
import sys
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "data" / "vozes"
MODELOS = RAIZ / "models"

# Frase de teste: leva números e nomes próprios de propósito. É aí que as vozes
# fracas se desmancham — a `tugão` não traz normalização de texto nenhuma.
FRASE = (
    "Olá Lara! Eu sou a Lylla. "
    "Tenho 2 rodas, 4 servos nos braços e 32 luzes em cada olho. "
    "Queres dar uma volta pela sala?"
)

VOZES_PHOONNX = [
    ("dii-tugaphone", "OpenVoiceOS/phoonnx_pt-PT_dii_tugaphone", "feminina · fonemizador português"),
    ("miro-tugaphone", "OpenVoiceOS/phoonnx_pt-PT_miro_tugaphone", "masculina · fonemizador português"),
    ("dii-espeak", "OpenVoiceOS/pipertts_pt-PT_dii", "feminina · espeak (como a tugão)"),
]

VOZES_MAC = [
    ("mac-joana", "Joana", "voz do macOS"),
    ("mac-catarina", "Catarina", "voz do macOS"),
    ("mac-joaquim", "Joaquim", "voz do macOS"),
]


def cabecalho(texto: str) -> None:
    print(f"\n  {texto}")


def falhou(nome: str, erro: object, ajuda: str = "") -> None:
    print(f"     ❌ {nome}: {erro}")
    if ajuda:
        print(f"        {ajuda}")


# ---------------------------------------------------------------- Piper (tugão)


def gerar_piper(ficheiros: list[tuple[str, Path, str]]) -> None:
    modelo = MODELOS / "pt_PT-tugão-medium.onnx"
    if not modelo.exists():
        falhou("tugão", "falta o modelo", "corre primeiro: python scripts/download_models.py")
        return
    try:
        from piper import PiperVoice, SynthesisConfig
    except ImportError as erro:
        falhou("tugão", erro, "pip install piper-tts")
        return

    voz = PiperVoice.load(str(modelo))
    variantes = [
        ("tugao", None, "a de agora, tal e qual"),
        # Mais devagar e com menos ruído: é o truque clássico para dar
        # inteligibilidade a um modelo VITS treinado com pouco áudio.
        ("tugao-lento", SynthesisConfig(length_scale=1.25, noise_scale=0.5, noise_w_scale=0.6),
         "a mesma, mas mais devagar e menos trémula"),
    ]
    for nome, cfg, descricao in variantes:
        destino = DESTINO / f"{nome}.wav"
        try:
            with wave.open(str(destino), "wb") as wav:
                voz.synthesize_wav(FRASE, wav, cfg)
            print(f"     ✅ {nome}")
            ficheiros.append((nome, destino, descricao))
        except Exception as erro:  # noqa: BLE001
            falhou(nome, erro)


# ------------------------------------------------------------------- phoonnx


def gerar_phoonnx(ficheiros: list[tuple[str, Path, str]]) -> None:
    try:
        from phoonnx.config import SynthesisConfig
        from phoonnx.model_manager import TTSModelManager
    except ImportError as erro:
        falhou("vozes novas", erro, "pip install phoonnx tugaphone")
        return

    gestor = TTSModelManager()
    gestor.merge_default_voices()
    catalogo = {v.voice_id: v for v in gestor.all_voices}

    for nome, voice_id, descricao in VOZES_PHOONNX:
        info = catalogo.get(voice_id)
        if info is None:
            falhou(nome, f"não está no catálogo ({voice_id})", "phoonnx-voices update-cache")
            continue
        destino = DESTINO / f"{nome}.wav"
        try:
            # A primeira vez descarrega ~60 MB para ~/.cache/phoonnx/voices/
            voz = info.load()
            with wave.open(str(destino), "wb") as wav:
                voz.synthesize_wav(FRASE, wav, SynthesisConfig())
            print(f"     ✅ {nome}")
            ficheiros.append((nome, destino, descricao))
        except Exception as erro:  # noqa: BLE001
            falhou(nome, erro)


# --------------------------------------------------------------- vozes do Mac


def gerar_mac(ficheiros: list[tuple[str, Path, str]]) -> None:
    if platform.system() != "Darwin" or not shutil.which("say"):
        print("     ⏭️  (só no Mac)")
        return

    instaladas = subprocess.run(
        ["say", "-v", "?"], capture_output=True, text=True, check=False
    ).stdout

    for nome, voz, descricao in VOZES_MAC:
        if voz not in instaladas:
            falhou(nome, "não está instalada",
                   "Definições → Acessibilidade → Conteúdo falado → Voz do sistema → Gerir vozes")
            continue
        destino = DESTINO / f"{nome}.wav"
        try:
            subprocess.run(
                ["say", "-v", voz, "-o", str(destino),
                 "--file-format=WAVE", "--data-format=LEI16@22050", FRASE],
                check=True, capture_output=True,
            )
            print(f"     ✅ {nome}")
            ficheiros.append((nome, destino, descricao))
        except subprocess.CalledProcessError as erro:  # noqa: PERF203
            falhou(nome, erro.stderr.decode(errors="replace").strip() or erro)


def apanhar_do_disco() -> list[tuple[str, Path, str]]:
    """Tudo o que já foi gerado, venha de que script vier."""
    conhecidas = {n: d for n, _, d in VOZES_PHOONNX}
    conhecidas.update({n: d for n, _, d in VOZES_MAC})
    conhecidas.update({
        "tugao": "a antiga do Piper",
        "tugao-lento": "a antiga, mais devagar",
        "xtts-ptpt": "XTTS afinado pt-PT · clonada",
        "xtts-base": "XTTS base · o controlo brasileiro",
        "qwen3": "Qwen3-TTS · clonada",
        "chatterbox": "Chatterbox v3 · clonada",
    })
    return [
        (f.stem, f, conhecidas.get(f.stem, "?"))
        for f in sorted(DESTINO.glob("*.wav"))
    ]


# ------------------------------------------------------------------- ouvir


def tocar(caminho: Path) -> None:
    for comando in (["afplay"], ["aplay", "-q"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
        if shutil.which(comando[0]):
            subprocess.run([*comando, str(caminho)], check=False)
            return
    print(f"     (não há leitor de áudio — abre à mão: {caminho})")


def ouvir(ficheiros: list[tuple[str, Path, str]], cego: bool) -> None:
    ordem = list(ficheiros)
    if cego:
        random.shuffle(ordem)
        print("\n🙈 Teste cego. Ouve todas e diz o número da que gostas mais.")
        print("   (a lista sai no fim)\n")

    for i, (nome, caminho, descricao) in enumerate(ordem, start=1):
        etiqueta = f"voz número {i}" if cego else f"{nome} — {descricao}"
        print(f"  ▶  {etiqueta}")
        tocar(caminho)
        if i < len(ordem):
            input("     [Enter para a próxima] ")

    if cego:
        print("\n  E eram:")
        for i, (nome, _, descricao) in enumerate(ordem, start=1):
            print(f"     {i}. {nome} — {descricao}")


# -------------------------------------------------------------------- main


def main() -> int:
    global FRASE  # noqa: PLW0603

    parser = argparse.ArgumentParser(description="Gera a mesma frase em várias vozes de português europeu.")
    parser.add_argument("--ouvir", action="store_true", help="tocar as vozes a seguir a gerar")
    parser.add_argument("--cego", action="store_true", help="tocar por ordem aleatória, sem dizer qual é qual")
    parser.add_argument("--frase", default=FRASE, help="frase alternativa")
    parser.add_argument("--so-ouvir", action="store_true", dest="so_ouvir",
                        help="não gerar nada; ouvir o que já está em data/vozes/")
    args = parser.parse_args()
    FRASE = args.frase

    DESTINO.mkdir(parents=True, exist_ok=True)

    if args.so_ouvir:
        ficheiros = apanhar_do_disco()
        if not ficheiros:
            print(f"\n   Não há nada em {DESTINO}. Gera primeiro.\n")
            return 1
        print(f"\n🎧 {len(ficheiros)} vozes em {DESTINO}")
        ouvir(ficheiros, cego=args.cego)
        print()
        return 0

    print(f'\n🔊 A dizer: "{FRASE}"')
    print(f"   Os ficheiros ficam em {DESTINO}")

    ficheiros: list[tuple[str, Path, str]] = []

    cabecalho("Piper — a voz de agora")
    gerar_piper(ficheiros)

    cabecalho("phoonnx — as vozes novas de português europeu")
    gerar_phoonnx(ficheiros)

    cabecalho("macOS — as vozes que já vêm no Mac")
    gerar_mac(ficheiros)

    if not ficheiros:
        print("\n❌ Não se gerou nada. Vê os erros aí em cima.\n")
        return 1

    print(f"\n🎧 {len(ficheiros)} vozes prontas:")
    for nome, caminho, descricao in ficheiros:
        print(f"     {caminho.name:<26} {descricao}")

    if args.ouvir or args.cego:
        ouvir(ficheiros, cego=args.cego)
    else:
        print("\n   Para as ouvir:  python scripts/testar_vozes.py --cego")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
