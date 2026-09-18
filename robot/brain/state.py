"""A MÁQUINA DE ESTADOS.

Sem isto, o comportamento do robô vira um emaranhado de `if`s que ninguém
consegue mudar sem partir outra coisa. Com isto, cada situação tem um sítio
óbvio onde vive.

    A_DORMIR ──ouve a palavra──► ATENTO
       ▲                            │
       │                       vê / ouve alguém
       │                            ▼
       └──5 min sem nada──── A_OUVIR ──► A_PENSAR ──► A_FALAR ──► A_AGIR
                                                                    │
                                                            ATENTO ◄┘
"""

from __future__ import annotations

import time
from enum import Enum


class Estado(Enum):
    A_DORMIR = "a_dormir"
    ATENTO = "atento"
    A_OUVIR = "a_ouvir"
    A_PENSAR = "a_pensar"
    A_FALAR = "a_falar"
    A_AGIR = "a_agir"
    A_PASSEAR = "a_passear"


# Que cara faz o robô em cada estado
OLHOS_POR_ESTADO = {
    Estado.A_DORMIR: "a_dormir",
    Estado.ATENTO: "neutro",
    Estado.A_OUVIR: "surpreso",
    Estado.A_PENSAR: "a_pensar",
    Estado.A_FALAR: "feliz",
    Estado.A_AGIR: "feliz",
    Estado.A_PASSEAR: "a_procurar",
}

SEGUNDOS_ATE_ADORMECER = 300  # 5 minutos


class Maquina:
    def __init__(self) -> None:
        self.estado = Estado.A_DORMIR
        self.desde = time.monotonic()
        self.ultima_interacao = time.monotonic()
        self.pessoa: str | None = None

    def mudar(self, novo: Estado, olhos: bool = True) -> None:
        """Muda de estado. `olhos=False` quando alguém já escolheu a cara — por
        exemplo o cérebro, que manda a expressão antes da primeira frase."""
        if novo is self.estado:
            return
        from robot.hardware import eyes

        anterior = self.estado
        self.estado = novo
        self.desde = time.monotonic()

        if novo is not Estado.A_DORMIR:
            self.ultima_interacao = time.monotonic()

        # Animações nas transições que se notam
        if anterior is Estado.A_DORMIR and novo is not Estado.A_DORMIR:
            eyes.animar("acordar")
        elif novo is Estado.A_DORMIR:
            eyes.animar("adormecer")
        elif olhos:
            eyes.expressao(OLHOS_POR_ESTADO.get(novo, "neutro"))

    @property
    def ha_quanto_tempo(self) -> float:
        return time.monotonic() - self.desde

    @property
    def tempo_sem_interacao(self) -> float:
        return time.monotonic() - self.ultima_interacao

    def registar_presenca(self) -> None:
        """Alguém está à frente do robô.

        ⚠️ Conta como interação para efeito de adormecer, mas NÃO muda de
           estado. Um robô de secretária que adormece com a Lara sentada à
           frente dele parece avariado; um que acorda e começa a falar por
           ela estar ali, parece intrusivo. Fica acordado e calado.
        """
        self.ultima_interacao = time.monotonic()

    def deve_adormecer(self) -> bool:
        return (
            self.estado is not Estado.A_DORMIR
            and self.tempo_sem_interacao > SEGUNDOS_ATE_ADORMECER
        )

    def __repr__(self) -> str:
        return f"<{self.estado.value} há {self.ha_quanto_tempo:.0f}s>"
