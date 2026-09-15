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
║  OS ENCODERS: contar quadratura em Python a ~1200 Hz por canal           ║
║  desperdiça CPU, e o pigpio (que fazia isto por DMA) não funciona        ║
║  no Pi 5. Por isso este caminho (tb6612) NÃO os usa.                     ║
║                                                                          ║
║  ⚠️ MAS HÁ UM SEGUNDO CAMINHO, e é o que resolve isso: com               ║
║  `motores.ligacao: mbot2` no robot.yaml o mBot2 fica INTEIRO e           ║
║  fala com o Pi por USB — o shield conta a quadratura em hardware         ║
║  e devolve graus. Aí o `andar_cm` deixa de ser um cronómetro e           ║
║  passa a ser uma medição, e o `virar_graus` usa o giroscópio.            ║
║  Ver robot/hardware/mbot2.py.                                            ║
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
from robot.hardware import mbot2, pca9685


def _ligacao() -> str:
    """"tb6612" (motores canibalizados) ou "mbot2" (o robô inteiro, por USB)."""
    return str(config.obter("motores.ligacao", "tb6612")).lower()


def _pelo_mbot2() -> bool:
    return _ligacao() == "mbot2"

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
    # ⚠️ Com o mBot2 não há PCA9685 nenhum em 0x40 — as rodas são comandadas
    #    pelo shield, por USB. Tentar iniciá-lo despejava "Remote I/O error"
    #    a cada chamada, e o `i2c.motores` do robot.yaml já está marcado como
    #    "caminho TB6612 antigo, inativo".
    if _pelo_mbot2():
        return False
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
        if _pelo_mbot2():
            # Mesmo a simular: é isto que mantém o conta-quilómetros de mentira
            # a andar, para a Lara poder aprender no Mac sem o robô ligado.
            mbot2.velocidade(*_em_rpm(esquerdo, direito))
    elif _pelo_mbot2():
        # A fração -1..1 vira RPM. O shield mantém a velocidade sozinho, em
        # malha fechada: não é preciso reenviar isto num ciclo.
        mbot2.velocidade(*_em_rpm(esquerdo, direito))
    else:
        _motor(_PWMA, _AIN1, _AIN2, esquerdo)
        _motor(_PWMB, _BIN1, _BIN2, direito)

    _a_mover_desde = None if (esquerdo == 0 and direito == 0) else time.monotonic()


def _em_rpm(esquerdo: float, direito: float) -> tuple[float, float]:
    """A fração -1..1 de cada roda, em RPM."""
    rpm = float(config.obter("mbot2.rpm_max", 86.0))
    return (esquerdo * rpm, direito * rpm)


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


def andar_cm(centimetros: float) -> float:
    """Anda uma distância. Devolve quanto andou mesmo, quando dá para saber.

    Há duas maneiras de fazer isto, e a diferença entre elas é a diferença
    entre um brinquedo e um robô:

    · pelo CRONÓMETRO (tb6612) — anda durante o tempo que a conta diz. Se o
      chão for mais macio, se a bateria estiver mais fraca, se uma roda
      escorregar, ele não sabe. Nunca é exato.
    · pela MEDIÇÃO (mbot2) — pergunta às rodas quanto já andaram e pára
      quando chegou. Isso é uma malha fechada, e corta o erro na origem em
      vez de o acumular.
    """
    centimetros = max(-50.0, min(50.0, centimetros))
    if not _pelo_mbot2() or config.a_simular():
        cm_por_s = float(config.obter("motores.cm_por_segundo", 18.0))
        duracao = abs(centimetros) / max(cm_por_s, 1.0)
        frente() if centimetros > 0 else tras()
        time.sleep(min(duracao, 3.0))
        parar()
        return centimetros

    alvo = abs(centimetros)
    mbot2.zerar()
    frente() if centimetros > 0 else tras()
    # A rede de segurança é o tempo: se uma roda ficar presa, o contador nunca
    # chega ao alvo e isto andaria para sempre.
    limite = time.monotonic() + min(20.0, alvo / max(1.0, cm_por_s_atual()) * 3.0 + 2.0)
    while time.monotonic() < limite:
        if mbot2.progresso_cm() >= alvo:
            break
        time.sleep(0.05)
    parar()
    andou = mbot2.progresso_cm()
    return andou if centimetros > 0 else -andou


# O `motores.cm_por_segundo` do robot.yaml foi medido a esta fração de
# velocidade — é a referência que permite escalar a conta para as outras.
VELOCIDADE_DE_REFERENCIA = 0.5


def cm_por_s_atual() -> float:
    """A velocidade que está configurada, em cm/s.

    Com o mBot2 é uma conta exata (RPM × perímetro da roda). Com o TB6612 é
    uma regra de três a partir de uma medição feita à mão — que é precisamente
    a diferença entre os dois caminhos.
    """
    if _pelo_mbot2():
        return mbot2.rpm_para_cms(float(config.obter("mbot2.rpm_max", 86.0)) * _v())
    medido = float(config.obter("motores.cm_por_segundo", 18.0))
    return medido * _v() / VELOCIDADE_DE_REFERENCIA


def virar_graus(graus: float) -> float:
    """Roda no lugar. Positivo = direita, negativo = esquerda.

    Com o mBot2 usa o GIROSCÓPIO do CyberPi: mede o que o robô rodou mesmo, e
    não o que devia ter rodado. O que escorrega deixa de contar.
    """
    graus = max(-180.0, min(180.0, graus))
    if not _pelo_mbot2() or config.a_simular():
        t90 = float(config.obter("motores.tempo_90_graus", 0.55))
        duracao = abs(graus) / 90.0 * t90
        direita() if graus > 0 else esquerda()
        time.sleep(min(duracao, 3.0))
        parar()
        return graus

    alvo = abs(graus)
    mbot2.zerar()
    direita() if graus > 0 else esquerda()
    limite = time.monotonic() + min(15.0, alvo / 90.0 * 3.0 + 2.0)
    while time.monotonic() < limite:
        if abs(mbot2.rodou_graus()) >= alvo:
            break
        time.sleep(0.02)
    parar()
    rodou = abs(mbot2.rodou_graus())
    return rodou if graus > 0 else -rodou


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
