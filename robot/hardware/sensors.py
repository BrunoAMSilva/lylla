"""OS SENSORES — distância à frente e deteção de precipício.

⚠️ O sensor ultrassónico TEM de ser o modelo HC-SR04P (3,3–5 V).
   O HC-SR04 normal devolve 5 V no pino Echo e DESTRÓI o GPIO do Raspberry Pi,
   que trabalha a 3,3 V. São €1,30 de diferença e um Pi de €95 de risco.

Usa-se gpiozero com o backend lgpio — a forma correta no Pi 5.
NUNCA importar RPi.GPIO.
"""

from __future__ import annotations

import atexit

from robot import config

_ultrassons = None
_precipicio: list = []
_iniciado = False


def _iniciar() -> None:
    global _ultrassons, _precipicio, _iniciado
    if _iniciado or config.a_simular():
        _iniciado = True
        return
    _iniciado = True

    # ⚠️ COM O mBot2 ESTES SENSORES NÃO EXISTEM NO PI.
    #    O ultrassónico e o sensor de chão vivem no mBot2 e chegam por USB
    #    (robot/hardware/mbot2.py). Criar aqui um DistanceSensor em pinos onde
    #    não há nada ligado não dá erro — dá PIOR: o `.distance` do gpiozero
    #    espera pela fila de ecos e, sem eco, BLOQUEIA PARA SEMPRE. Foi isso
    #    que prendeu o `contexto.montar()` e impediu o cérebro de responder.
    if str(config.obter("motores.ligacao", "mbot2")) == "mbot2":
        _ultrassons = None
        _precipicio = []
        return

    try:
        from gpiozero import DigitalInputDevice, DistanceSensor

        _ultrassons = DistanceSensor(
            echo=int(config.obter("pinos.ultrassons_echo", 24)),
            trigger=int(config.obter("pinos.ultrassons_trigger", 23)),
            max_distance=2.0,
            queue_len=3,
        )
        _precipicio = [
            DigitalInputDevice(int(config.obter(f"pinos.precipicio_{lado}", omissao)))
            for lado, omissao in (("esq", 17), ("centro", 27), ("dir", 22))
        ]
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Sensores indisponíveis ({erro}). O robô vai andar às cegas.")
        _ultrassons = None
        _precipicio = []


def distancia_cm() -> float:
    """Distância ao obstáculo mais próximo à frente, em centímetros.

    Devolve 999 se não houver sensor — é o valor seguro: 'caminho livre'
    seria perigoso, mas 'obstáculo à frente' bloquearia o robô para sempre.
    Um robô sem sensor deve andar devagar, não ficar parado.
    """
    _iniciar()
    if config.a_simular():
        return 100.0
    if _ultrassons is None:
        return 999.0
    try:
        return round(_ultrassons.distance * 100, 1)
    except Exception:  # noqa: BLE001
        return 999.0


def sem_sensor() -> bool:
    """True se não houver sensor de distância a funcionar."""
    return not config.a_simular() and _ultrassons is None


def caminho_livre() -> bool:
    """True se não houver nada demasiado perto à frente."""
    return distancia_cm() > float(config.obter("seguranca.distancia_min_cm", 25))


def deve_abrandar() -> bool:
    """True se convier ir devagar.

    Sem sensor, devolve SEMPRE True: um robô cego deve andar devagar. (Já
    não bloqueamos o caminho_livre() nesse caso, senão o robô nunca andaria.)
    """
    _iniciar()
    if sem_sensor():
        return True
    return distancia_cm() < float(config.obter("seguranca.distancia_aviso_cm", 40))


def ha_precipicio() -> bool:
    """True se algum dos 3 sensores de baixo deixar de ver o chão.

    É isto que impede o robô de cair da mesa.
    """
    _iniciar()
    if config.a_simular() or not _precipicio:
        return False
    if not config.obter("seguranca.verificar_precipicio", True):
        return False
    try:
        # Os TCRT5000 dão sinal ALTO quando NÃO veem chão (sem reflexão)
        return any(s.value == 1 for s in _precipicio)
    except Exception:  # noqa: BLE001
        return False


def estado() -> dict:
    """Tudo de uma vez — útil para depurar e para o check_health."""
    return {
        "distancia_cm": distancia_cm(),
        "caminho_livre": caminho_livre(),
        "precipicio": ha_precipicio(),
    }


@atexit.register
def _fechar() -> None:
    for dispositivo in [_ultrassons, *_precipicio]:
        try:
            if dispositivo is not None:
                dispositivo.close()
        except Exception:  # noqa: BLE001, S110
            pass
