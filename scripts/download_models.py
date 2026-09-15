#!/usr/bin/env python3
"""DESCARREGAR OS MODELOS DE IA.

    python scripts/download_models.py            # YuNet e SFace para o Pi
    python scripts/download_models.py --tudo     # inclui vozes locais antigas

Só é preciso correr uma vez (e sempre que se apagar a pasta models/, que está
no .gitignore por serem ficheiros grandes).

O que a arquitetura atual usa:
  · YuNet   —  deteção de caras          (~350 KB)
  · SFace   —  reconhecimento de caras   (~40 MB)

Ambos correm no Raspberry Pi. A transcrição, o modelo de linguagem e a síntese
de voz correm no mac mini. Os modelos de voz locais permanecem disponíveis
para repetir experiências antigas, mas não fazem parte da montagem atual. Só
são descarregados com `--tudo` ou quando `voz.modelo_tts` os pede de propósito.

A voz da GLaDOS vem da release do projeto dnhkng/GLaDOS (MIT), não da pasta do
lado. É essa a diferença entre "funciona no meu Mac" e "funciona no Pi": o robô
tem de se conseguir montar de raiz sem depender de nada que esteja fora deste
repositório.

⚠️ A voz da GLaDOS é derivada do Portal 2. Uso pessoal em casa, como a fan art
   do Astro Bot. Não redistribuir o modelo nem áudio gerado com ele.

O modelo de transcrição é instalado no mac mini. O modelo da palavra-chave é
treinado no Pi na etapa própria.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402

# ⚠️ media.githubusercontent.com/media/… e NÃO raw.githubusercontent.com.
# O opencv_zoo guarda os modelos em git-lfs: o `raw` devolve um ponteiro de
# texto com 131 bytes, não o modelo. Passava despercebido no download e só
# rebentava lá à frente, ao carregar o ONNX, com um erro que ninguém liga a isto.
BASE_OPENCV = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
BASE_PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_PT/"
BASE_GLADOS = "https://github.com/dnhkng/GlaDOS/releases/download/0.1/"
BASE_GLADOS_RAW = "https://raw.githubusercontent.com/dnhkng/GlaDOS/main/models/TTS/"

# grupo: "sempre" · ou o valor de voz.modelo_tts que o torna necessário.
# sha256 é opcional — onde existe, verifica-se. Um download truncado que passe
# despercebido só dá erro lá à frente, no carregamento, e aí ninguém liga as
# duas coisas.
MODELOS = [
    {
        "grupo": "sempre",
        "ficheiro": "face_detection_yunet_2023mar.onnx",
        "url": BASE_OPENCV + "face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "descricao": "YuNet — encontra caras (~2-3 ms por imagem no Pi 5)",
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    },
    {
        "grupo": "sempre",
        "ficheiro": "face_recognition_sface_2021dec.onnx",
        "url": BASE_OPENCV + "face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "descricao": "SFace — transforma uma cara em 128 números",
        "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    },
    {
        "grupo": "glados",
        "ficheiro": "glados.onnx",
        "url": BASE_GLADOS + "glados.onnx",
        "descricao": "GLaDOS — voz inglesa, Piper de 63 MB, corre no próprio Pi",
        "sha256": "17ea16dd18e1bac343090b8589042b4052f1e5456d42cad8842a4f110de25095",
    },
    {
        "grupo": "glados",
        "ficheiro": "glados.onnx.json",
        "url": BASE_GLADOS_RAW + "glados.json",
        "descricao": "configuração da GLaDOS (o Piper procura-a com este nome)",
        "sha256": "01f5e602e1ec04daec6d54960e4d641b5de305f39186e40bf9b4a47bd757a489",
    },
    {
        "grupo": "pt_PT-tugão-medium",
        "ficheiro": "pt_PT-tugão-medium.onnx",
        "url": BASE_PIPER + "tug%C3%A3o/medium/pt_PT-tug%C3%A3o-medium.onnx",
        "descricao": "tugão — voz pt-PT do Piper (percebe-se mal; ver voz_do_robo)",
    },
    {
        "grupo": "pt_PT-tugão-medium",
        "ficheiro": "pt_PT-tugão-medium.onnx.json",
        "url": BASE_PIPER + "tug%C3%A3o/medium/pt_PT-tug%C3%A3o-medium.onnx.json",
        "descricao": "configuração da tugão",
    },
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


def sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def descarregar(modelo: dict) -> bool:
    destino = config.MODELS_DIR / modelo["ficheiro"]
    esperado = modelo.get("sha256")

    if destino.exists() and destino.stat().st_size > 1000:
        if esperado and sha256(destino) != esperado:
            print(f"  ♻️  {modelo['ficheiro']}  (existe mas está corrompido — a repetir)")
            destino.unlink()
        else:
            print(f"  ✅ {modelo['ficheiro']}  (já existe)")
            return True

    print(f"  ⬇️  {modelo['ficheiro']}")
    print(f"     {modelo['descricao']}")

    # Escrever ao lado e mudar o nome só no fim: se a ligação cair a meio, não
    # fica um ficheiro meio-escrito com ar de bom.
    temporario = destino.with_suffix(destino.suffix + ".parcial")
    try:
        urllib.request.urlretrieve(modelo["url"], temporario, reporthook=barra)  # noqa: S310
        if temporario.read_bytes()[:20].startswith(b"version https://git-"):
            raise ValueError(
                "veio um ponteiro do git-lfs em vez do modelo — o URL tem de ser "
                "media.githubusercontent.com/media/…, não raw.githubusercontent.com"
            )
        if esperado:
            obtido = sha256(temporario)
            if obtido != esperado:
                raise ValueError(f"sha256 não bate certo\n     esperado {esperado}\n     obtido   {obtido}")
        temporario.replace(destino)
        print(f"\n     ✅ {destino.stat().st_size / 1e6:.1f} MB\n")
        return True
    except Exception as erro:  # noqa: BLE001
        print(f"\n     ❌ falhou: {erro}")
        print(f"     descarrega à mão de:\n     {modelo['url']}\n")
        temporario.unlink(missing_ok=True)
        return False


def main() -> int:
    tudo = "--tudo" in sys.argv
    voz_escolhida = config.obter("voz.modelo_tts") or ""

    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n📥 A descarregar para {config.MODELS_DIR}")
    if voz_escolhida:
        print(f"   O config/robot.yaml pede a voz '{voz_escolhida}'.\n")
    else:
        print("   Voz no mac mini. Só são necessários os modelos de visão no Pi.\n")

    falhas = 0
    for modelo in MODELOS:
        grupo = modelo["grupo"]
        preciso = grupo == "sempre" or tudo or grupo == voz_escolhida
        if not preciso:
            print(f"  ⏭️  {modelo['ficheiro']}  (só com voz.modelo_tts: \"{grupo}\" ou --tudo)")
            continue
        if not descarregar(modelo):
            falhas += 1

    if falhas:
        print(f"⚠️  {falhas} modelo(s) falharam. Há internet aqui?\n")
        return 1

    print("🎉 Modelos prontos. Verifica tudo com:")
    print("   python scripts/check_health.py\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
