"""RECONHECER CARAS — OpenCV YuNet (detetar) + SFace (identificar).

╔══════════════════════════════════════════════════════════════════════════╗
║  PORQUÊ NÃO USAMOS A face_recognition                                    ║
║                                                                          ║
║  É a biblioteca que toda a gente recomenda na Internet — e está MORTA:   ║
║  a última versão é de fevereiro de 2020 e obriga a compilar o dlib a     ║
║  partir do código-fonte (30 a 60 minutos num Raspberry Pi, e falha por   ║
║  falta de memória).                                                      ║
║                                                                          ║
║  O OpenCV moderno já traz tudo o que é preciso:                          ║
║    · YuNet  → encontra caras         (~2-3 ms por imagem no Pi 5)        ║
║    · SFace  → identifica-as          (~25-35 ms por cara)                ║
║  Instalação:  pip install opencv-python.  Um comando.                    ║
╚══════════════════════════════════════════════════════════════════════════╝

🔒 PRIVACIDADE
   Não guardamos fotografias. Guardamos 128 números por pessoa (o
   "embedding"), em data/faces/. Não se consegue reconstruir a cara a partir
   deles. A pasta está no .gitignore e qualquer pessoa pode ser apagada com:

       python scripts/enrol_face.py --apagar Nome
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from robot import config

MODELO_DETETOR = config.MODELS_DIR / "face_detection_yunet_2023mar.onnx"
MODELO_RECONHECEDOR = config.MODELS_DIR / "face_recognition_sface_2021dec.onnx"
PASTA_CARAS = config.DATA_DIR / "faces"

_detetor = None
_reconhecedor = None
_conhecidos: dict[str, np.ndarray] = {}
_carregado = False


def _iniciar() -> bool:
    """Carrega os modelos e as assinaturas conhecidas. True se correu bem."""
    global _detetor, _reconhecedor, _carregado
    if _carregado:
        return _detetor is not None
    _carregado = True

    if not MODELO_DETETOR.exists() or not MODELO_RECONHECEDOR.exists():
        print(
            "⚠️  Faltam os modelos de visão.\n"
            "    Corre:  python scripts/download_models.py"
        )
        return False
    try:
        import cv2

        _detetor = cv2.FaceDetectorYN.create(
            str(MODELO_DETETOR), "", (320, 320), 0.85, 0.3, 5000
        )
        _reconhecedor = cv2.FaceRecognizerSF.create(str(MODELO_RECONHECEDOR), "")
        carregar_conhecidos()
        return True
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Visão indisponível ({erro}).")
        _detetor = None
        return False


def carregar_conhecidos() -> None:
    """Lê as assinaturas de data/faces/*.npz."""
    _conhecidos.clear()
    PASTA_CARAS.mkdir(parents=True, exist_ok=True)
    for ficheiro in PASTA_CARAS.glob("*.npz"):
        try:
            dados = np.load(ficheiro)
            _conhecidos[ficheiro.stem] = dados["assinatura"]
        except Exception as erro:  # noqa: BLE001
            print(f"⚠️  Não consegui ler {ficheiro.name}: {erro}")


def pessoas_conhecidas() -> list[str]:
    if not _carregado:
        _iniciar()
    return sorted(_conhecidos)


def detetar(imagem) -> list:
    """Devolve a lista de caras encontradas numa imagem."""
    if not _iniciar():
        return []
    altura, largura = imagem.shape[:2]
    _detetor.setInputSize((largura, altura))
    _, caras = _detetor.detect(imagem)
    return [] if caras is None else list(caras)


def assinatura(imagem, cara) -> np.ndarray | None:
    """Transforma uma cara em 128 números.

    Isto é o coração de tudo: um rosto vira um ponto num espaço de 128
    dimensões, e caras parecidas ficam perto umas das outras.
    """
    if not _iniciar():
        return None
    try:
        alinhada = _reconhecedor.alignCrop(imagem, cara)
        vetor = _reconhecedor.feature(alinhada)
        return vetor / np.linalg.norm(vetor)  # normalizar
    except Exception:  # noqa: BLE001
        return None


def identificar(vetor: np.ndarray) -> tuple[str | None, float]:
    """Compara com toda a gente que conhecemos.

    Devolve (nome, semelhança). Nome é None se não reconhecer ninguém.
    """
    if vetor is None or not _conhecidos:
        return None, 0.0
    limiar = float(config.obter("faces.limiar", 0.45))
    melhor_nome, melhor_valor = None, -1.0
    for nome, referencia in _conhecidos.items():
        semelhanca = float(np.dot(vetor.flatten(), referencia.flatten()))
        if semelhanca > melhor_valor:
            melhor_nome, melhor_valor = nome, semelhanca
    if melhor_valor >= limiar:
        return melhor_nome, melhor_valor
    return None, melhor_valor


def quem_esta_a_ver(imagem=None) -> str | None:
    """A função principal: quem é que está à frente do robô?

    >>> nome = quem_esta_a_ver()
    >>> if nome: falar(f"Olá, {nome}!")
    """
    if config.a_simular():
        config.sim("câmara → (simulação: não vejo ninguém)")
        return None

    if imagem is None:
        from robot.perception import camera

        imagem = camera.tirar_foto()
    if imagem is None:
        return None

    caras = detetar(imagem)
    if not caras:
        return None

    # A cara maior é, quase sempre, a pessoa que está a falar connosco.
    maior = max(caras, key=lambda c: c[2] * c[3])
    nome, _ = identificar(assinatura(imagem, maior))
    return nome


def guardar_pessoa(nome: str, vetores: list[np.ndarray]) -> Path:
    """Guarda a média das assinaturas de uma pessoa.

    Fazer a média de 8 fotos (ângulos e luzes diferentes) dá um resultado
    muito mais estável do que usar uma só.
    """
    PASTA_CARAS.mkdir(parents=True, exist_ok=True)
    media = np.mean(np.array([v.flatten() for v in vetores]), axis=0)
    media = media / np.linalg.norm(media)
    caminho = PASTA_CARAS / f"{nome}.npz"
    np.savez(caminho, assinatura=media, n_fotos=len(vetores))
    carregar_conhecidos()
    return caminho


def apagar_pessoa(nome: str) -> bool:
    """Direito a ser esquecido. Um comando, e desaparece."""
    caminho = PASTA_CARAS / f"{nome}.npz"
    if caminho.exists():
        caminho.unlink()
        carregar_conhecidos()
        return True
    return False
