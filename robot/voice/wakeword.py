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

from collections import deque

import time

import numpy as np

from robot import config

TAXA = 16_000
BLOCO = 1280  # 80 ms — o tamanho que o openWakeWord espera

_modelo = None
_iniciado = False

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  O PRÉ-ROLO — o que ficou para trás quando a palavra foi ouvida          ║
# ║                                                                          ║
# ║  Entre ouvir «Olá robô» e abrir a gravação passa-se tempo: fechar um     ║
# ║  stream de áudio e abrir outro custa dezenas ou centenas de ms, e as     ║
# ║  crianças não esperam — a Lara diz «Olá robô SEGUE-ME» de enfiada.       ║
# ║  Esse princípio de frase caía no buraco entre os dois streams.           ║
# ║                                                                          ║
# ║  Como já estamos a ler blocos de 80 ms para a palavra-chave, guardá-los  ║
# ║  numa fila circular não custa nada: 1,6 s de áudio são 50 KB. Quando a   ║
# ║  palavra dispara, esses 1,6 s são a PRIMEIRA coisa que vai para o mini,  ║
# ║  que começa a transcrever antes de o microfone reabrir sequer.           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

SEGUNDOS_DE_PRE_ROLO = 1.6
_pre_rolo: deque[np.ndarray] = deque(maxlen=int(SEGUNDOS_DE_PRE_ROLO * TAXA / BLOCO))


def pre_rolo() -> np.ndarray | None:
    """O áudio dos últimos ~1,6 s antes de a palavra ter disparado.

    Devolve int16 mono a 16 kHz, ou None se não houver nada guardado (em
    simulação, ou antes da primeira escuta).
    """
    if not _pre_rolo:
        return None
    return np.concatenate(list(_pre_rolo))


def esquecer_pre_rolo() -> None:
    """Deitar fora o que está guardado — depois de o usar, ou por privacidade."""
    _pre_rolo.clear()


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


class _SomAlto:
    """O substituto do modelo: som alto em relação ao SILÊNCIO DA SALA.

    ⚠️ Era um limiar fixo (rms > 2000) e disparava uma vez por segundo assim
       que o microfone passou a dar sinal a sério — um número absoluto não
       sobrevive a uma mudança de ganho. Agora aprende o chão de ruído e exige
       que o som se aguente: um estalido não acorda ninguém.
    """

    ARRANQUE_S = 1.0      # tempo a aprender o silêncio antes de decidir
    VEZES = 4.0           # quantas vezes acima do chão conta como voz
    BLOCOS = 3            # ~240 ms seguidos, não um pico isolado

    def __init__(self) -> None:
        self.chao = float("inf")
        self.seguidos = 0
        self._inicio = time.monotonic()

    def acordou(self, amostra: np.ndarray) -> bool:
        energia = float(np.sqrt(np.mean(amostra.astype(np.float32) ** 2)))
        self.chao = min(self.chao, energia)
        if time.monotonic() - self._inicio < self.ARRANQUE_S:
            return False
        if energia > max(300.0, self.chao * self.VEZES):
            self.seguidos += 1
            return self.seguidos >= self.BLOCOS
        self.seguidos = 0
        return False


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
    som_alto = _SomAlto() if modelo is None else None

    inicio = time.monotonic()

    try:
        # O mesmo microfone e os mesmos canais do `listen` — uma regra só.
        from robot.voice.listen import abrir_microfone, canal_util

        with abrir_microfone(sd, "int16") as stream:
            while timeout is None or time.monotonic() - inicio < timeout:
                dados, _ = stream.read(BLOCO)
                amostra = canal_util(dados)
                _pre_rolo.append(amostra.copy())

                if modelo is None:
                    if som_alto.acordou(amostra):
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
