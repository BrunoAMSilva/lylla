#!/usr/bin/env python3
"""A VOZ DA LYLLA — o serviço que corre no MAC.

⚠️ SUBSTITUÍDO pelo `cerebro/` (python -m cerebro.servidor), que faz isto e
   mais: transcreve, pensa e devolve a resposta já em áudio, na mesma porta
   8420 e com o mesmo /falar. Este ficheiro fica porque é pequeno, não tem
   dependências nenhumas e serve de recurso se o cérebro não arrancar.
   Ver docs/AI-config.md.

    python scripts/servidor_voz.py                 # Joana, porta 8420
    python scripts/servidor_voz.py --voz Catarina
    python scripts/servidor_voz.py --vozes         # que vozes pt-PT há neste Mac

Porque é que a voz vive no Mac e não no Pi:

A Lara ouviu às cegas as seis melhores vozes de português europeu que existem
em modelos abertos, mais as do próprio macOS, e escolheu a **Joana**. A Joana
não é um ficheiro que se copie — é uma voz do sistema, só existe no macOS.

Isso não nos custa independência nenhuma: o cérebro grande (o LLM) já vive no
Mac. Sem Mac o robô não tem nada de novo para dizer, e as frases que ele diz
sozinho — bateria fraca, "não te percebi", a saudação — ficam em cache no Pi
depois de serem ditas uma vez. Ou seja: o Pi guarda a voz da Joana em disco e
continua a falar mesmo com o Mac desligado.

O serviço é de propósito burro e sem dependências (só a biblioteca do Python).
Recebe texto, devolve um WAV. Quem quiser trocar a Joana por um modelo neuronal
mais tarde só tem de acrescentar um motor aqui — o Pi não precisa de saber.

⚠️ Fica à escuta na rede local. Qualquer computador de casa pode fazer o Mac
   falar. É uma rede doméstica e o pior que pode acontecer é um robô a dizer
   disparates, mas fica registado.
"""

from __future__ import annotations

import argparse
import array
import hashlib
import io
import json
import math
import platform
import shutil
import subprocess
import sys
import tempfile
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CACHE = Path.home() / ".cache" / "lylla-voz"
MAX_CARACTERES = 1000
PALAVRAS_POR_MINUTO = 180  # o ritmo natural do `say`

_opcoes = argparse.Namespace(voz="Joana", motor="say", velocidade=1.0)


# ---------------------------------------------------------------- os motores
#
# Um motor é uma função (texto, voz, velocidade) -> bytes de um ficheiro WAV.
# Para acrescentar um modelo neuronal mais tarde, escreve outra função com esta
# assinatura e mete-a no dicionário MOTORES. Mais nada muda — nem aqui, nem no
# Pi. É essa a única razão de este serviço existir.


def motor_say(texto: str, voz: str, velocidade: float) -> bytes:
    """As vozes do macOS. Instantâneo, sem modelo nenhum para descarregar."""
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        subprocess.run(
            [
                "say", "-v", voz,
                "-r", str(int(PALAVRAS_POR_MINUTO * velocidade)),
                "-o", tmp.name,
                "--file-format=WAVE",
                "--data-format=LEI16@22050",
                texto,
            ],
            check=True, capture_output=True, timeout=30,
        )
        return Path(tmp.name).read_bytes()


def motor_teste(texto: str, voz: str, velocidade: float) -> bytes:
    """Um apito. Serve para os testes correrem em qualquer máquina."""
    taxa = 22050
    duracao = min(0.05 * max(len(texto), 1), 3.0) / max(velocidade, 0.1)
    amostras = array.array(
        "h",
        (int(12000 * math.sin(2 * math.pi * 440 * i / taxa))
         for i in range(int(taxa * duracao))),
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(taxa)
        wav.writeframes(amostras.tobytes())
    return buffer.getvalue()


MOTORES = {"say": motor_say, "teste": motor_teste}


# -------------------------------------------------------------------- cache


def chave(texto: str, voz: str, velocidade: float) -> str:
    crua = f"{_opcoes.motor}|{voz}|{velocidade:.2f}|{texto.strip()}"
    return hashlib.sha1(crua.encode("utf-8")).hexdigest()


def sintetizar(texto: str, voz: str, velocidade: float) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    ficheiro = CACHE / f"{chave(texto, voz, velocidade)}.wav"
    if ficheiro.is_file():
        return ficheiro.read_bytes()

    audio = MOTORES[_opcoes.motor](texto, voz, velocidade)

    # Escrever ao lado e mudar o nome: se isto morrer a meio, não fica um
    # ficheiro truncado na cache a envenenar todas as vezes seguintes.
    temporario = ficheiro.with_suffix(".parcial")
    temporario.write_bytes(audio)
    temporario.rename(ficheiro)
    return audio


# ------------------------------------------------------------------ serviço


def vozes_instaladas() -> list[str]:
    if not shutil.which("say"):
        return []
    saida = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=False).stdout
    return [
        linha.split("pt_PT")[0].strip()
        for linha in saida.splitlines()
        if "pt_PT" in linha
    ]


