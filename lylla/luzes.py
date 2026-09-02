"""LUZES E CARA — o que o robô mostra.

    from lylla import luzes
    luzes.olhos("feliz")
    luzes.luz("azul")
"""

from __future__ import annotations

from robot.hardware import mbot2

EMOCOES = mbot2.EMOCOES
CORES = mbot2.CORES


def olhos(emocao: str = "feliz") -> None:
    """Muda a cara: feliz · piscar · a_pensar · tonto · a_dormir.

    Vai aos dois sítios ao mesmo tempo — aos 8 LEDs dos ultrassons do mBot2 e,
    quando existir, ao painel do ESP32. Quem escreve isto não tem de saber
    quantos ecrãs o robô tem.
    """
    conseguiu = mbot2.olhos(emocao)
    try:
        from robot.hardware import eyes

        if eyes.disponivel():
            eyes.expressao(emocao)
            conseguiu = True
    except Exception:  # noqa: BLE001
        pass
    print(f"  👀 olhos: {emocao}" if conseguiu
          else f"  ❓ não conheço a cara '{emocao}'. Há: {', '.join(EMOCOES)}")


def luz(cor: str = "ciano") -> None:
    """Acende as luzes do robô. `luz("apagar")` desliga-as."""
    print(f"  💡 luz: {cor}" if mbot2.luz(cor)
          else f"  ❓ não conheço a cor '{cor}'. Há: {', '.join(CORES)}, apagar")
