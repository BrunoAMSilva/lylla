#!/usr/bin/env python3
"""A CLASSE PESADA — vozes neuronais, com a TUA voz como referência.

O `testar_vozes.py` compara vozes pequenas que cabem no Pi. Este compara as
grandes, que só correm no Mac. É a diferença entre uma voz de 60 MB e uma de
2 GB, e ouve-se.

    python scripts/testar_vozes_neuronais.py --gravar          # 15 s da tua voz
    python scripts/testar_vozes_neuronais.py --motor xtts-ptpt
    python scripts/testar_vozes.py --so-ouvir --cego           # ouvir tudo às cegas

## A ideia que muda o problema

Não há vozes pt-PT boas nos modelos abertos porque não há dados de treino em
português europeu — é um mercado de 10 milhões de pessoas contra 200 milhões
do Brasil. Os modelos de **clonagem** não precisam disso: precisam de 10
segundos de referência. Está publicado (arXiv 2603.05977) que a saída herda o
**sotaque** da referência, e não só o timbre — o artigo existe para *suprimir*
esse efeito, que aqui é exatamente o que queremos.

Ou seja: gravas-te a ler uma frase em português, e o robô passa a falar
português de Portugal a sério. Podes usar a tua voz, a da Lara, a de quem
quiser — desde que a pessoa saiba e concorde. Voz de alguém é coisa dessa
pessoa.

## Motores (cada um no seu venv — as dependências brigam entre si)

    # A · XTTS — o primeiro a experimentar
    python3.12 -m venv ~/.venvs/zeca-xtts && source ~/.venvs/zeca-xtts/bin/activate
    pip install torch torchaudio coqui-tts huggingface_hub

    # B · MLX — Qwen3 e Chatterbox, nativo em Metal
    python3.12 -m venv ~/.venvs/zeca-mlx && source ~/.venvs/zeca-mlx/bin/activate
    pip install -U mlx-audio

⚠️ Nada disto foi testado nesta máquina — não há Mac nem acesso ao Hugging Face
   do lado de cá. Cada motor apanha o erro e diz-te o comando exato. Se algum
   falhar de maneira que não esteja prevista, o traço fica no ecrã.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "data" / "vozes"
REFERENCIA = RAIZ / "data" / "referencia.wav"
REFERENCIA_TXT = RAIZ / "data" / "referencia.txt"

FRASE = (
    "Olá Lara! Eu sou o Zeca. "
    "Tenho 2 rodas, 4 servos nos braços e 32 luzes em cada olho. "
    "Queres dar uma volta pela sala?"
)

# Uma frase com os três sinais que denunciam um sotaque brasileiro num robô que
# devia ser português: vogais átonas reduzidas, o /s/ final chiado, e nenhuma
# vogal de apoio a seguir a consoante final.
FRASE_TESTE_SOTAQUE = (
    "Os pastéis de Belém estão excelentes. "
    "O Rodrigo trouxe o telemóvel e o comboio das seis."
)


def erro(motor: str, mensagem: object, ajuda: str = "") -> None:
    print(f"\n❌ {motor}: {mensagem}")
    if ajuda:
        print(f"   → {ajuda}")


def diagnostico_do_python(venv: str) -> None:
    """Diz QUAL Python está a correr isto, e se é um venv.

    Este projeto já perdeu horas com o mesmo engano: neste Mac o `pip` aponta
    para o Python 3.10 do python.org e o `python3` para o 3.14 do Homebrew.
    Instala-se num, corre-se no outro, e o erro que sai é "No module named X"
    — que parece um problema de instalação e não é.
    """
    num_venv = sys.prefix != sys.base_prefix
    print(f"\n   Este Python é: {sys.executable}")
    print(f"   Dentro de um venv: {'sim' if num_venv else 'NÃO ← é quase de certeza isto'}")
    if num_venv:
        return
    print("\n   Instala e corre com o MESMO Python, pelo caminho absoluto.")
    print("   Assim não é preciso activar nada e não há enganos possíveis:\n")
    print(f"     python3 -m venv ~/.venvs/{venv}")
    print(f"     ~/.venvs/{venv}/bin/python -m pip install -U pip")
    print(f"     ~/.venvs/{venv}/bin/python -m pip install <o que falta>")
    print(f"     ~/.venvs/{venv}/bin/python {Path(sys.argv[0]).as_posix()} --motor ...")


def avisar_do_tts_velho() -> None:
    """O pacote `tts` (Coqui original, morto em 2023) colide com o coqui-tts."""
    import importlib.metadata as metadados

    try:
        versao = metadados.version("tts")
    except metadados.PackageNotFoundError:
        return
    print(f"   ⚠️  Tens o pacote `tts` {versao} — o Coqui original, abandonado em 2023.")
    print("      Dá o mesmo módulo `TTS` que o coqui-tts, e ganha quem for importado")
    print("      primeiro. Desinstala-o antes de continuar:")
    print("        python -m pip uninstall -y tts\n")


def dispositivo(preferir_mps: bool) -> str:
    """CPU por omissão, e é de propósito.

    O MPS no XTTS tem um bug aberto (coqui-ai/TTS#3649) em que o processo fica
    pendurado para sempre em vez de falhar. Pendurado é pior que lento.
    """
    if not preferir_mps:
        return "cpu"
    try:
        import torch

        return "mps" if torch.backends.mps.is_available() else "cpu"
    except ImportError:
        return "cpu"


def ler_referencia() -> Path | None:
    if REFERENCIA.is_file():
        return REFERENCIA
    erro("referência", f"falta o {REFERENCIA}",
         "grava-a: python scripts/testar_vozes_neuronais.py --gravar")
    return None


# ------------------------------------------------------------------ gravar


def gravar(segundos: int, dispositivo_audio: str) -> int:
    """Grava a voz de referência com o ffmpeg."""
    if not shutil.which("ffmpeg"):
        erro("gravar", "não há ffmpeg", "brew install ffmpeg")
        return 1

    REFERENCIA.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n🎙️  {segundos} segundos, a partir do sinal. Lê isto com calma:\n")
    print(f"      {FRASE_TESTE_SOTAQUE}\n")
    print("   (quarto silencioso, telemóvel longe, sem música)")
    for i in (3, 2, 1):
        print(f"   {i}…")
        time.sleep(1)
    print("   🔴 A GRAVAR\n")

    comando = [
        "ffmpeg", "-y", "-f", "avfoundation", "-i", dispositivo_audio,
        "-t", str(segundos), "-ar", "24000", "-ac", "1",
        str(REFERENCIA), "-loglevel", "error",
    ]
    resultado = subprocess.run(comando, check=False)
    if resultado.returncode != 0 or not REFERENCIA.is_file():
        erro("gravar", "o ffmpeg não gravou nada",
             'vê os dispositivos:  ffmpeg -f avfoundation -list_devices true -i ""\n'
             "   e repete com --dispositivo \":1\" (ou o índice certo).\n"
             "   Alternativa: grava no Gravador de Voz, exporta para WAV e põe em\n"
             f"   {REFERENCIA}")
        return 1

    REFERENCIA_TXT.write_text(FRASE_TESTE_SOTAQUE, encoding="utf-8")
    print(f"   ✅ {REFERENCIA}")
    print(f"   ✅ {REFERENCIA_TXT}  (a transcrição — o Qwen3 precisa dela)")
    print("\n   Ouve-a antes de continuar:  afplay data/referencia.wav\n")
    return 0


# ------------------------------------------------------------------ motores


def motor_xtts(nome: str, repo: str | None, texto: str, dev: str) -> Path | None:
    """XTTS-v2. Com repo=None usa o modelo base (o controlo brasileiro)."""
    avisar_do_tts_velho()
    referencia = ler_referencia()
    if referencia is None:
        return None
    destino = DESTINO / f"{nome}.wav"

    if repo is None:
        # O modelo base pede a concordância com a licença CPML por variável.
        os.environ.setdefault("COQUI_TOS_AGREED", "1")
        from TTS.api import TTS

        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(dev)
        tts.tts_to_file(text=texto, file_path=str(destino),
                        speaker_wav=[str(referencia)], language="pt")
        return destino

    import scipy.io.wavfile as wavfile
    from huggingface_hub import hf_hub_download
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    pasta = Path.home() / ".cache" / "zeca-xtts-ptpt"
    pasta.mkdir(parents=True, exist_ok=True)
    for ficheiro in ("model.pth", "config.json", "vocab.json", "dvae.pth", "mel_stats.pth"):
        if not (pasta / ficheiro).is_file():
            print(f"   ⬇️  {ficheiro}")
            hf_hub_download(repo_id=repo, filename=ficheiro, local_dir=str(pasta))

    config = XttsConfig()
    config.load_json(str(pasta / "config.json"))
    modelo = Xtts.init_from_config(config)
    modelo.load_checkpoint(config, checkpoint_dir=str(pasta), use_deepspeed=False)
    modelo.to(dev)

    saida = modelo.synthesize(
        text=texto, config=config, speaker_wav=str(referencia),
        language="pt", gpt_cond_len=6, temperature=0.7,
    )
    wavfile.write(str(destino), 24000, saida["wav"])
    return destino


def motor_mlx(nome: str, modelo: str, texto: str, lang_code: str | None) -> Path | None:
    """Qwen3-TTS e Chatterbox, por cima do mlx-audio (Metal nativo)."""
    referencia = ler_referencia()
    if referencia is None:
        return None

    from mlx_audio.tts.generate import generate_audio

    argumentos: dict[str, object] = {
        "text": texto,
        "model": modelo,
        "ref_audio": str(referencia),
        "file_prefix": nome,
    }
    if lang_code:
        argumentos["lang_code"] = lang_code
    if REFERENCIA_TXT.is_file():
        # O Qwen3-Base quer a transcrição exata do clip de referência.
        argumentos["ref_text"] = REFERENCIA_TXT.read_text(encoding="utf-8").strip()

    anterior = Path.cwd()
    DESTINO.mkdir(parents=True, exist_ok=True)
    os.chdir(DESTINO)
    try:
        generate_audio(**argumentos)
    finally:
        os.chdir(anterior)

    # O generate_audio escolhe o nome do ficheiro; ficamos com o mais recente.
    candidatos = sorted(DESTINO.glob(f"{nome}*.wav"), key=lambda p: p.stat().st_mtime)
    if not candidatos:
        raise RuntimeError("o mlx-audio não deixou nenhum .wav")
    destino = DESTINO / f"{nome}.wav"
    if candidatos[-1] != destino:
        candidatos[-1].replace(destino)
    return destino


MOTORES = {
    "xtts-ptpt": (
        "XTTS-v2 afinado para português europeu · clona a tua voz",
        lambda t, d: motor_xtts("xtts-ptpt", "Martim-Ramos-Neural/xtts-v2-antonio-oliveira-pt-pt", t, d),
        "pip install torch torchaudio coqui-tts huggingface_hub",
        "zeca-xtts",
    ),
    "xtts-base": (
        "XTTS-v2 base · o controlo — deve soar BRASILEIRO",
        lambda t, d: motor_xtts("xtts-base", None, t, d),
        "pip install torch torchaudio coqui-tts",
        "zeca-xtts",
    ),
    "qwen3": (
        "Qwen3-TTS 1.7B · Apache-2.0, o mais recente",
        lambda t, d: motor_mlx("qwen3", "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit", t, None),
        "pip install -U mlx-audio",
        "zeca-mlx",
    ),
    "chatterbox": (
        "Chatterbox multilingue v3 · MIT, mas lento",
        lambda t, d: motor_mlx("chatterbox", "mlx-community/chatterbox-multilingual-v3", t, "pt"),
        "pip install -U mlx-audio",
        "zeca-mlx",
    ),
}


# -------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ensaia as vozes neuronais grandes, clonadas da tua voz.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="motores:\n" + "\n".join(f"  {k:<12} {v[0]}" for k, v in MOTORES.items()),
    )
    parser.add_argument("--motor", choices=sorted(MOTORES))
    parser.add_argument("--gravar", action="store_true", help="gravar a voz de referência")
    parser.add_argument("--segundos", type=int, default=15)
    parser.add_argument("--dispositivo", default=":0", help="entrada de áudio do avfoundation")
    parser.add_argument("--frase", default=FRASE)
    parser.add_argument("--sotaque", action="store_true",
                        help="usar a frase que denuncia o sotaque brasileiro")
    parser.add_argument("--mps", action="store_true",
                        help="tentar a GPU (cuidado: o XTTS pendura-se em MPS nalgumas versões)")
    args = parser.parse_args()

    if args.gravar:
        return gravar(args.segundos, args.dispositivo)

    if not args.motor:
        parser.print_help()
        return 1

    descricao, funcao, instalacao, venv = MOTORES[args.motor]
    texto = FRASE_TESTE_SOTAQUE if args.sotaque else args.frase
    dev = dispositivo(args.mps)

    DESTINO.mkdir(parents=True, exist_ok=True)
    print(f"\n🧠 {args.motor} — {descricao}")
    print(f"   {dev} · a primeira vez descarrega ~2 GB\n")

    inicio = time.monotonic()
    try:
        caminho = funcao(texto, dev)
    except ImportError as falha:
        erro(args.motor, falha, instalacao)
        diagnostico_do_python(venv)
        return 1
    except Exception as falha:  # noqa: BLE001
        erro(args.motor, falha)
        print("\n   Traço completo:\n")
        import traceback

        traceback.print_exc()
        return 1

    if caminho is None:
        return 1

    decorrido = time.monotonic() - inicio
    print(f"\n   ✅ {caminho.name}   ({decorrido:.1f} s)")
    if decorrido > 3:
        print(f"      ⚠️  {decorrido:.0f} s por frase é muito para uma conversa.")
        print("         Ou pré-geras as frases fixas, ou este motor não serve.")
    print(f"\n   Ouve:  afplay {caminho}")
    print("   E depois compara tudo às cegas:")
    print("     python scripts/testar_vozes.py --so-ouvir --cego\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
