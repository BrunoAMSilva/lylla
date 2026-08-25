"""OS MOTORES — TB6612FNG comandado por um PCA9685 (I2C, 0x40, a 1 kHz).

Os motores são os do mBot2 canibalizado: 180 Optical Encoder Motor,
7,4 V nominal, redução 39,6:1, ≤750 mA em carga — cabem folgadamente no
TB6612FNG, que aguenta 1,2 A por canal.

╔══════════════════════════════════════════════════════════════════════════╗
║  PORQUÊ I2C E NÃO GPIO DIRETO                                            ║
║                                                                          ║
║  A biblioteca RPi.GPIO NÃO FUNCIONA no Raspberry Pi 5. O Pi 5 trouxe um  ║
║  chip de entradas/saídas novo (o RP1) e metade dos tutoriais de robôs    ║
║  que estão na Internet foram escritos para o Pi 4 — vão simplesmente     ║
║  rebentar.                                                               ║
║                                                                          ║
║  Escolhemos comandar tudo por I2C precisamente por causa disto: o I2C    ║
║  é o mesmo no Pi 4 e no Pi 5. Este código não vai partir com a próxima   ║
║  atualização do sistema.                                                 ║
║                                                                          ║
║  NOTA SOBRE OS ENCODERS: os motores têm-nos e os fios estão ligados,    ║
║  mas a v1 não os usa. Contar quadratura em Python a ~1200 Hz por canal  ║
║  desperdiça CPU, e o pigpio (que fazia isto por DMA) não funciona no    ║
║  Pi 5. Ficam prontos para a v2 com o ESP32, que tem 8 contadores de     ║
║  quadratura em hardware.                                                ║
╚══════════════════════════════════════════════════════════════════════════╝

Funções para usar:

    frente()          tras()          parar()
    esquerda()        direita()
    andar_cm(30)      virar_graus(90)
"""

from __future__ import annotations

import atexit
import time

from robot import config
from robot.hardware import pca9685

# Canais do PCA9685 #1 ligados ao TB6612FNG
_PWMA, _AIN1, _AIN2 = 0, 1, 2
_PWMB, _BIN1, _BIN2 = 5, 3, 4

FREQ_HZ = 1000.0   # motores a 50 Hz rosnam e não controlam a baixa velocidade

_a_mover_desde: float | None = None
_ligado = False


def _endereco() -> int:
    return int(config.obter("i2c.motores", 0x40))


def _iniciar() -> bool:
    global _ligado
    if _ligado:
        return True
    _ligado = pca9685.iniciar(_endereco(), FREQ_HZ)
    return _ligado


def _motor(pwm_ch: int, in1: int, in2: int, velocidade: float) -> None:
    """velocidade de -1.0 (trás) a 1.0 (frente).

    Com 0, pomos IN1=IN2=HIGH, que no TB6612 é **travagem curta** (short
    brake) — as duas pontas do motor ficam à massa e ele resiste a rodar.
    Se puséssemos ambos a LOW seria *coast*: o motor fica livre e o robô
    continua a deslizar, o que estraga a paragem à beira de uma mesa.
    """
    if not _iniciar():
        return
    endereco = _endereco()
    velocidade = max(-1.0, min(1.0, velocidade))
    if velocidade > 0:
        pca9685.duty(endereco, in1, 1.0)
        pca9685.duty(endereco, in2, 0.0)
    elif velocidade < 0:
        pca9685.duty(endereco, in1, 0.0)
        pca9685.duty(endereco, in2, 1.0)
    else:
        # Travagem curta: ambas as entradas a HIGH e o PWM ao máximo.
        pca9685.duty(endereco, in1, 1.0)
        pca9685.duty(endereco, in2, 1.0)
        pca9685.duty(endereco, pwm_ch, 1.0)
        return
    pca9685.duty(endereco, pwm_ch, abs(velocidade))


# ---------------------------------------------------------------------------
# Camada que a Lara usa
# ---------------------------------------------------------------------------

_modo = "chao"


