"""A LYLLA, para escrever de uma linha só.

Abre o terminal na pasta do robô e escreve:

    python3
    >>> from lylla import *
    >>> ajuda()

E já está. Todos os comandos ficam à mão, em português, e nenhum deles precisa
que saibas o que é um objeto, um módulo ou uma classe. Isso aprende-se depois —
primeiro é preciso ver o robô mexer-se.

    andar(30)          # anda 30 centímetros e diz quanto andou mesmo
    virar_direita()    # meia volta à direita (90 graus)
    olhos("feliz")
    luz("azul")

⚠️ Por baixo disto está bastante complexidade: uma ligação série ao mBot2,
   subscrições, malha fechada, limites de segurança. Nada disso aparece aqui de
   propósito. Quem quiser ver o motor por dentro abre o robot/hardware/mbot2.py.

Para experimentar sem o robô ligado (no Mac, por exemplo):

    ROBO_SIMULAR=1 python3 -c "from lylla import *; andar(30)"
"""

from __future__ import annotations

import time

from robot import config
from robot.hardware import mbot2, motors

__all__ = [
    "ajuda", "andar", "recuar", "virar_esquerda", "virar_direita", "parar",
    "devagar", "normal", "depressa", "distancia", "caminho_livre",
    "olhos", "luz", "dizer", "esperar", "quanto_andei", "zerar",
    "em_cima_da_mesa", "no_chao", "estado",
]

# Quando a coisa mais próxima está a menos de isto, não se anda para a frente.
PERTO_DEMAIS_CM = 20.0
PASSO_CM = 10.0          # anda aos bocados, para poder olhar pelo caminho


# ---------------------------------------------------------------------------
# O mapa — é a primeira coisa que ela vai escrever
# ---------------------------------------------------------------------------
def ajuda() -> None:
    """Escreve a lista de tudo o que a Lylla sabe fazer."""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  A LYLLA SABE FAZER ISTO                                         ║
╚══════════════════════════════════════════════════════════════════╝

  ANDAR
    andar()            anda 20 cm            andar(50)
    recuar()           anda 20 cm para trás  recuar(10)
    virar_direita()    roda 90 graus         virar_direita(45)
    virar_esquerda()   roda 90 graus
    parar()            pára já

  DEPRESSA OU DEVAGAR
    devagar()   ·   normal()   ·   depressa()

  VER
    distancia()        a quantos cm está a coisa mais próxima
    caminho_livre()    True se dá para andar, False se não dá
    quanto_andei()     cm desde a última vez que puseste a zero
    zerar()            põe o conta-quilómetros a zero

  A CARA E AS LUZES
    olhos("feliz")     feliz · piscar · a_pensar · tonto · a_dormir
    luz("azul")        azul · verde · vermelho · amarelo · roxo ·
                       branco · ciano · laranja · rosa · apagar

  FALAR E ESPERAR
    dizer("olá Lara")
    esperar(2)         espera 2 segundos

  E AINDA
    ajuda()            este mapa
    estado()           bateria, distância, quanto andou

  ONDE ESTÁ O ROBÔ
    em_cima_da_mesa()  limita a velocidade (uma queda parte-o)
    no_chao()          velocidade normal

  EXPERIMENTA ISTO — um quadrado:

      for lado in range(4):
          andar(30)
          virar_direita()

  Repara: `andar` DEVOLVE quantos centímetros andou mesmo.

      andou = andar(30)
      print("pedi 30 e ele andou", andou)
""")


# ---------------------------------------------------------------------------
# Andar
# ---------------------------------------------------------------------------
def andar(cm: float = 20) -> float:
    """Anda para a frente. Devolve quantos centímetros andou mesmo.

    Vai aos bocados e olha entre cada um: se aparecer alguma coisa à frente,
    pára e diz-te. Um robô que anda sem olhar não é corajoso, é avariado.
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
        passo = min(PASSO_CM, cm - andado)
        andado += abs(motors.andar_cm(passo))
    print(f"  ➡️  andei {andado:.0f} cm")
    if not mbot2.rodas_concordam():
        print("  ⚠️  as minhas duas rodas contaram sentidos contrários numa")
        print("      linha reta. Diz ao pai para trocar o `mbot2.inverter_direita`")
        print("      no config/robot.yaml — é uma linha, e fica resolvido.")
    return andado


