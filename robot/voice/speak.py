"""FALAR — a voz da Joana, sintetizada no Mac.

A Lara ouviu às cegas as seis melhores vozes de português europeu que existem
em modelos abertos e as três do próprio macOS. Escolheu a **Joana**, e não foi
por pouco. A `tugão` do Piper — a única voz pt-PT dos modelos abertos até 2025 —
foi afinada a partir de uma voz inglesa e treinada com 1,5 h de áudio gravado
pelo browser. Ouve-se.

A Joana não é um ficheiro que se copie: é uma voz do sistema, só existe no
macOS. Por isso a síntese passou para o Mac (`scripts/servidor_voz.py`) e o Pi
só pede o WAV e toca-o.

Isto não custa independência ao robô, porque o cérebro grande (o LLM, D8) já
vivia no Mac. Sem Mac não há frases novas para dizer — e as frases que o robô
diz por iniciativa própria (bateria fraca, "não te percebi", a saudação) são um
conjunto fechado que fica **em cache no disco do Pi** depois de ser dito uma
vez. Com o Mac desligado, o robô continua a falar com a voz da Joana.

Se a frase for nova E o Mac não responder, ainda há o Piper e, em último
recurso, o espeak-ng. Feios, mas melhor do que silêncio.

⚠️ O Raspberry Pi 5 NÃO TEM tomada de auscultadores — foi removida.
   O som sai pelo reSpeaker XVF3800, por USB: a coluna liga-se à ficha JST
   da placa dele, NÃO ao Pi. Não é capricho — o cancelamento de eco do XMOS
   só funciona se o áudio que o robô toca passar pelo chip que ouve (D6).
   O `aplay` aqui em baixo usa a placa por omissão do ALSA, que é o reSpeaker
   por causa de duas linhas em /etc/asound.conf (Apêndice B do PLANO.md):
       defaults.pcm.card Array
       defaults.ctl.card Array
   Sem essas linhas o som vai para a primeira placa — o HDMI — em silêncio.
"""

from __future__ import annotations

import hashlib
import json
import queue
import subprocess
import threading
import wave
from pathlib import Path
from urllib.request import Request, urlopen

from robot import config

CACHE = config.DATA_DIR / "voz"

_voz = None
_iniciada = False
_avisado_do_mac = False
_fila: queue.Queue[str | None] = queue.Queue()
_thread: threading.Thread | None = None


# --------------------------------------------------------------- a Joana, do Mac


def _chave(texto: str, voz: str, velocidade: float) -> str:
    crua = f"say|{voz}|{velocidade:.2f}|{texto.strip()}"
    return hashlib.sha1(crua.encode("utf-8")).hexdigest()


def _pedir_ao_mac(texto: str) -> Path | None:
    """Devolve o WAV desta frase, do disco ou do Mac. None se não der.

    A cache é consultada ANTES da rede, de propósito: é o que faz o robô
    continuar a falar quando o Mac está desligado.
    """
    global _avisado_do_mac

    url = config.obter("voz.servidor")
    if not url:
        return None

    voz = config.obter("voz.voz_mac", "Joana")
    velocidade = float(config.obter("voz.velocidade_fala", 1.0) or 1.0)
    destino = CACHE / f"{_chave(texto, voz, velocidade)}.wav"
    if destino.is_file():
        return destino

    pedido = Request(
        url,
        data=json.dumps({"texto": texto, "voz": voz, "velocidade": velocidade}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(pedido, timeout=float(config.obter("voz.tempo_limite_s", 5))) as resposta:  # noqa: S310
            audio = resposta.read()
    except Exception as erro:  # noqa: BLE001
        if not _avisado_do_mac:
            _avisado_do_mac = True
            print(f"⚠️  O Mac não respondeu ({erro}). Só falo o que já está em cache.")
            print(f"    No Mac:  python scripts/servidor_voz.py")
        return None

    if not audio:
        return None

    # Gravar ao lado e mudar o nome: um WAV truncado na cache ficaria lá para
    # sempre, e o robô passava a gaguejar aquela frase todas as vezes.
    CACHE.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".parcial")
    temporario.write_bytes(audio)
    temporario.rename(destino)
    _avisado_do_mac = False
    return destino


def frases_em_cache() -> int:
    return len(list(CACHE.glob("*.wav"))) if CACHE.is_dir() else 0


# ------------------------------------------------------ o Piper, como recurso


def _iniciar():
    global _voz, _iniciada
    if _iniciada or config.a_simular():
        _iniciada = True
        return _voz
    _iniciada = True
    nome = config.obter("voz.modelo_tts")
    if not nome:
        return None
    caminho = config.MODELS_DIR / f"{nome}.onnx"
    if not caminho.exists():
        return None
    try:
        from piper import PiperVoice

        _voz = PiperVoice.load(str(caminho))
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Piper indisponível ({erro}). A tentar o espeak-ng como recurso.")
        _voz = None
    return _voz


# --------------------------------------------------------------------- falar


def _reproduzir_wav(caminho: str | Path) -> None:
    try:
        subprocess.run(
            ["aplay", "-q", str(caminho)], check=False, timeout=30,
            stderr=subprocess.DEVNULL,
        )
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Não consegui reproduzir o som: {erro}")


def _falar_agora(texto: str) -> None:
    """Sintetiza e reproduz. Bloqueia até acabar de falar."""
    if not texto or not texto.strip():
        return

    if config.a_simular():
        config.sim(f'falar → "{texto}"')
        return

    # 1 · a Joana: da cache do Pi, ou do Mac (que também tem cache).
    caminho = _pedir_ao_mac(texto)
    if caminho is not None:
        _reproduzir_wav(caminho)
        return

    # 2 · o Piper, se estiver instalado e configurado.
    voz = _iniciar()
    destino = "/tmp/robo_fala.wav"
    if voz is not None:
        try:
            with wave.open(destino, "wb") as f:
                voz.synthesize_wav(texto, f)
            _reproduzir_wav(destino)
            return
        except Exception as erro:  # noqa: BLE001
            print(f"⚠️  Piper falhou ({erro}). A usar o espeak-ng.")

    # 3 · som robótico dos anos 90, mas melhor que silêncio.
    try:
        subprocess.run(
            ["espeak-ng", "-v", "pt", "-s", "150", texto],
            check=False, timeout=30, stderr=subprocess.DEVNULL,
        )
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Sem voz nenhuma disponível: {erro}")
        print(f'    O robô queria dizer: "{texto}"')


def _trabalhador() -> None:
    while True:
        texto = _fila.get()
        if texto is None:
            break
        try:
            _falar_agora(texto)
        finally:
            _fila.task_done()


def falar(texto: str, esperar: bool = True) -> None:
    """Diz uma frase em voz alta.

    >>> falar("Olá, Lara!")

    Com esperar=False a frase entra numa fila e o programa continua — útil
    para o robô falar enquanto anda.
    """
    global _thread
    if esperar:
        _falar_agora(texto)
        return
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_trabalhador, daemon=True)
        _thread.start()
    _fila.put(texto)


def esperar_acabar() -> None:
    """Espera que a fila de fala esvazie."""
    _fila.join()


def disponivel() -> bool:
    if config.a_simular():
        return True
    if config.obter("voz.servidor") or frases_em_cache():
        return True
    return _iniciar() is not None
