"""Driver do PCA9685 — o chip que gera PWM por I2C.

╔══════════════════════════════════════════════════════════════════════════╗
║  PORQUÊ I2C E NÃO GPIO DIRETO                                            ║
║                                                                          ║
║  A biblioteca RPi.GPIO NÃO FUNCIONA no Raspberry Pi 5. O Pi 5 trouxe um  ║
║  chip de entradas/saídas novo (o RP1) e metade dos tutoriais de robôs    ║
║  que estão na Internet vão simplesmente rebentar. E o `pigpio`, que      ║
║  fazia PWM preciso por DMA, também não funciona.                        ║
║                                                                          ║
║  O I2C é imune ao problema: é igual no Pi 4 e no Pi 5.                  ║
╚══════════════════════════════════════════════════════════════════════════╝

Temos DOIS destes chips, e a razão é importante:

    0x40 → a  1000 Hz → motores    (via TB6612FNG)
    0x41 → a    50 Hz → servos     (os braços)

O PCA9685 só tem UMA frequência para os seus 16 canais. Servos querem 50 Hz;
motores a 50 Hz rosnam e não controlam bem a baixa velocidade. Por isso são
dois chips de €8 em vez de um.
"""

from __future__ import annotations

import time

from robot import config

# Registos do PCA9685
_MODO1 = 0x00
_PRESCALE = 0xFE
_LED0_ON_L = 0x06

_bus = None
_iniciados: dict[int, bool] = {}

# ⚠️ Um endereço que não responde NÃO se volta a tentar. O `iniciar()` é
#    chamado do ciclo principal (~10x por segundo) e, com a placa fora, o
#    aviso saía dez vezes por segundo e enterrava tudo o resto no terminal.
#    Uma placa I2C não aparece sozinha a meio de uma execução: ou está ligada
#    no arranque, ou fica para a próxima.
_ausentes: set[int] = set()
_oe = None
_oe_tentado = False


def _ligar_oe():
    """Activa o pino OE (Output Enable) dos PCA9685.

    ╔══════════════════════════════════════════════════════════════════════╗
    ║  ISTO É A REDE DE SEGURANÇA MAIS IMPORTANTE DO ROBÔ TODO.            ║
    ║                                                                      ║
    ║  O PCA9685 é *latching*: uma vez escrito um valor, o chip continua a ║
    ║  gerar aquele PWM PARA SEMPRE, mesmo que o Raspberry Pi morra.       ║
    ║  Sem isto, um `kill -9` deixaria os motores a rodar até a bateria    ║
    ║  acabar — com o robô a atravessar a casa e ninguém a poder pará-lo.  ║
    ║                                                                      ║
    ║  O OE é activo-baixo e tem uma resistência de pull-up para 3,3 V:    ║
    ║    · Pi vivo   → GPIO em LOW  → saídas ligadas                       ║
    ║    · Pi morto  → GPIO em alta impedância → pull-up puxa para HIGH    ║
    ║                  → saídas DESLIGADAS, motores e servos param         ║
    ║                                                                      ║
    ║  Ou seja: a falha segura é o estado natural. Não depende de código. ║
    ╚══════════════════════════════════════════════════════════════════════╝
    """
    global _oe, _oe_tentado
    if _oe_tentado or config.a_simular():
        _oe_tentado = True
        return _oe
    _oe_tentado = True
    pino = config.obter("pinos.pca_oe")
    if pino is None:
        return None
    try:
        from gpiozero import DigitalOutputDevice

        _oe = DigitalOutputDevice(int(pino), active_high=False, initial_value=True)
    except Exception as erro:  # noqa: BLE001
        print(
            f"⚠️  Não consegui activar o OE dos PCA9685 no GPIO {pino}: {erro}\n"
            f"    O robô funciona, mas perde a paragem automática em caso de crash."
        )
        _oe = None
    return _oe


def desligar_saidas() -> None:
    """Corta as saídas de TODOS os PCA9685 de uma vez, por hardware."""
    if _oe is not None:
        try:
            _oe.off()
        except Exception:  # noqa: BLE001, S110
            pass


def _abrir_bus():
    global _bus
    if _bus is not None or config.a_simular():
        return _bus
    try:
        import smbus2

        _bus = smbus2.SMBus(1)
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  I2C indisponível ({erro}).")
        _bus = None
    return _bus


