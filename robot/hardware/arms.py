"""OS BRAÇOS — cinco servos por I2C (PCA9685 em 0x41, a 50 Hz).

    ombro_esq (DS3218)      ombro_dir (DS3218)
        │                       │
    cotovelo_esq (MG90S)    cotovelo_dir (MG90S)
                                │
                            garra (MG90S)

╔══════════════════════════════════════════════════════════════════════════╗
║  ⚠️  NUNCA ALIMENTAR SERVOS A PARTIR DOS PINOS DE 5 V DO RASPBERRY PI    ║
║                                                                          ║
║  Esses pinos vêm do rail de entrada, a jusante do chip que monitoriza   ║
║  quedas de tensão; as pistas do header são finas; e o pico de arranque  ║
║  de um servo cria uma queda que reinicia o Pi ou corrompe o cartão SD.  ║
║                                                                          ║
║  Os servos têm barramento próprio de 6 V. Só a MASSA é partilhada.      ║
╚══════════════════════════════════════════════════════════════════════════╝

Funções para usar:

    acenar()            apontar("esquerda")     bracos_ao_lado()
    garra("abrir")      pose("festejar")        angulo("ombro_esq", 90)
"""

from __future__ import annotations

import atexit
import threading
import time

from robot import config
from robot.hardware import pca9685

FREQ_HZ = 50.0
_lock = threading.Lock()
_posicao: dict[str, float] = {}
_ligado = False


def _endereco() -> int:
    return int(config.obter("bracos.i2c", 0x41))


def _juntas() -> dict:
    """A definição das juntas, vinda do config/robot.yaml."""
    return config.obter("bracos.juntas", {}) or {}


def _iniciar() -> bool:
    global _ligado
    if _ligado:
        return True
    _ligado = pca9685.iniciar(_endereco(), FREQ_HZ)
    return _ligado


# ---------------------------------------------------------------------------
# Nível baixo — um servo de cada vez
# ---------------------------------------------------------------------------

def angulo(junta: str, graus: float, esperar: float = 0.0) -> None:
    """Move uma junta para um ângulo, respeitando os limites do robot.yaml.

    >>> angulo("ombro_dir", 120)

    Os limites existem para o braço não bater no corpo nem o servo forçar
    contra um batente — o que o queima em segundos.
    """
    juntas = _juntas()
    if junta not in juntas:
        disponiveis = ", ".join(sorted(juntas)) or "(nenhuma definida)"
        raise ValueError(
            f"Não existe a junta '{junta}'.\n"
            f"As que existem são: {disponiveis}\n"
            f"(Estão definidas em config/robot.yaml, secção bracos.juntas)"
        )

    cfg = juntas[junta]
    minimo = float(cfg.get("min", 0))
    maximo = float(cfg.get("max", 180))

    # ⚠️ A validação acontece AQUI, não em quem chama. Se o LLM pedir 400°,
    #    é aqui que a mecânica é salva.
    graus_limitado = max(minimo, min(maximo, float(graus)))
    if graus_limitado != float(graus):
        print(f"⚠️  {junta}: {graus}° fora dos limites [{minimo}, {maximo}] → {graus_limitado}°")

    _posicao[junta] = graus_limitado

    if config.a_simular():
        config.sim(f"servo {junta} → {graus_limitado:.0f}°")
    elif _iniciar():
        us_min = float(config.obter("bracos.us_min", 500))
        us_max = float(config.obter("bracos.us_max", 2500))
        us = us_min + (graus_limitado / 180.0) * (us_max - us_min)
        with _lock:
            pca9685.microsegundos(_endereco(), int(cfg["canal"]), us, FREQ_HZ)

    if esperar:
        time.sleep(esperar)


def suave(junta: str, graus: float, duracao: float = 0.5, passos: int = 20) -> None:
    """Move devagar, em vez de saltar. Fica muito melhor e força menos a mecânica."""
    inicio = _posicao.get(junta, graus)
    for i in range(1, passos + 1):
        angulo(junta, inicio + (graus - inicio) * i / passos)
        time.sleep(duracao / passos)


def relaxar() -> None:
    """Corta o sinal a todos os servos — deixam de forçar e ficam moles.

    Importante: um servo a manter uma posição consome corrente e aquece. Se
    o robô vai ficar parado, é melhor relaxar.
    """
    if config.a_simular():
        config.sim("servos → relaxados")
        return
    if _ligado:
        pca9685.desligar_tudo(_endereco())


