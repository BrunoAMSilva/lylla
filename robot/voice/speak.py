"""FALAR — duas vozes, um interruptor.

`voz.motor` decide quem fala primeiro:

  · "mac"   → sintetizada no mac mini (`cerebro/falar.py`, endpoint /v1/falar)
              e guardada em cache no Pi. É lá que estão as vozes todas.
  · "piper" → um modelo .onnx no próprio Pi, sem rede nenhuma. É o caso da voz
              da GLaDOS, que é um Piper de 63 MB e corre a RTF ~0,2 — a mesma
              arquitetura da `tugão`, mas treinada com horas de estúdio.

⚠️ No caminho normal (main.py → /v1/turno) o áudio já vem com a resposta, e
   quem o toca é `tocar()`, aqui em baixo. Estas funções servem as frases que
   o robô diz por iniciativa própria — a saudação, a bateria fraca, o "não
   percebi" — que são as que têm de continuar a sair com o mini desligado.

O que falhar cai para o outro, e em último recurso para o espeak-ng.

⚠️ A voz da GLaDOS tem fonemizador `en-us`. Texto português passado por ela sai
   estropiado — por isso o modo inglês é um interruptor de projeto (`lingua`
   no robot.yaml), não só uma troca de ficheiro. Ver robot/brain/personalidade.py.

--- o resto da história ---

FALAR — a voz da Joana, sintetizada no Mac.

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
   O som sai por I2S (amplificador MAX98357A), USB ou HDMI.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from urllib.request import Request, urlopen

from robot import config

CACHE = config.DATA_DIR / "voz"

_voz = None
_iniciada = False
_avisado_do_mac = False
_fila: queue.Queue[str | bytes | None] = queue.Queue()
_thread: threading.Thread | None = None


# --------------------------------------------------------------- a Joana, do Mac


def _chave(texto: str, voz: str, velocidade: float) -> str:
    crua = f"say|{voz}|{velocidade:.2f}|{texto.strip()}"
    return hashlib.sha1(crua.encode("utf-8")).hexdigest()


def _url_do_servidor() -> str | None:
    """Onde é que se pede um WAV.

    `voz.servidor` continua a mandar (é o que o robot.local.yaml de casa tem
    e o que os testes usam); sem ele, monta-se a partir do `cerebro.url`, que
    é o endereço do mini. Um endereço só, num sítio só.
    """
    url = config.obter("voz.servidor")
    if url:
        return str(url)
    base = config.obter("cerebro.url")
    return f"{str(base).rstrip('/')}/v1/falar" if base else None


def _pedir_ao_mac(texto: str) -> Path | None:
    """Devolve o WAV desta frase, do disco ou do Mac. None se não der.

    A cache é consultada ANTES da rede, de propósito: é o que faz o robô
    continuar a falar quando o Mac está desligado.
    """
    global _avisado_do_mac

    url = _url_do_servidor()
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
            print(f"⚠️  O mini não respondeu ({erro}). Só falo o que já está em cache.")
            print("    No mini:  python -m cerebro.servidor")
        return None

    if not audio:
        return None

    # Gravar ao lado e mudar o nome: um WAV truncado na cache ficaria lá para
    # sempre, e o robô passava a gaguejar aquela frase todas as vezes.
    # Nome temporário único: duas threads a pedir a mesma frase ao mesmo tempo
    # escreviam as duas no mesmo ".parcial", e a segunda não encontrava nada
    # para mudar de nome.
    CACHE.mkdir(parents=True, exist_ok=True)
    descritor, temporario = tempfile.mkstemp(dir=CACHE, suffix=".parcial")
    with os.fdopen(descritor, "wb") as f:
        f.write(audio)
    os.replace(temporario, destino)
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
    except ImportError as erro:
        # Não é "o Piper não funciona" — é "este Python não tem o Piper".
        # Dizer QUAL Python está a correr poupa a meia hora que este projeto já
        # perdeu três vezes com o mesmo engano.
        import sys

        print(f"⚠️  {erro}")
        print(f"    O Python que está a correr isto é: {sys.executable}")
        if sys.prefix == sys.base_prefix:
            print("    E não é um venv. O projeto quer o seu:")
            print("      python3 -m venv --system-site-packages .venv")
            print("      .venv/bin/python -m pip install -r requirements.txt")
            print("      .venv/bin/python scripts/test_voz.py")
        else:
            print(f"    Falta o piper-tts nesse venv:  {sys.executable} -m pip install piper-tts")
        _voz = None
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Piper indisponível ({erro}).")
        _voz = None
    return _voz


# --------------------------------------------------------------------- falar


# O `aplay` é do Linux e é o que o Pi usa. Mas o mesmo código corre no Mac
# durante o desenvolvimento, e lá o comando chama-se `afplay` — sem isto o robô
# sintetizava a frase e ficava calado, sem erro nenhum, que é a pior maneira de
# uma coisa falhar.
LEITORES = (["aplay", "-q"], ["afplay"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"])


def _reproduzir_wav(caminho: str | Path) -> None:
    for comando in LEITORES:
        if shutil.which(comando[0]) is None:
            continue
        try:
            subprocess.run([*comando, str(caminho)], check=False, timeout=30,
                           stderr=subprocess.DEVNULL)
            return
        except Exception as erro:  # noqa: BLE001
            print(f"⚠️  O {comando[0]} falhou: {erro}")
    print(f"⚠️  Não há leitor de áudio (aplay, afplay ou ffplay). O som está em {caminho}")


def _falar_agora(texto: str) -> None:
    """Sintetiza e reproduz. Bloqueia até acabar de falar."""
    if not texto or not texto.strip():
        return

    if config.a_simular():
        config.sim(f'falar → "{texto}"')
        return

    # A ordem depende do motor escolhido. Com `voz.motor: piper` o Pi fala
    # sozinho, sem rede nenhuma — é o caso da voz da GLaDOS, que é um modelo
    # Piper de 63 MB e corre no próprio robô a RTF ~0,2.
    if config.obter("voz.motor", "mac") == "piper":
        ordem = ("piper", "mac")
    else:
        ordem = ("mac", "piper")

    for motor in ordem:
        if motor == "mac":
            caminho = _pedir_ao_mac(texto)
            if caminho is not None:
                _reproduzir_wav(caminho)
                return
        else:
            voz = _iniciar()
            if voz is None:
                continue
            destino = "/tmp/robo_fala.wav"
            try:
                with wave.open(destino, "wb") as f:
                    voz.synthesize_wav(texto, f)
                _reproduzir_wav(destino)
                return
            except Exception as erro:  # noqa: BLE001
                print(f"⚠️  Piper falhou ({erro}).")

    # Último recurso: som robótico dos anos 90, mas melhor que silêncio.
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
        item = _fila.get()
        if item is None:
            break
        try:
            if isinstance(item, bytes):
                _tocar_agora(item)
            else:
                _falar_agora(item)
        finally:
            _fila.task_done()


def _tocar_agora(dados: bytes) -> None:
    """Toca um WAV que já veio pronto (do /v1/turno). Bloqueia até ao fim.

    ⚠️ Ficheiro temporário com nome único, e apagado no fim. Um nome derivado
       do conteúdo parecia mais esperto — poupava escritas — mas deixava um
       WAV por frase no /tmp do Pi, para sempre. O cartão SD do robô não é
       sítio para uma cache que ninguém limpa; a cache das frases é a de
       `data/voz/`, e essa é intencional.
    """
    if config.a_simular():
        config.sim(f"tocar → {len(dados)} bytes de áudio")
        return
    ficheiro = None
    try:
        with tempfile.NamedTemporaryFile(prefix="lylla_", suffix=".wav", delete=False) as tmp:
            tmp.write(dados)
            ficheiro = Path(tmp.name)
        _reproduzir_wav(ficheiro)
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Não consegui tocar o áudio: {erro}")
    finally:
        if ficheiro is not None:
            ficheiro.unlink(missing_ok=True)


def tocar(dados: bytes, esperar: bool = True) -> None:
    """Toca áudio que veio do cérebro, já sintetizado.

    Com esperar=False entra na MESMA fila das frases, o que é o que garante
    que a segunda frase só toca depois de a primeira acabar — mesmo tendo
    chegado enquanto a primeira ainda tocava.
    """
    global _thread
    if esperar:
        esperar_acabar()
        _tocar_agora(dados)
        return
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_trabalhador, daemon=True)
        _thread.start()
    _fila.put(dados)


def falar(texto: str, esperar: bool = True) -> None:
    """Diz uma frase em voz alta.

    >>> falar("Olá, Lara!")

    Com esperar=False a frase entra numa fila e o programa continua — útil
    para o robô falar enquanto anda.
    """
    global _thread
    if esperar:
        esperar_acabar()      # ⚠️ ver a nota em esperar_acabar()
        _falar_agora(texto)
        return
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_trabalhador, daemon=True)
        _thread.start()
    _fila.put(texto)


def esperar_acabar() -> None:
    """Espera que a fila de fala esvazie.

    ⚠️ É por isto que `falar(…, esperar=True)` começa por chamar isto. Sem
       esse cuidado, uma frase "urgente" era sintetizada e tocada na thread de
       quem a pediu, POR CIMA do que a fila ainda estava a dizer — duas vozes
       ao mesmo tempo, e nenhuma delas percebível. Esperar significa esperar
       pela vez, não passar à frente.
    """
    _fila.join()


def disponivel() -> bool:
    if config.a_simular():
        return True
    if config.obter("voz.motor", "mac") == "piper":
        return _iniciar() is not None or bool(_url_do_servidor())
    if _url_do_servidor() or frases_em_cache():
        return True
    return _iniciar() is not None
