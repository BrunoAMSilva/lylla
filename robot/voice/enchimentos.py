"""OS «HMM» — o que o robô diz enquanto o mini pensa.

Entre a Lara acabar a frase e a primeira palavra da resposta passa um segundo
ou mais (vários, quando a pergunta pede uma explicação). Um robô calado esse
tempo todo parece avariado; um que diz «hmm…» ou «let me check» parece estar a
pensar — e as crianças acham-lhe graça.

⚠️ SÓ SE TOCA O QUE JÁ ESTÁ EM CACHE. Um «hmm» que tivesse de ir ao mini ser
   sintetizado chegava depois da resposta. Por isso `preparar()` pede-os todos
   no arranque, numa thread, e `dizer()` nunca vai à rede: se ainda não houver
   nenhum pronto, toca o bip e pronto.
"""

from __future__ import annotations

import random
import threading

from robot import config
from robot.rotinas import enriquecimento
from robot.voice import frases

_prontos: set[str] = set()
_ultimo: str | None = None


def preparar() -> None:
    """Pede ao mini os WAV de todos os «hmm», em fundo. Chamar no arranque."""
    from robot.voice import speak

    def _trabalho() -> None:
        for tipo in ("curtos", "longos"):
            for texto in frases.enchimentos(tipo):
                try:
                    if speak.em_cache(texto):
                        _prontos.add(texto)
                except Exception:  # noqa: BLE001
                    return          # sem mini: tenta-se no próximo arranque
    threading.Thread(target=_trabalho, daemon=True, name="enchimentos").start()


def escolher(tipo: str = "curtos") -> str | None:
    """Um ao calhas, nunca o mesmo duas vezes seguidas. None se nenhum estiver pronto."""
    global _ultimo
    opcoes = [t for t in frases.enchimentos(tipo) if t in _prontos or config.a_simular()]
    if len(opcoes) > 1 and _ultimo in opcoes:
        opcoes.remove(_ultimo)
    if not opcoes:
        return None
    _ultimo = random.choice(opcoes)
    return _ultimo


def dizer(tipo: str = "curtos") -> None:
    """Diz um «hmm» sem esperar — entra na fila da voz antes da resposta."""
    from robot.voice import speak

    texto = escolher(tipo)
    if texto is not None:
        speak.falar(texto, esperar=False)


@enriquecimento("voz.hmm")
def _hmm() -> None:
    dizer("curtos")


@enriquecimento("voz.deixa_pensar")
def _deixa_pensar() -> None:
    dizer("longos")
