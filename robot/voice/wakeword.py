"""A PALAVRA MÁGICA — "Olá robô".

Porquê ter uma palavra de ativação em vez de transcrever tudo:

  1. EFICIÊNCIA — este modelo tem 1-5 MB e gasta menos de 5% de um core.
     Ter o Whisper sempre a correr consumiria o Pi inteiro.
  2. PRIVACIDADE — o robô não está a perceber o que se diz em casa. Está
     só à espera de um som específico. É uma diferença que interessa.

Como treinar a palavra em 2026:
  · livekit-wakeword (abril 2026) — gera as amostras de treino
    sinteticamente, inclusive com a própria voz do Piper. Um comando.
    Exporta .onnx compatível com o openWakeWord.
  · O openWakeWord continua a funcionar mas está parado desde fev/2024.
  · O Snowboy morreu em 2020. O Porcupine é pago acima de 3 utilizadores.
"""

from __future__ import annotations

import numpy as np

from robot import config

TAXA = 16_000
BLOCO = 1280  # 80 ms — o tamanho que o openWakeWord espera

_modelo = None
_iniciado = False


def _iniciar():
    global _modelo, _iniciado
    if _iniciado or config.a_simular():
        _iniciado = True
        return _modelo
    _iniciado = True
    nome = config.obter("voz.palavra_chave", "ola_robo")
    caminho = config.MODELS_DIR / f"{nome}.onnx"
    try:
        from openwakeword.model import Model

        if caminho.exists():
            _modelo = Model(wakeword_models=[str(caminho)], inference_framework="onnx")
        else:
            print(
                f"⚠️  Ainda não existe o modelo da palavra '{nome}'.\n"
                f"    Treina-o na fase 7 (ver PLANO.md) e põe o .onnx em models/.\n"
                f"    Por agora, o robô responde a qualquer som alto."
            )
            _modelo = None
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Palavra-chave indisponível ({erro}).")
        _modelo = None
    return _modelo


def esperar_pela_palavra(timeout: float | None = None) -> bool:
    """Fica à espera de ouvir a palavra mágica. True quando a ouvir.

    Com o modelo ainda por treinar, usa um simples detetor de som alto —
    assim a fase 8 pode avançar antes de a fase 7 estar perfeita.
    """
    if config.a_simular():
        try:
            input('[SIM] carrega Enter para dizer "Olá robô": ')
            return True
        except (EOFError, KeyboardInterrupt):
            return False

    try:
        import sounddevice as sd
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Microfone indisponível ({erro}).")
        return False

    modelo = _iniciar()
    limiar = float(config.obter("voz.limiar_palavra_chave", 0.6))
    import time

    inicio = time.monotonic()

    try:
        with sd.InputStream(
            samplerate=TAXA, channels=1, dtype="int16", blocksize=BLOCO
        ) as stream:
            while timeout is None or time.monotonic() - inicio < timeout:
                dados, _ = stream.read(BLOCO)
                amostra = dados[:, 0]

                if modelo is None:
                    # Substituto: qualquer som claramente alto serve.
                    if float(np.sqrt(np.mean(amostra.astype(np.float32) ** 2))) > 2000:
                        return True
                    continue

                resultado = modelo.predict(amostra)
                if any(v > limiar for v in resultado.values()):
                    modelo.reset()
                    return True
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Falha a ouvir a palavra-chave: {erro}")
        return False
    return False


def disponivel() -> bool:
    return config.a_simular() or _iniciar() is not None