def modo(nome: str = "chao") -> str:
    """"chao" ou "secretaria". Muda o TETO de velocidade, para sempre.

    ⚠️ Isto não é conforto, é segurança. Uma secretária tem 75 cm de altura e
       arestas a menos de meio metro em todas as direções. A velocidade que é
       normal no chão da sala atravessa uma secretária em menos de dois
       segundos — e os sensores de precipício, a 10 leituras por segundo, não
       chegam para travar a tempo.

       Por isso o limite não vive na função que anda: vive AQUI, no sítio por
       onde passa obrigatoriamente todo o movimento, incluindo o que o LLM
       mandar fazer.
    """
    global _modo
    if nome not in ("chao", "secretaria"):
        raise ValueError(f"Modo '{nome}' não existe. Só há 'chao' e 'secretaria'.")
    _modo = nome
    parar()
    return _modo


def modo_atual() -> str:
    return _modo


def _limitar(v: float) -> float:
    """Nunca deixar passar o limite de segurança da configuração."""
    maximo = float(config.obter("motores.velocidade_max", 0.6))
    if _modo == "secretaria":
        maximo = min(maximo, float(config.obter("secretaria.velocidade_max", 0.25)))
    return max(-maximo, min(maximo, v))


def mover(esquerdo: float, direito: float) -> None:
    """Controlo direto dos dois motores, de -1 a 1."""
    global _a_mover_desde
    esquerdo = _limitar(esquerdo * float(config.obter("motores.compensacao_esq", 1.0)))
    direito = _limitar(direito * float(config.obter("motores.compensacao_dir", 1.0)))

    if config.a_simular():
        config.sim(f"motores → esq={esquerdo:+.2f} dir={direito:+.2f}")
    else:
        _motor(_PWMA, _AIN1, _AIN2, esquerdo)
        _motor(_PWMB, _BIN1, _BIN2, direito)

    _a_mover_desde = None if (esquerdo == 0 and direito == 0) else time.monotonic()


def _v() -> float:
    return float(config.obter("motores.velocidade", 0.5))


def frente(velocidade: float | None = None) -> None:
    v = _v() if velocidade is None else velocidade
    mover(v, v)


def tras(velocidade: float | None = None) -> None:
    v = _v() if velocidade is None else velocidade
    mover(-v, -v)


def esquerda(velocidade: float | None = None) -> None:
    v = _v() if velocidade is None else velocidade
    mover(-v, v)


def direita(velocidade: float | None = None) -> None:
    v = _v() if velocidade is None else velocidade
    mover(v, -v)


def parar() -> None:
    mover(0, 0)


def andar_cm(centimetros: float) -> None:
    """Anda uma distância aproximada.

    NOTA: sem encoders, o robô não sabe onde está. Só sabe durante quanto
    tempo andou. Por isso isto nunca é exato — e por isso é que os robôs a
    sério têm sensores nas rodas.
    """
    centimetros = max(-50.0, min(50.0, centimetros))
    cm_por_s = float(config.obter("motores.cm_por_segundo", 18.0))
    duracao = abs(centimetros) / max(cm_por_s, 1.0)
    frente() if centimetros > 0 else tras()
    time.sleep(min(duracao, 3.0))
    parar()


def virar_graus(graus: float) -> None:
    """Roda no lugar. Positivo = direita, negativo = esquerda."""
    graus = max(-180.0, min(180.0, graus))
    t90 = float(config.obter("motores.tempo_90_graus", 0.55))
    duracao = abs(graus) / 90.0 * t90
    direita() if graus > 0 else esquerda()
    time.sleep(min(duracao, 3.0))
    parar()


def verificar_timeout() -> None:
    """Para os motores se um comando ficou pendurado.

    Se o programa bloquear a meio de um movimento, o robô continuaria a andar
    até bater na parede. Isto é a rede de segurança — chamar no ciclo principal.
    """
    if _a_mover_desde is None:
        return
    limite = float(config.obter("motores.timeout_s", 3.0))
    if time.monotonic() - _a_mover_desde > limite:
        print("⚠️  Timeout de movimento — a parar os motores por segurança.")
        parar()


@atexit.register
def _parar_ao_sair() -> None:
    """PARAR SEMPRE. Aconteça o que acontecer ao programa."""
    try:
        parar()
    except Exception:  # noqa: BLE001, S110
        pass
