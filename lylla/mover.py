"""MOVER — as rodas, em português.

    from lylla import mover
    mover.andar(30)

Por baixo há malha fechada, encoders e um cabo série. Nada disso aparece aqui.
"""

from __future__ import annotations

from robot import config
from robot.hardware import mbot2, motors

PERTO_DEMAIS_CM = 20.0      # abaixo disto não se anda para a frente
PASSO_CM = 10.0             # anda aos bocados, para poder olhar pelo caminho


def andar(cm: float = 20) -> float:
    """Anda para a frente. Devolve quantos centímetros andou mesmo.

    Vai aos bocados e olha entre cada um: se aparecer alguma coisa à frente,
    pára e diz. Um robô que anda sem olhar não é corajoso, é avariado.
    """
    cm = _limitar_distancia(cm)
    if cm <= 0:
        return 0.0

    andado = 0.0
    while andado < cm - 0.5:
        if not caminho_livre():
            print(f"  ✋ parei aos {andado:.0f} cm — está alguma coisa a "
                  f"{distancia():.0f} cm à minha frente")
            return andado
        andado += abs(motors.andar_cm(min(PASSO_CM, cm - andado)))
    print(f"  ➡️  andei {andado:.0f} cm")
    if not mbot2.rodas_concordam():
        print("  ⚠️  as minhas duas rodas contaram sentidos contrários numa")
        print("      linha reta. Diz ao pai para trocar o `mbot2.inverter_direita`")
        print("      no config/robot.yaml — é uma linha, e fica resolvido.")
    return andado


def recuar(cm: float = 20) -> float:
    """Anda para trás. ⚠️ A Lylla não tem olhos atrás: pouco e devagar."""
    andado = abs(motors.andar_cm(-_limitar_distancia(cm)))
    print(f"  ⬅️  recuei {andado:.0f} cm (às cegas — não vejo para trás)")
    return andado


def virar_direita(graus: float = 90) -> float:
    """Roda para a direita sem sair do sítio."""
    return _virar(abs(_limitar_graus(graus)), "direita")


def virar_esquerda(graus: float = 90) -> float:
    """Roda para a esquerda sem sair do sítio."""
    return -_virar(-abs(_limitar_graus(graus)), "esquerda")


def _virar(graus: float, lado: str) -> float:
    rodou = motors.virar_graus(graus)
    print(f"  ↻  rodei {abs(rodou):.0f} graus para a {lado}")
    return abs(rodou)


def parar() -> None:
    """Pára já.

    ⚠️ Isto demora umas dezenas de milissegundos a chegar pelo cabo. A paragem
       a sério, aquela em que se carrega quando algo corre mal, é o botão
       vermelho — não é isto.
    """
    motors.parar()
    print("  ⏹  parei")


def devagar() -> None:
    """Metade da velocidade normal. Boa para experimentar coisas novas."""
    _velocidade(0.25)


def normal() -> None:
    _velocidade(0.5)


def depressa() -> None:
    """O máximo que é seguro dentro de casa — que não é o máximo do motor."""
    _velocidade(float(config.obter("motores.velocidade_max", 0.6)))


def _velocidade(fracao: float) -> None:
    config.carregar().setdefault("motores", {})["velocidade"] = fracao
    print(f"  🐢 velocidade: {fracao:.0%}  (~{motors.cm_por_s_atual():.0f} cm por segundo)")


def distancia() -> float:
    """A quantos centímetros está a coisa mais próxima à frente."""
    return round(mbot2.distancia_cm(), 1)


def caminho_livre() -> bool:
    """True se dá para andar, False se está alguma coisa demasiado perto."""
    return distancia() > PERTO_DEMAIS_CM


def quanto_andei() -> float:
    """Centímetros desde o último `zerar()`.

    Quem conta são as RODAS, não o relógio: se o robô escorregar ou alguém o
    empurrar, o número muda na mesma. É isso que faz dele um robô.
    """
    return round(mbot2.andado_cm(), 1)


def zerar() -> None:
    """Põe o conta-quilómetros a zero."""
    mbot2.zerar()
    print("  0️⃣  conta-quilómetros a zero")


def em_cima_da_mesa() -> None:
    """Baixa o teto da velocidade. Uma queda de 75 cm parte o robô."""
    motors.modo("secretaria")
    print("  🪑 modo secretária — velocidade limitada, e é de propósito")


def no_chao() -> None:
    motors.modo("chao")
    print("  🏠 modo chão — velocidade normal")


def _limitar_distancia(cm: float) -> float:
    cm = abs(float(cm))
    if cm > 200:
        print("  ✂️  200 cm de cada vez é o máximo — vamos com 200.")
        return 200.0
    return cm


def _limitar_graus(graus: float) -> float:
    return max(-360.0, min(360.0, float(graus)))