def iniciar(endereco: int, frequencia_hz: float) -> bool:
    """Prepara um PCA9685 e define a frequência. Idempotente."""
    if config.a_simular():
        _iniciados[endereco] = True
        return True
    if _iniciados.get(endereco):
        return True
    if endereco in _ausentes:
        return False

    bus = _abrir_bus()
    if bus is None:
        return False
    _ligar_oe()
    try:
        bus.write_byte_data(endereco, _MODO1, 0x00)
        time.sleep(0.01)
        # prescale = round(clock / (4096 * freq)) - 1, com clock de 25 MHz
        prescale = int(round(25_000_000.0 / (4096 * frequencia_hz)) - 1)
        prescale = max(3, min(255, prescale))

        antigo = bus.read_byte_data(endereco, _MODO1)
        bus.write_byte_data(endereco, _MODO1, (antigo & 0x7F) | 0x10)  # dormir
        bus.write_byte_data(endereco, _PRESCALE, prescale)
        bus.write_byte_data(endereco, _MODO1, antigo)
        time.sleep(0.005)
        bus.write_byte_data(endereco, _MODO1, antigo | 0xA0)  # acordar + auto-inc
        _iniciados[endereco] = True
        return True
    except Exception as erro:  # noqa: BLE001
        _ausentes.add(endereco)
        print(
            f"⚠️  PCA9685 em 0x{endereco:02x} não responde ({erro}).\n"
            f"    Confirma com:  i2cdetect -y 1\n"
            f"    Desisti deste endereço até reiniciares."
        )
        return False


def escrever_bruto(endereco: int, canal: int, ligado: int, desligado: int) -> None:
    """Escreve os contadores ON/OFF de um canal (0-4095, ou o bit 0x1000)."""
    if endereco in _ausentes:
        return
    bus = _abrir_bus()
    if bus is None:
        return
    base = _LED0_ON_L + 4 * canal
    try:
        bus.write_byte_data(endereco, base + 0, ligado & 0xFF)
        bus.write_byte_data(endereco, base + 1, ligado >> 8)
        bus.write_byte_data(endereco, base + 2, desligado & 0xFF)
        bus.write_byte_data(endereco, base + 3, desligado >> 8)
    except Exception as erro:  # noqa: BLE001
        _ausentes.add(endereco)
        print(f"⚠️  Falha a escrever no PCA9685 0x{endereco:02x} canal {canal}: {erro}")


def duty(endereco: int, canal: int, fracao: float) -> None:
    """Define o ciclo de trabalho de um canal, de 0.0 a 1.0.

    Para 0% e 100% usamos os bits FULL_OFF/FULL_ON em vez de 0/4095 — senão
    os pinos de direção dos motores teriam um pequeno impulso a cada ciclo,
    o que os faz zumbir.
    """
    if config.a_simular():
        return
    if fracao >= 1.0:
        escrever_bruto(endereco, canal, 0x1000, 0)       # FULL_ON
    elif fracao <= 0.0:
        escrever_bruto(endereco, canal, 0, 0x1000)       # FULL_OFF
    else:
        escrever_bruto(endereco, canal, 0, int(fracao * 4095))


def microsegundos(endereco: int, canal: int, us: float, frequencia_hz: float = 50.0) -> None:
    """Define a largura do impulso em microssegundos — é assim que se fala com servos.

    Um servo típico entende 500 µs (0°) a 2500 µs (180°), com 1500 µs ao meio.
    """
    if config.a_simular():
        return
    periodo_us = 1_000_000.0 / frequencia_hz
    contagem = int(round(us / periodo_us * 4096))
    escrever_bruto(endereco, canal, 0, max(0, min(4095, contagem)))


def desligar_tudo(endereco: int) -> None:
    """Põe os 16 canais em FULL_OFF. Usado ao sair do programa."""
    if config.a_simular():
        return
    for canal in range(16):
        escrever_bruto(endereco, canal, 0, 0x1000)


import atexit  # noqa: E402


@atexit.register
def _cortar_ao_sair() -> None:
    """Corta as saídas por hardware ao terminar, aconteça o que acontecer."""
    try:
        desligar_saidas()
    except Exception:  # noqa: BLE001, S110
        pass
