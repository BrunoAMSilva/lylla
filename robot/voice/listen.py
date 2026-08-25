"""OUVIR — grava até haver silêncio e transcreve com o faster-whisper.

Modelo: "base" com language="pt".

  · tiny  → rápido, mas erra demasiado
  · base  → transcreve a ~1-2× o tempo real no Pi 5. É o ponto certo.
  · small → mais preciso, mas MAIS LENTO QUE O TEMPO REAL. Insuportável.

Não usamos o Vosk: está parado desde 2022 e só tem modelos de português
do Brasil.
"""

from __future__ import annotations

import time

import numpy as np

from robot import config

TAXA = 16_000
_modelo = None
_iniciado = False


def _iniciar():
    global _modelo, _iniciado
    if _iniciado or config.a_simular():
        _iniciado = True
        return _modelo
    _iniciado = True
    try:
        from faster_whisper import WhisperModel

        nome = config.obter("voz.modelo_stt", "base")
        print(f"   a carregar o Whisper '{nome}'… (demora uns segundos)")
        _modelo = WhisperModel(nome, device="cpu", compute_type="int8")
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Whisper indisponível ({erro}). O robô não vai perceber o que dizes.")
        _modelo = None
    return _modelo


def gravar_ate_silencio(
    max_segundos: float = 10.0, silencio_s: float | None = None
) -> np.ndarray | None:
    """Grava enquanto houver voz e para depois de um bocado de silêncio.

    É assim que o robô sabe que a frase acabou, sem ninguém carregar num
    botão. O limiar é adaptativo: mede o ruído de fundo no primeiro terço de
    segundo e considera "voz" tudo o que estiver claramente acima disso.
    """
    if config.a_simular():
        config.sim("microfone → (simulação: nada gravado)")
        return None
    if silencio_s is None:
        silencio_s = float(config.obter("voz.silencio_para_parar_s", 1.0))

    try:
        import sounddevice as sd
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Microfone indisponível ({erro}).")
        return None

    # ⚠️ ARMADILHA QUE JÁ NOS APANHOU UMA VEZ:
    # a tentação é medir o ruído de fundo nos primeiros blocos da gravação.
    # Mas isto começa LOGO A SEGUIR à palavra-chave — a pessoa já está a
    # falar. O limiar ficaria calibrado ao nível da voz dela e nunca mais
    # disparava: o robô gravava 10 s de nada e respondia "não percebi".
    #
    # Em vez disso: um chão ABSOLUTO (que apanha a fala mesmo que ela já
    # tenha começado) combinado com o mínimo observado até agora (que se
    # adapta a uma sala barulhenta).
    CHAO_ABSOLUTO = 0.012

    bloco = 1024
    blocos: list[np.ndarray] = []
    ruido_minimo = 1.0
    ultimo_som = time.monotonic()
    inicio = time.monotonic()
    falou = False

    try:
        with sd.InputStream(
            samplerate=TAXA, channels=1, dtype="float32", blocksize=bloco
        ) as stream:
            while time.monotonic() - inicio < max_segundos:
                dados, _ = stream.read(bloco)
                amostra = dados[:, 0]
                blocos.append(amostra.copy())
                energia = float(np.sqrt(np.mean(amostra**2)))
                ruido_minimo = min(ruido_minimo, energia)

                limiar = max(CHAO_ABSOLUTO, ruido_minimo * 3.0)
                if energia > limiar:
                    ultimo_som = time.monotonic()
                    falou = True
                elif falou and time.monotonic() - ultimo_som > silencio_s:
                    break
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Falha ao gravar: {erro}")
        return None

    return np.concatenate(blocos) if falou and blocos else None


def transcrever(audio: np.ndarray) -> str:
    """Áudio → texto."""
    modelo = _iniciar()
    if modelo is None or audio is None:
        return ""
    try:
        segmentos, _ = modelo.transcribe(
            audio,
            language=config.obter("voz.idioma", "pt"),
            beam_size=1,          # 1 é bastante mais rápido e chega bem
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segmentos).strip()
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Falha a transcrever: {erro}")
        return ""


def ouvir(max_segundos: float = 10.0) -> str:
    """Grava uma frase e devolve o texto. É esta a função que se usa.

    >>> texto = ouvir()
    >>> print(texto)
    'que horas são'

    🔒 O áudio NUNCA é escrito em disco. É transcrito em memória e
       descartado no fim desta função.
    """
    if config.a_simular():
        try:
            return input("[SIM] escreve o que dirias ao robô: ").strip()
        except (EOFError, KeyboardInterrupt):
            return ""
    audio = gravar_ate_silencio(max_segundos)
    if audio is None:
        return ""
    return transcrever(audio)


def disponivel() -> bool:
    return config.a_simular() or _iniciar() is not None
