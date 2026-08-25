"""O BRILHO AZUL — os LEDs de acento da sonda.

O Astro tem partes que brilham a azul. Na nossa versão sonda espacial, o
brilho está onde ele teria pernas: um anel de LEDs na base, que se lê como
os propulsores de uma nave. Mais um anel no peito.

╔══════════════════════════════════════════════════════════════════════════╗
║  PORQUE NÃO USAMOS NEOPIXEL (WS2812)                                     ║
║                                                                          ║
║  Seria a escolha óbvia — LEDs RGB endereçáveis, uma cor qualquer. Mas    ║
║  os WS2812 precisam de temporização a nanossegundos, e no Raspberry Pi 5 ║
║  a biblioteca clássica (rpi_ws281x, que usava DMA e PWM) deixou de       ║
║  funcionar por causa do chip RP1 novo. É o mesmo problema do RPi.GPIO.   ║
║                                                                          ║
║  Como só queremos UMA cor — o azul do Astro — não precisamos de RGB.     ║
║  Usamos LEDs azuis comuns nos canais que sobram do PCA9685 dos motores,  ║
║  que já corre a 1 kHz. Zero chips novos, zero risco de temporização.     ║
║                                                                          ║
║  ⚠️ Tinham de ser os canais do PCA9685 dos MOTORES (1 kHz) e não os dos  ║
║     servos: a 50 Hz os LEDs tremeriam de forma visível.                  ║
╚══════════════════════════════════════════════════════════════════════════╝

⚠️ Cada grupo de LEDs precisa da SUA resistência em série. Sem ela, o LED
   dura uns segundos. Para LEDs azuis (~3,2 V) a 5 V com ~15 mA: 120 Ω.
"""

from __future__ import annotations

import atexit
import math
import threading
import time

from robot import config
from robot.hardware import pca9685

FREQ_HZ = 1000.0
_animacao: threading.Thread | None = None
_parar = threading.Event()
_nivel: dict[str, float] = {}


def _endereco() -> int:
    return int(config.obter("i2c.motores", 0x40))


def _canais() -> dict:
    """Os grupos de LEDs, definidos no config/robot.yaml."""
    return config.obter("brilho.canais", {}) or {}


def brilho(grupo: str, valor: float) -> None:
    """Acende um grupo de LEDs, de 0.0 (apagado) a 1.0 (máximo).

    >>> brilho("base", 0.6)
    """
    canais = _canais()
    if grupo not in canais:
        disponiveis = ", ".join(sorted(canais)) or "(nenhum definido)"
        raise ValueError(
            f"Não existe o grupo de luz '{grupo}'.\n"
            f"Os que existem são: {disponiveis}\n"
            f"(Estão em config/robot.yaml, secção brilho.canais)"
        )
    valor = max(0.0, min(1.0, float(valor)))
    _nivel[grupo] = valor

    if config.a_simular():
        config.sim(f"brilho {grupo} → {valor * 100:.0f}%")
        return
    if pca9685.iniciar(_endereco(), FREQ_HZ):
        pca9685.duty(_endereco(), int(canais[grupo]), valor)


def tudo(valor: float) -> None:
    for grupo in _canais():
        brilho(grupo, valor)


def apagar() -> None:
    parar_animacao()
    tudo(0.0)


# ---------------------------------------------------------------------------
# Animações — é isto que faz o robô parecer vivo mesmo parado
# ---------------------------------------------------------------------------

def _ciclo(funcao, periodo: float) -> None:
    inicio = time.monotonic()
    while not _parar.wait(0.04):
        t = (time.monotonic() - inicio) / max(periodo, 0.05)
        try:
            funcao(t)
        except Exception:  # noqa: BLE001
            break


def respirar(grupo: str = "base", periodo: float = 3.5,
             minimo: float = 0.12, maximo: float = 0.55) -> None:
    """Sobe e desce devagar, como uma respiração.

    É o comportamento por omissão quando o robô está parado. Uma luz que
    pulsa devagar lê-se como "vivo mas em repouso"; uma luz fixa lê-se como
    "aparelho ligado".
    """
    parar_animacao()

    def passo(t: float) -> None:
        # Seno deslocado para 0..1
        f = (math.sin(t * 2 * math.pi) + 1) / 2
        brilho(grupo, minimo + f * (maximo - minimo))

    _arrancar(passo, periodo)


def pulsar(grupo: str = "base", periodo: float = 0.6) -> None:
    """Pisca depressa — para quando o robô está a pensar ou a trabalhar."""
    parar_animacao()

    def passo(t: float) -> None:
        f = (math.sin(t * 2 * math.pi) + 1) / 2
        brilho(grupo, 0.15 + f * 0.85)

    _arrancar(passo, periodo)


def _arrancar(funcao, periodo: float) -> None:
    global _animacao
    _parar.clear()
    _animacao = threading.Thread(target=_ciclo, args=(funcao, periodo), daemon=True)
    _animacao.start()


def parar_animacao() -> None:
    global _animacao
    if _animacao is not None and _animacao.is_alive():
        _parar.set()
        _animacao.join(timeout=0.5)
    _animacao = None
    _parar.clear()


def nivel_atual() -> dict[str, float]:
    return dict(_nivel)


def disponivel() -> bool:
    return bool(_canais())


@atexit.register
def _apagar_ao_sair() -> None:
    try:
        apagar()
    except Exception:  # noqa: BLE001, S110
        pass
