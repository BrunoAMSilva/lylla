"""FALAR — texto para áudio, no mac mini.

Substitui o scripts/servidor_voz.py (que só sabia o `say`). A ideia é a mesma
e continua a valer: um motor é uma função (texto, voz, velocidade) → bytes de
um WAV, e o Pi guarda o WAV em cache para continuar a falar com o mini
desligado. Ver robot/voice/speak.py.

Motores:

    piper   → um modelo .onnx em models/ (a GLaDOS, a tugão, a nossa voz
              quando a gravarmos). Corre em CPU e é rápido: ~0,1 s por frase.
    say     → as vozes do macOS (Joana, Catarina, Joaquim). Só no Mac.
    teste   → um apito. Para os testes correrem em qualquer máquina.

A voz pede-se pelo nome. Sem prefixo é do motor por omissão; com prefixo
escolhe-se o motor: "glados" · "piper:glados" · "say:Joana".
"""

from __future__ import annotations

import array
import hashlib
import io
import math
import os
import platform
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

from cerebro import config

MAX_CARACTERES = 1000
PALAVRAS_POR_MINUTO = 180  # o ritmo natural do `say`


class VozIndisponivel(RuntimeError):
    pass


# ---------------------------------------------------------------- os motores


def motor_teste(texto: str, voz: str, velocidade: float) -> bytes:
    """Um apito com a duração da frase. Serve para ver o caminho todo a andar."""
    taxa = 22050
    duracao = min(0.05 * max(len(texto), 1), 3.0) / max(velocidade, 0.1)
    amostras = array.array(
        "h",
        (int(12000 * math.sin(2 * math.pi * 440 * i / taxa)) for i in range(int(taxa * duracao))),
    )
    return _wav(amostras.tobytes(), taxa)


def motor_say(texto: str, voz: str, velocidade: float) -> bytes:
    if platform.system() != "Darwin" or not shutil.which("say"):
        raise VozIndisponivel("o motor 'say' só existe no macOS")
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        subprocess.run(
            [
                "say", "-v", voz or "Joana",
                "-r", str(int(PALAVRAS_POR_MINUTO * velocidade)),
                "-o", tmp.name, "--file-format=WAVE", "--data-format=LEI16@22050",
                texto,
            ],
            check=True, capture_output=True, timeout=30,
        )
        return Path(tmp.name).read_bytes()


_piper_vozes: dict[str, object] = {}
_piper_lock = threading.Lock()


def _piper_carregar(nome: str):
    with _piper_lock:
        if nome in _piper_vozes:
            return _piper_vozes[nome]
        caminho = config.MODELS_DIR / f"{nome}.onnx"
        if not caminho.exists():
            raise VozIndisponivel(
                f"não há models/{nome}.onnx — corre `python scripts/download_models.py`"
            )
        try:
            from piper import PiperVoice
        except ImportError as erro:
            raise VozIndisponivel(f"falta o piper-tts neste Python ({erro})") from erro
        voz = PiperVoice.load(str(caminho))
        _piper_vozes[nome] = voz
        return voz


def motor_piper(texto: str, voz: str, velocidade: float) -> bytes:
    modelo = _piper_carregar(voz or "glados")
    buffer = io.BytesIO()
    with _piper_lock, wave.open(buffer, "wb") as f:
        # A velocidade no Piper é o inverso: length_scale 0.8 fala mais depressa.
        cfg = None
        try:
            try:
                from piper import SynthesisConfig
            except ImportError:
                from piper.config import SynthesisConfig
            cfg = SynthesisConfig(length_scale=1.0 / max(velocidade, 0.2))
        except Exception:  # noqa: BLE001 — versões antigas do piper não têm isto
            cfg = None
        if cfg is not None:
            modelo.synthesize_wav(texto, f, syn_config=cfg)
        else:
            modelo.synthesize_wav(texto, f)
    return buffer.getvalue()


def _wav(pcm16: bytes, taxa: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm16)
    return buffer.getvalue()


MOTORES = {"piper": motor_piper, "say": motor_say, "teste": motor_teste}


# ------------------------------------------------------------------ a fachada


class Voz:
    def __init__(self, motor: str | None = None, cache: str | Path | None = None) -> None:
        self.motor_omissao = motor or str(config.obter("falar.motor", "piper"))
        if self.motor_omissao not in MOTORES:
            raise ValueError(f"motor de TTS desconhecido: {self.motor_omissao} (há {sorted(MOTORES)})")
        self.voz_omissao = str(config.obter("falar.voz", "glados"))
        self.velocidade_omissao = float(config.obter("falar.velocidade", 1.0) or 1.0)
        self.cache = Path(cache or config.obter("falar.cache", "~/.cache/lylla-voz")).expanduser()

    def resolver(self, voz: str | None) -> tuple[str, str]:
        """"say:Joana" → ("say", "Joana") · "glados" → (motor por omissão, "glados")."""
        nome = (voz or self.voz_omissao).strip()
        if ":" in nome:
            motor, _, nome = nome.partition(":")
            if motor not in MOTORES:
                raise VozIndisponivel(f"não há o motor de voz '{motor}'")
            return motor, nome
        return self.motor_omissao, nome

    def chave(self, texto: str, voz: str | None, velocidade: float | None) -> str:
        motor, nome = self.resolver(voz)
        v = float(velocidade or self.velocidade_omissao)
        crua = f"{motor}|{nome}|{v:.2f}|{texto.strip()}"
        return hashlib.sha1(crua.encode("utf-8")).hexdigest()

    def sintetizar(self, texto: str, voz: str | None = None, velocidade: float | None = None) -> tuple[bytes, bool]:
        """→ (bytes do WAV, veio_da_cache)."""
        texto = (texto or "").strip()[:MAX_CARACTERES]
        if not texto:
            raise ValueError("não há texto para dizer")
        motor, nome = self.resolver(voz)
        v = float(velocidade or self.velocidade_omissao)

        self.cache.mkdir(parents=True, exist_ok=True)
        ficheiro = self.cache / f"{self.chave(texto, voz, velocidade)}.wav"
        if ficheiro.is_file():
            return ficheiro.read_bytes(), True

        audio = MOTORES[motor](texto, nome, v)

        # Escrever ao lado e mudar o nome: se isto morrer a meio, não fica um
        # ficheiro truncado na cache a envenenar todas as vezes seguintes.
        # O nome temporário é único por chamada (os.getpid + um contador do
        # tempfile): duas sínteses da MESMA frase ao mesmo tempo davam duas
        # escritas no mesmo ".parcial" e um FileNotFoundError no rename.
        descritor, temporario = tempfile.mkstemp(dir=self.cache, suffix=".parcial")
        try:
            with os.fdopen(descritor, "wb") as f:
                f.write(audio)
            os.replace(temporario, ficheiro)
        except Exception:
            Path(temporario).unlink(missing_ok=True)
            raise
        return audio, False

    def aquecer(self) -> None:
        motor, nome = self.resolver(None)
        if motor == "piper":
            _piper_carregar(nome)

    def em_cache(self) -> int:
        return len(list(self.cache.glob("*.wav"))) if self.cache.is_dir() else 0

    def descricao(self) -> dict:
        return {"motor": self.motor_omissao, "voz": self.voz_omissao, "em_cache": self.em_cache()}