def posicao_atual() -> dict[str, float]:
    return dict(_posicao)


# ---------------------------------------------------------------------------
# Nível alto — gestos com nome (a Lara edita estes em robot/gestures.py)
# ---------------------------------------------------------------------------

def pose(nome: str) -> None:
    """Coloca os braços numa pose com nome, definida em robot/gestures.py.

    ⚠️ AS JUNTAS MOVEM-SE UMA A UMA, com um pequeno intervalo entre elas.

    Não é estética: é elétrica. Dois DS3218 a arrancar em simultâneo puxam
    até 6 A, e o regulador dos servos dá 5 A. Escalonar o arranque mantém o
    pico dentro do que a fonte aguenta — e evita que a queda de tensão
    reinicie o Raspberry Pi.

    Os ombros (que são os servos grandes) nunca arrancam ao mesmo tempo.
    """
    from robot.gestures import POSES

    if nome not in POSES:
        raise ValueError(
            f"Não existe a pose '{nome}'.\n"
            f"As que existem são: {', '.join(sorted(POSES))}\n"
            f"(Podes criar novas em robot/gestures.py)"
        )
    intervalo = float(config.obter("bracos.intervalo_s", 0.08))
    # Ombros primeiro e separados — são os que puxam mais corrente.
    juntas = sorted(POSES[nome].items(), key=lambda kv: 0 if "ombro" in kv[0] else 1)
    for i, (junta, graus) in enumerate(juntas):
        angulo(junta, graus)
        if intervalo and i < len(juntas) - 1:
            time.sleep(intervalo)


def gesto(nome: str) -> None:
    """Corre um gesto — uma sequência de poses com pausas."""
    from robot.gestures import GESTOS

    if nome not in GESTOS:
        raise ValueError(
            f"Não existe o gesto '{nome}'.\n"
            f"Os que existem são: {', '.join(sorted(GESTOS))}"
        )
    for passo, pausa in GESTOS[nome]:
        if isinstance(passo, str):
            pose(passo)
        else:
            for junta, graus in passo.items():
                angulo(junta, graus)
        if pausa and not config.a_simular():
            time.sleep(pausa)


def acenar(vezes: int = 3) -> None:
    """O gesto mais importante do robô todo."""
    from robot.gestures import POSES

    if "acenar_cima" not in POSES:
        return
    pose("acenar_cima")
    time.sleep(0.3)
    for _ in range(max(1, min(6, vezes))):
        pose("acenar_fora")
        time.sleep(0.25)
        pose("acenar_dentro")
        time.sleep(0.25)
    pose("descanso")


def bracos_ao_lado() -> None:
    pose("descanso")


def apontar(direcao: str = "frente") -> None:
    """Aponta com um braço. 'esquerda', 'direita', 'cima' ou 'frente'."""
    from robot.gestures import POSES

    escolha = {
        "esquerda": "apontar_esq",
        "direita": "apontar_dir",
        "cima": "apontar_cima",
        "frente": "apontar_dir",
    }.get(direcao)
    if escolha is None or escolha not in POSES:
        raise ValueError(
            "Só sei apontar para 'esquerda', 'direita', 'cima' ou 'frente'."
        )
    pose(escolha)
    time.sleep(1.2)
    pose("descanso")


def festejar() -> None:
    """Braços ao ar. Para quando há boas notícias."""
    gesto("festejar")


def abrir_garra() -> None:
    garra("abrir")


def fechar_garra() -> None:
    garra("fechar")


def garra(acao: str = "abrir") -> None:
    """Abre ou fecha a garra.

    ⚠️ A garra fecha com força suficiente para fazer doer num dedo pequeno.
       O `fechar` do robot.yaml não deve ser o limite mecânico do servo.
    """
    if acao not in ("abrir", "fechar"):
        raise ValueError("A garra só sabe 'abrir' ou 'fechar'.")
    juntas = _juntas()
    if "garra" not in juntas:
        return
    cfg = juntas["garra"]
    angulo("garra", float(cfg["max"] if acao == "abrir" else cfg["min"]))


def disponivel() -> bool:
    return config.a_simular() or _iniciar()


@atexit.register
def _relaxar_ao_sair() -> None:
    """Relaxar SEMPRE ao terminar — senão os servos ficam a forçar e a aquecer."""
    try:
        relaxar()
    except Exception:  # noqa: BLE001, S110
        pass
