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

import threading
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

# ⚠️ O YuNet e o SFace são UM objeto cada, partilhado por quem os chamar, e
#    guardam estado por dentro (o detetor tem um tamanho de entrada que se
#    define antes de cada deteção). Dois fios a usá-los ao mesmo tempo não dão
#    erro nenhum: devolvem menos caras, ou uma assinatura que não é de
#    ninguém. É a mesma armadilha do transcribe_stream() no cérebro.
#
#    Apareceu a sério no ver_visao.py: o ciclo da câmara a reconhecer 10x por
#    segundo enquanto o browser pedia uma captura para o registo — de quatro
#    fotos pedidas, duas desapareciam em silêncio. Uma assinatura estragada é
#    pior do que uma que falha: fica lá, e a Lara passa a ser mal reconhecida
#    sem que nada tenha dado erro.
_lock = threading.Lock()


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
    except ImportError as erro:
        print(
            f"⚠️  Visão indisponível: falta o OpenCV ({erro}).\n"
            "\n"
            "    ⚠️  ISTO NÃO É A CÂMARA. Se viste 'imagem 640×480' acima, o\n"
            "        cabo e o sensor estão bons — não voltes a mexer no CSI.\n"
            "\n"
            "    A causa nº1 é estar-se a correr o Python errado:\n"
            "        which python        # tem de dar .venv/bin/python\n"
            "        source .venv/bin/activate\n"
            "\n"
            "    Se já for o do venv e mesmo assim faltar:\n"
            "        pip install -r requirements.txt\n"
            "\n"
            "    E se o erro passar a ser 'libGL.so.1' em vez deste, é o\n"
            "    pacote errado — o Pi OS Lite não tem bibliotecas gráficas:\n"
            "        pip uninstall -y opencv-python\n"
            "        pip install 'opencv-python-headless>=4.10,<5'"
        )
        _detetor = None
        return False

    try:
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


def disponivel() -> bool:
    """A visão arranca mesmo? (OpenCV instalado E modelos a carregar)

    ⚠️ Não é a mesma pergunta que "os ficheiros dos modelos existem". Sem o
       cv2 instalado os .onnx estão lá na mesma e a visão está morta — foi
       exatamente assim que o check_health.py já deu dois ✅ a uma visão que
       não via nada.
    """
    return _iniciar()


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
    with _lock:                      # ⚠️ ver a nota do _lock lá em cima
        _detetor.setInputSize((largura, altura))
        _, caras = _detetor.detect(imagem)
    return [] if caras is None else list(caras)


def escalar_cara(cara, escala_x: float, escala_y: float):
    """A mesma cara, noutra resolução — a caixa E os cinco pontos.

    ⚠️ O BUG QUE A IMPEDIA DE RECONHECER QUEM QUER QUE FOSSE (19/09/2026).
       Uma cara do YuNet são 15 números: a caixa (x, y, w, h), os olhos, o
       nariz e os cantos da boca (5 pares x, y), e a confiança. O modo
       secretária deteta numa imagem de 320×240 e tira a assinatura da de
       640×480 — e só escalava a CAIXA. O `alignCrop` alinha a cara pelos
       cinco pontos, que continuavam em coordenadas da imagem pequena: a
       «cara» recortada era um bocado de testa e parede. Assinatura lixo,
       ninguém reconhecido — mesmo logo a seguir a registar a cara. O registo
       não sofria disto (deteta e assina na mesma imagem), por isso a cara
       ficava bem guardada; era a leitura que estava errada.
    """
    escalada = np.array(cara, dtype=np.float32, copy=True)
    escalada[0:14:2] *= escala_x      # x, w e os cinco x
    escalada[1:14:2] *= escala_y      # y, h e os cinco y
    return escalada


def assinatura(imagem, cara) -> np.ndarray | None:
    """Transforma uma cara em 128 números.

    Isto é o coração de tudo: um rosto vira um ponto num espaço de 128
    dimensões, e caras parecidas ficam perto umas das outras.
    """
    if not _iniciar():
        return None
    try:
        with _lock:                  # ⚠️ ver a nota do _lock lá em cima
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


def _nome_seguro(nome: str) -> str:
    """O nome vira `data/faces/<nome>.npz`, e pode vir de um POST (ver_visao.py).

    Sem isto, um nome com "../" escrevia fora da pasta. A validação boa está no
    servidor; esta é a rede por baixo, para o caso de aparecer outro caminho.
    """
    limpo = (nome or "").strip()
    if not limpo or limpo in (".", "..") or set(limpo) & set("/\\\x00"):
        raise ValueError(f"nome de pessoa inválido: {nome!r}")
    return limpo


def guardar_pessoa(nome: str, vetores: list[np.ndarray]) -> Path:
    """Guarda a média das assinaturas de uma pessoa.

    Fazer a média de 8 fotos (ângulos e luzes diferentes) dá um resultado
    muito mais estável do que usar uma só.
    """
    nome = _nome_seguro(nome)
    PASTA_CARAS.mkdir(parents=True, exist_ok=True)
    media = np.mean(np.array([v.flatten() for v in vetores]), axis=0)
    media = media / np.linalg.norm(media)
    caminho = PASTA_CARAS / f"{nome}.npz"
    np.savez(caminho, assinatura=media, n_fotos=len(vetores))
    carregar_conhecidos()
    return caminho


def apagar_pessoa(nome: str) -> bool:
    """Direito a ser esquecido. Um comando, e desaparece."""
    caminho = PASTA_CARAS / f"{_nome_seguro(nome)}.npz"
    if caminho.exists():
        caminho.unlink()
        carregar_conhecidos()
        return True
    return False
