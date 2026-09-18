"""SONS — bips curtos, feitos aqui mesmo, sem rede nenhuma.

São a resposta mais rápida que o robô tem: não dependem do mini, nem da cache,
nem de um modelo. Um bip a subir quer dizer «estou a ouvir»; um a descer quer
dizer «ouvi, vou tratar disso». Uma criança aprende isto em duas conversas.

Os sons são gerados com numpy uma vez e ficam em memória.
"""

from __future__ import annotations

from functools import lru_cache

from robot.rotinas import enriquecimento

TAXA = 22_050


def _nota(freq: float, ms: int, volume: float = 0.25):
    import numpy as np

    n = int(TAXA * ms / 1000)
    t = np.arange(n) / TAXA
    onda = np.sin(2 * np.pi * freq * t)
    # Subida e descida de 8 ms: sem isto cada nota começa com um estalido.
    rampa = min(n // 2, int(TAXA * 0.008))
    envelope = np.ones(n)
    envelope[:rampa] = np.linspace(0, 1, rampa)
    envelope[-rampa:] = np.linspace(1, 0, rampa)
    return (onda * envelope * volume).astype("float32")


@lru_cache(maxsize=None)
def som(nome: str) -> bytes:
    """O WAV de um som, pelo nome: a_ouvir · ouvi · boa · festa."""
    import numpy as np

    from robot.brain.cerebro import para_wav

    notas = {
        "a_ouvir": [(660, 70), (990, 90)],                   # a subir: fala!
        "ouvi": [(990, 60), (740, 80)],                      # a descer: ouvi
        "boa": [(1320, 110)],                                # ding
        "festa": [(523, 90), (659, 90), (784, 90), (1047, 180)],
    }[nome]
    return para_wav(np.concatenate([_nota(f, ms) for f, ms in notas]), TAXA)


def tocar(nome: str, esperar: bool = False) -> None:
    from robot.voice import speak

    speak.tocar(som(nome), esperar=esperar)


# ⚠️ O «a_ouvir» ESPERA que acabe. Toca logo antes de o microfone abrir, e um
#    bip gravado no princípio da frase contava como voz: o detetor de silêncio
#    achava que ela já tinha falado e fechava a frase 1 s depois do bip.
@enriquecimento("som.a_ouvir")
def _a_ouvir() -> None:
    tocar("a_ouvir", esperar=True)


@enriquecimento("som.ouvi")
def _ouvi() -> None:
    tocar("ouvi")


@enriquecimento("som.boa")
def _boa() -> None:
    tocar("boa")


@enriquecimento("som.festa")
def _festa() -> None:
    tocar("festa")