def recuar(cm: float = 20) -> float:
    """Anda para trás. Devolve quantos centímetros andou.

    ⚠️ A Lylla não tem olhos atrás. Recua devagar e pouco.
    """
    cm = _limitar_distancia(cm)
    andado = abs(motors.andar_cm(-cm))
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

    ⚠️ Isto é o comando normal de parar, e demora umas dezenas de
       milissegundos a chegar pelo cabo. A paragem a sério, aquela em que se
       carrega quando algo corre mal, é o botão vermelho — não é isto.
    """
    motors.parar()
    print("  ⏹  parei")


# ---------------------------------------------------------------------------
# Depressa ou devagar
# ---------------------------------------------------------------------------
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
    cms = motors.cm_por_s_atual()
    print(f"  🐢 velocidade: {fracao:.0%}  (~{cms:.0f} cm por segundo)")


# ---------------------------------------------------------------------------
# Ver
# ---------------------------------------------------------------------------
def distancia() -> float:
    """A quantos centímetros está a coisa mais próxima à frente."""
    return round(mbot2.distancia_cm(), 1)


def caminho_livre() -> bool:
    """True se dá para andar, False se está alguma coisa demasiado perto."""
    return distancia() > PERTO_DEMAIS_CM


def quanto_andei() -> float:
    """Centímetros andados desde o último `zerar()`.

    Quem conta isto são as rodas, não o relógio: se o robô escorregar ou
    alguém o empurrar, o número muda na mesma. É o que faz dele um robô.
    """
    return round(mbot2.andado_cm(), 1)


def zerar() -> None:
    """Põe o conta-quilómetros a zero."""
    mbot2.zerar()
    print("  0️⃣  conta-quilómetros a zero")


# ---------------------------------------------------------------------------
# Cara, luzes, voz
# ---------------------------------------------------------------------------
def olhos(emocao: str = "feliz") -> None:
    """Muda a cara. Há: feliz, piscar, a_pensar, tonto, a_dormir."""
    conseguiu = mbot2.olhos(emocao)
    try:                                    # e a cara a sério, quando existir
        from robot.hardware import eyes     # noqa: PLC0415

        if eyes.disponivel():
            eyes.expressao(emocao)
            conseguiu = True
    except Exception:  # noqa: BLE001
        pass
    if conseguiu:
        print(f"  👀 olhos: {emocao}")
    else:
        print(f"  ❓ não conheço a cara '{emocao}'. "
              f"Há: {', '.join(mbot2.EMOCOES)}")


def luz(cor: str = "ciano") -> None:
    """Acende as luzes do robô. `luz("apagar")` desliga-as."""
    if mbot2.luz(cor):
        print(f"  💡 luz: {cor}")
    else:
        print(f"  ❓ não conheço a cor '{cor}'. "
              f"Há: {', '.join(mbot2.CORES)}, apagar")


def dizer(texto: str = "olá!") -> None:
    """A Lylla diz uma frase em voz alta."""
    if config.a_simular():
        print(f"  🗣️  (simulado) {texto}")
        return
    try:
        from robot.voice import speak  # noqa: PLC0415

        speak.falar(texto)
    except Exception:  # noqa: BLE001
        print(f"  🔇 (sem voz agora) {texto}")
        return
    print(f"  🗣️  {texto}")


def esperar(segundos: float = 1) -> None:
    """Não faz nada durante uns segundos."""
    time.sleep(max(0.0, min(60.0, float(segundos))))


# ---------------------------------------------------------------------------
# Onde está o robô — isto é segurança, não é conforto
# ---------------------------------------------------------------------------
def em_cima_da_mesa() -> None:
    """Diz à Lylla que está numa secretária: baixa o teto da velocidade.

    Uma queda de 75 cm parte o robô. O limite não vive na função que anda,
    vive no sítio por onde passa TODO o movimento — até o que o cérebro mandar.
    """
    motors.modo("secretaria")
    print("  🪑 modo secretária — velocidade limitada, e é de propósito")


def no_chao() -> None:
    motors.modo("chao")
    print("  🏠 modo chão — velocidade normal")


def estado() -> dict:
    """Um retrato do robô: bateria, distância, quanto andou."""
    return mbot2.estado()


# ---------------------------------------------------------------------------
def _limitar_distancia(cm: float) -> float:
    cm = abs(float(cm))
    if cm > 200:
        print("  ✂️  200 cm de cada vez é o máximo — vamos com 200.")
        return 200.0
    return cm


def _limitar_graus(graus: float) -> float:
    graus = float(graus)
    return max(-360.0, min(360.0, graus))


def _apresentar() -> None:
    nome = config.nome_do_robo()
    if config.a_simular():
        print(f"\n🤖 {nome} em MODO SIMULAÇÃO — nada se mexe a sério.")
    else:
        print(f"\n🤖 {nome} pronta. (Ligo-me ao robô no primeiro comando.)")
    print("   Escreve  ajuda()  para veres tudo o que ela sabe fazer.\n")


_apresentar()
