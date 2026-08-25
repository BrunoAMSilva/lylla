#!/usr/bin/env python3
"""DESCARREGAR OS MODELOS DE IA.

    python scripts/download_models.py

São ~150 MB no total. Só é preciso correr uma vez (e sempre que se apagar
a pasta models/, que está no .gitignore por serem ficheiros grandes).

O que vem:
  · YuNet   —  deteção de caras          (~350 KB)
  · SFace   —  reconhecimento de caras   (~40 MB)
  · tugão   —  voz do Piper, SÓ com --com-voz-piper (~63 MB)

A voz do robô é a Joana e vem do Mac (config/robot.yaml → voz.servidor), por
isso a voz do Piper já não é precisa. Fica disponível como recurso para quem
quiser um robô que fala sem o Mac ligado — mas percebe-se mal, foi por isso
que a Lara a rejeitou.

O modelo do Whisper descarrega-se sozinho na primeira vez que o robô ouvir.
O modelo da palavra-chave é treinado por vocês na fase 7.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402

# (ficheiro, url, descrição, opcional)
MODELOS = [
    (
        "face_detection_yunet_2023mar.onnx",
        "https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "YuNet — encontra caras (~2-3 ms por imagem no Pi 5)",
    ),
    (
        "face_recognition_sface_2021dec.onnx",
        "https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "SFace — transforma uma cara em 128 números",
    ),
    (
        "pt_PT-tugão-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_PT/"
        "tug%C3%A3o/medium/pt_PT-tug%C3%A3o-medium.onnx",
        "tugão — voz de recurso do Piper (a boa é a Joana, no Mac)",
        True,
    ),
    (
        "pt_PT-tugão-medium.onnx.json",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_PT/"
        "tug%C3%A3o/medium/pt_PT-tug%C3%A3o-medium.onnx.json",
        "configuração da voz de recurso",
        True,
    ),
]


def barra(bloco: int, tamanho: int, total: int) -> None:
    if total <= 0:
        return
    feito = min(bloco * tamanho, total)
    pct = feito / total
    cheio = int(34 * pct)
    print(
        f"\r     [{'█' * cheio}{'░' * (34 - cheio)}] "
        f"{pct * 100:5.1f}%  ({feito / 1e6:.1f} MB)",
        end="", flush=True,
    )


def main() -> int:
    com_piper = "--com-voz-piper" in sys.argv
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n📥 A descarregar para {config.MODELS_DIR}\n")

    falhas = 0
    for entrada in MODELOS:
        ficheiro, url, descricao = entrada[0], entrada[1], entrada[2]
        opcional = len(entrada) > 3 and entrada[3]
        if opcional and not com_piper:
            print(f"  ⏭️  {ficheiro}  (só com --com-voz-piper)")
            continue
        destino = config.MODELS_DIR / ficheiro
        if destino.exists() and destino.stat().st_size > 1000:
            print(f"  ✅ {ficheiro}  (já existe)")
            continue
        print(f"  ⬇️  {ficheiro}")
        print(f"     {descricao}")
        try:
            urllib.request.urlretrieve(url, destino, reporthook=barra)  # noqa: S310
            print(f"\n     ✅ {destino.stat().st_size / 1e6:.1f} MB\n")
        except Exception as erro:  # noqa: BLE001
            print(f"\n     ❌ falhou: {erro}")
            print(f"     descarrega à mão de:\n     {url}\n")
            destino.unlink(missing_ok=True)
            falhas += 1

    if falhas:
        print(f"⚠️  {falhas} modelo(s) falharam. Há internet no robô?\n")
        return 1

    print("🎉 Modelos prontos. Verifica tudo com:")
    print("   python scripts/check_health.py\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
