"""A CÂMARA — Raspberry Pi Camera Module 3.

⚠️ NÃO ESQUECER O CABO ADAPTADOR.
   O Raspberry Pi 5 mudou para conectores CSI de 22 pinos. A Camera Module 3
   vem com o cabo antigo de 15 pinos. Sem o adaptador 22→15 a câmara
   simplesmente não liga — é o erro mais comum de quem vem do Pi 4.

Testar sem Python (desde o Raspberry Pi OS Bookworm chamam-se rpicam-*):
    rpicam-hello --list-cameras       # tem de aparecer um imx708
    rpicam-jpeg -o teste.jpg

⚠️ O picamera2 instala-se pelo apt (python3-picamera2), nunca pelo pip. Para
   este import funcionar dentro do venv, o venv tem de ter sido criado com
   `python3 -m venv --system-site-packages .venv` (Apêndice B do PLANO.md).
"""

from __future__ import annotations

import atexit

from robot import config

_camara = None
_iniciada = False


def _iniciar():
    global _camara, _iniciada
    if _iniciada or config.a_simular():
        _iniciada = True
        return _camara
    _iniciada = True
    try:
        from picamera2 import Picamera2

        largura, altura = config.obter("faces.resolucao", [640, 480])
        _camara = Picamera2()
        _camara.configure(
            _camara.create_preview_configuration(
                main={"size": (int(largura), int(altura)), "format": "RGB888"}
            )
        )
        _camara.start()
        import time

        time.sleep(1.5)  # dar tempo ao autofoco e à exposição
    except Exception as erro:  # noqa: BLE001
        print(
            f"⚠️  Câmara indisponível ({erro}).\n"
            f"    Verifica:  rpicam-hello --list-cameras\n"
            f"    E o cabo adaptador 22→15 pinos. Se o erro for 'No module named\n"
            f"    picamera2', o venv não foi criado com --system-site-packages."
        )
        _camara = None
    return _camara


def tirar_foto():
    """Devolve uma imagem (array numpy BGR), ou None se não houver câmara."""
    if config.a_simular():
        config.sim("câmara → foto simulada")
        return None
    camara = _iniciar()
    if camara is None:
        return None
    try:
        return camara.capture_array()
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Falha ao tirar foto: {erro}")
        return None


def guardar_foto(caminho: str) -> bool:
    """Guarda uma foto em disco. Só para testes — o robô não guarda imagens."""
    imagem = tirar_foto()
    if imagem is None:
        return False
    try:
        import cv2

        cv2.imwrite(caminho, imagem)
        return True
    except Exception:  # noqa: BLE001
        return False


def disponivel() -> bool:
    return not config.a_simular() and _iniciar() is not None


@atexit.register
def _fechar() -> None:
    global _camara
    if _camara is not None:
        try:
            _camara.stop()
            _camara.close()
        except Exception:  # noqa: BLE001, S110
            pass
        _camara = None
