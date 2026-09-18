"""A LYLLA, para escrever de uma linha só.

    python3
    >>> from lylla import *
    >>> ajuda()
    >>> andar(30)

São duas maneiras de usar isto, e são as duas boas:

  1. O VOCABULÁRIO SIMPLES — `from lylla import *` e os comandos ficam à mão,
     sem pontos nem pastas. É por aqui que se começa.

  2. AS BIBLIOTECAS — quando a função já é grande, importa-se só o que ela
     precisa, e o código fica a dizer de onde vem cada coisa:

         from lylla import comando, ver, voz, mover

         @comando("adicionar face")
         def adicionar_face():
             voz.dizer("What's your name?")
             nome = voz.ouvir()
             ver.guardar_face(nome, aviso=voz.dizer)

As bibliotecas são: `mover` (rodas) · `ver` (câmara e caras) · `voz` (falar e
ouvir) · `luzes` (olhos e cores) · `comandos` (ensinar frases novas).

⚠️ A complexidade fica toda em baixo, de propósito: ligação série ao mBot2,
   subscrições, malha fechada, deteção de caras. Quem quiser ver o motor por
   dentro abre o robot/hardware/mbot2.py ou o robot/perception/faces.py.

Para experimentar sem o robô (no Mac, por exemplo):

    ROBO_SIMULAR=1 python3 -c "from lylla import *; andar(30)"
"""

from __future__ import annotations

from robot import config

from lylla import comandos, luzes, mover, ver, voz
from lylla.comandos import comando
from lylla.luzes import luz, olhos
from lylla.mover import (
    andar,
    caminho_livre,
    depressa,
    devagar,
    distancia,
    em_cima_da_mesa,
    no_chao,
    normal,
    parar,
    quanto_andei,
    recuar,
    virar_direita,
    virar_esquerda,
    zerar,
)
from lylla.voz import dizer, esperar, ouvir

__all__ = [
    "ajuda", "andar", "recuar", "virar_esquerda", "virar_direita", "parar",
    "devagar", "normal", "depressa", "distancia", "caminho_livre",
    "olhos", "luz", "dizer", "ouvir", "esperar", "quanto_andei", "zerar",
    "em_cima_da_mesa", "no_chao", "estado", "comando",
    "mover", "ver", "voz", "luzes", "comandos",
]


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

  FALAR E OUVIR
    dizer("hello Lara")
    ouvir()            ouve uma frase e devolve o texto
    esperar(2)         espera 2 segundos

  ONDE ESTÁ O ROBÔ
    em_cima_da_mesa()  limita a velocidade (uma queda parte-o)
    no_chao()          velocidade normal

  E AINDA
    ajuda()            este mapa
    estado()           bateria, distância, quanto andou

  AS BIBLIOTECAS, para funções maiores:
    mover · ver · voz · luzes · comandos     (e o decorador `comando`)

    from lylla import comando, ver, voz

    @comando("adicionar face")
    def adicionar_face():
        voz.dizer("What's your name?")
        nome = voz.ouvir()
        ver.guardar_face(nome, aviso=voz.dizer)
        return f"Já conheço a {nome}!"

  EXPERIMENTA ISTO — um quadrado:

      for lado in range(4):
          andar(30)
          virar_direita()

  Repara: `andar` DEVOLVE quantos centímetros andou mesmo.

      andou = andar(30)
      print("pedi 30 e ele andou", andou)
""")


def estado() -> dict[str, object]:
    """Um retrato do robô: bateria, distância, quanto andou."""
    from robot.hardware import mbot2

    return mbot2.estado()


def _apresentar() -> None:
    nome = config.nome_do_robo()
    if config.a_simular():
        print(f"\n🤖 {nome} em MODO SIMULAÇÃO — nada se mexe a sério.")
    else:
        print(f"\n🤖 {nome} pronta. (Ligo-me ao robô no primeiro comando.)")
    print("   Escreve  ajuda()  para veres tudo o que ela sabe fazer.\n")


_apresentar()