class Manipulador(BaseHTTPRequestHandler):
    server_version = "LyllaVoz/1.0"

    def log_message(self, formato, *args):  # noqa: A002
        print(f"   {self.address_string()} · {formato % args}")

    def _responder(self, codigo: int, corpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, codigo: int, dados: dict) -> None:
        self._responder(codigo, json.dumps(dados, ensure_ascii=False).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/saude":
            self._json(200, {
                "ok": True,
                "motor": _opcoes.motor,
                "voz": _opcoes.voz,
                "em_cache": len(list(CACHE.glob("*.wav"))) if CACHE.is_dir() else 0,
            })
        elif self.path == "/vozes":
            self._json(200, {"vozes": vozes_instaladas()})
        else:
            self._json(404, {"erro": "só existe /falar, /vozes e /saude"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/falar":
            self._json(404, {"erro": "só existe /falar"})
            return
        try:
            tamanho = int(self.headers.get("Content-Length", 0))
            pedido = json.loads(self.rfile.read(tamanho) or b"{}")
            texto = (pedido.get("texto") or "").strip()[:MAX_CARACTERES]
            if not texto:
                self._json(400, {"erro": "falta o campo 'texto'"})
                return
            audio = sintetizar(
                texto,
                pedido.get("voz") or _opcoes.voz,
                float(pedido.get("velocidade") or _opcoes.velocidade),
            )
            self._responder(200, audio, "audio/wav")
        except Exception as erro:  # noqa: BLE001
            self._json(500, {"erro": str(erro)})


def servir(host: str, porta: int) -> None:
    servidor = ThreadingHTTPServer((host, porta), Manipulador)
    print(f"\n🔊 A voz da Lylla está de pé em http://{host}:{porta}")
    print(f"   motor: {_opcoes.motor} · voz: {_opcoes.voz} · cache: {CACHE}")
    print("   No Pi, põe isto no config/robot.local.yaml:")
    print(f"     voz:\n       servidor: \"http://{platform.node()}:{porta}/falar\"")
    print("\n   Ctrl-C para parar.\n")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n   Adeus.\n")
    finally:
        servidor.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve a voz do robô a partir do Mac.")
    parser.add_argument("--porta", type=int, default=8420)
    parser.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = visível na rede de casa")  # noqa: S104
    parser.add_argument("--voz", default="Joana")
    parser.add_argument("--velocidade", type=float, default=1.0)
    parser.add_argument("--motor", default="say", choices=sorted(MOTORES))
    parser.add_argument("--vozes", action="store_true", help="listar as vozes pt-PT deste Mac e sair")
    args = parser.parse_args()

    global _opcoes  # noqa: PLW0603
    _opcoes = args

    if args.vozes:
        encontradas = vozes_instaladas()
        print("\n".join(f"  · {v}" for v in encontradas) if encontradas
              else "  (nenhuma voz pt_PT instalada — Definições → Acessibilidade →\n"
                   "   Conteúdo falado → Voz do sistema → Gerir vozes → Português (Portugal))")
        return 0

    if args.motor == "say":
        if platform.system() != "Darwin":
            print("❌ O motor 'say' só existe no macOS. Usa --motor teste.")
            return 1
        if args.voz not in vozes_instaladas():
            print(f"❌ A voz '{args.voz}' não está instalada. As que há:")
            print("\n".join(f"  · {v}" for v in vozes_instaladas()) or "  (nenhuma)")
            return 1

    servir(args.host, args.porta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
