#!/usr/bin/env python3
"""VER PELA CÂMARA DO ROBÔ — no browser do Mac, do telemóvel, do que for.

    /usr/bin/python3 scripts/ver_camera.py                → abre http://robo.local:8000
    /usr/bin/python3 scripts/ver_camera.py --rodar        # se a câmara estiver de pernas para o ar
    /usr/bin/python3 scripts/ver_camera.py --porta 8080 --largura 640 --altura 480

Corre com o Python DO SISTEMA (/usr/bin/python3), porque só precisa do
picamera2, que vem do apt. Não precisa do venv nem do resto do projeto — dá
para usar no primeiro dia, antes de estar mais nada instalado.

É uma ferramenta de teste: em funcionamento normal o robô NÃO faz streaming
de imagem nenhum (ver §10.3 do PLANO.md). O vídeo só anda na rede de casa e
não fica guardado em lado nenhum. Ctrl+C para parar.
"""

from __future__ import annotations

import argparse
import io
import socket
import sys
import threading
from http import server

PAGINA = """<!doctype html>
<html lang="pt"><head><meta charset="utf-8"><title>Zeca — o que ele vê</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;background:#161B22;color:#F4F6F8;font-family:sans-serif;text-align:center">
<h2 style="margin:12px;font-weight:normal">O que o Zeca vê</h2>
<img src="stream.mjpg" alt="câmara do robô" style="max-width:100%;height:auto;border-radius:8px">
</body></html>
"""


class UltimoFotograma(io.BufferedIOBase):
    """O picamera2 escreve aqui cada JPEG; quem estiver a ver é acordado."""

    def __init__(self) -> None:
        self.dados: bytes | None = None
        self.novo = threading.Condition()

    def write(self, buf) -> int:  # type: ignore[override]
        with self.novo:
            self.dados = bytes(buf)
            self.novo.notify_all()
        return len(buf)


saida = UltimoFotograma()


class Pedido(server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            conteudo = PAGINA.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(conteudo)))
            self.end_headers()
            self.wfile.write(conteudo)
        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    with saida.novo:
                        saida.novo.wait()
                        dados = saida.dados
                    if not dados:
                        continue
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(dados)))
                    self.end_headers()
                    self.wfile.write(dados)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # quem estava a ver fechou a página — normal
        else:
            self.send_error(404)

    def log_message(self, *args) -> None:  # silêncio no terminal
        pass


class Servidor(server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--porta", type=int, default=8000)
    parser.add_argument("--largura", type=int, default=1280)
    parser.add_argument("--altura", type=int, default=720)
    parser.add_argument("--rodar", action="store_true", help="roda a imagem 180°")
    args = parser.parse_args()

    try:
        from picamera2 import Picamera2
        from picamera2.encoders import JpegEncoder
        from picamera2.outputs import FileOutput
        from libcamera import Transform
    except ImportError as erro:
        print(f"❌ Falta o picamera2 ({erro}).")
        print("   sudo apt install -y --no-install-recommends python3-picamera2")
        print("   e corre com o Python do sistema:  /usr/bin/python3 scripts/ver_camera.py")
        return 1

    camara = Picamera2()
    camara.configure(camara.create_video_configuration(
        main={"size": (args.largura, args.altura)},
        transform=Transform(hflip=args.rodar, vflip=args.rodar),
    ))
    camara.start_recording(JpegEncoder(q=80), FileOutput(saida))

    nome = socket.gethostname()
    print(f"\n📷 A transmitir {args.largura}×{args.altura}. Abre no browser (Mac ou telemóvel):")
    print(f"   http://{nome}.local:{args.porta}\n   Ctrl+C para parar.\n")
    try:
        Servidor(("0.0.0.0", args.porta), Pedido).serve_forever()
    except KeyboardInterrupt:
        print("\n   parado.\n")
    finally:
        camara.stop_recording()
    return 0


if __name__ == "__main__":
    sys.exit(main())
