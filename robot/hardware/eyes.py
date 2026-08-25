"""OS OLHOS — painel HUB75 64×32 RGB, comandado por um ESP32.

╔══════════════════════════════════════════════════════════════════════════╗
║  PORQUÊ UM SEGUNDO PROCESSADOR SÓ PARA A CARA                            ║
║                                                                          ║
║  Um painel HUB75 não tem memória: é preciso reenviar-lhe as 2048 cores   ║
║  linha a linha, centenas de vezes por segundo, com temporização certa.   ║
║  Se o Raspberry Pi fizesse isso, gastava um core inteiro e a imagem      ║
║  tremia sempre que o Whisper arrancasse.                                 ║
║                                                                          ║
║  Então dividimos outra vez, como fizemos com o LLM:                      ║
║                                                                          ║
║    ESP32  →  DESENHA. Renderiza a 60 fps, faz a transição suave entre    ║
║              caras, pisca sozinho e "respira". É a única coisa que faz.  ║
║    Pi     →  DIZ O NOME. `expressao("feliz")` são ~40 bytes na série.    ║
║                                                                          ║
║  Custo para o Pi: praticamente zero. E a animação fica mais fluida do    ║
║  que ficaria se o Pi a fizesse, porque o ESP32 não tem mais nada que     ║
║  fazer.                                                                  ║
║                                                                          ║
║  Bónus: zero pinos GPIO do Pi usados. O HUB75 precisaria de 13, e quatro ║
║  deles chocavam com os pinos dos nossos sensores.                        ║
╚══════════════════════════════════════════════════════════════════════════╝

O protocolo é de texto, uma linha por comando, de propósito: dá para o
depurar com um terminal série e ver exatamente o que o Pi mandou.

    E <nome> <rx> <ry> <ab_esq> <ab_dir> <red> <rot> <arco> <cheio> <ox> <oy> <cor>
    F <forma> <cor>            formas especiais: coracao, arranque
    B <0|1>                    piscar automático
    L <0-100>                  brilho
    P                          ping — o ESP32 responde OK
"""

from __future__ import annotations

import atexit
import threading
import time

from robot import config
from robot.expressions import ANIMACOES, EXPRESSOES, morph_ms, parametros

_porta = None
_iniciada = False
_lock = threading.Lock()
_expressao_atual = "a_dormir"
_olhar_atual: tuple[float, float] = (0.0, 0.0)
_avisou = False

# Quanto o olhar tem de mudar para valer a pena mandar uma linha nova.
# 0.08 em -1..1 são ~4% da largura do painel: menos do que isso não se vê.
LIMIAR_OLHAR = 0.08


def _abrir():
    """Liga-se ao ESP32 pela porta série. Devolve None se não estiver lá."""
    global _porta, _iniciada, _avisou
    if _iniciada or config.a_simular():
        _iniciada = True
        return _porta
    _iniciada = True
    try:
        import serial

        caminho = config.obter("cara.porta", "/dev/ttyUSB0")
        _porta = serial.Serial(
            caminho,
            int(config.obter("cara.baud", 115200)),
            timeout=0.5,
            write_timeout=0.5,
        )
        time.sleep(2.0)  # o ESP32 reinicia quando a porta abre
        _porta.reset_input_buffer()
        _enviar_bruto(f"L {int(config.obter('cara.brilho', 40))}")
        _enviar_bruto(f"M {morph_ms()}")
    except Exception as erro:  # noqa: BLE001
        if not _avisou:
            _avisou = True
            print(
                f"⚠️  Não encontrei a cara ({erro}).\n"
                f"    O ESP32 está ligado por USB? Confirma a porta com:\n"
                f"      ls /dev/ttyUSB* /dev/ttyACM*\n"
                f"    O robô funciona à mesma — só fica sem cara."
            )
        _porta = None
    return _porta


def _enviar_bruto(linha: str) -> None:
    if _porta is None:
        return
    try:
        _porta.write((linha + "\n").encode("ascii", "replace"))
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Falha a falar com a cara: {erro}")


def _enviar(linha: str) -> None:
    with _lock:
        _abrir()
        _enviar_bruto(linha)


# ---------------------------------------------------------------------------
# A API — é esta que se usa em todo o lado
# ---------------------------------------------------------------------------

def expressao(nome: str, olhar: tuple[float, float] | None = None) -> None:
    """Muda a cara do robô. O ESP32 faz a transição suave sozinho.

    >>> expressao("feliz")
    >>> expressao("feliz", olhar=(0.6, -0.2))   # feliz, a olhar para a direita

    O `olhar` é (x, y), cada um de -1 a 1, e sobrepõe-se ao que a cara traz do
    config/expressoes.yaml. É isto que faz o robô SEGUIR uma pessoa com os
    olhos sem mudar de expressão — a coisa mais barata que existe para um robô
    de secretária parecer vivo.
    """
    global _expressao_atual, _olhar_atual
    p = parametros(nome)  # levanta ValueError com mensagem clara se não existir
    _expressao_atual = nome

    ox, oy = p["olhar_x"], p["olhar_y"]
    if olhar is not None:
        ox = max(-1.0, min(1.0, float(olhar[0])))
        oy = max(-1.0, min(1.0, float(olhar[1])))
    _olhar_atual = (ox, oy)

    if p["forma"] != "olhos":
        linha = f"F {p['forma']} {p['cor']}"
    else:
        linha = (
            f"E {nome} {p['rx']:.2f} {p['ry']:.2f} "
            f"{p['abertura_esq']:.2f} {p['abertura_dir']:.2f} "
            f"{p['redondeza']:.2f} {p['rotacao']:.2f} {p['arco']:.2f} "
            f"{p['cheio']:.2f} {ox:.2f} {oy:.2f} {p['cor']}"
        )

    if config.a_simular():
        alvo = "" if olhar is None else f"  olhar=({ox:+.2f},{oy:+.2f})"
        config.sim(f"cara → {nome}  (#{p['cor']}){alvo}")
        return
    _enviar(linha)


def olhar_para(x: float, y: float) -> None:
    """Mexe só os olhos, mantendo a expressão que já lá está.

    ⚠️ Não faz nada se o olhar quase não mudou. Sem isto, o ciclo de atenção
       mandaria 10 linhas por segundo pela série a dizer praticamente a mesma
       coisa — e o morph do ESP32 nunca chegaria ao fim, deixando os olhos
       permanentemente a meio caminho.
    """
    ax, ay = _olhar_atual
    if abs(x - ax) < LIMIAR_OLHAR and abs(y - ay) < LIMIAR_OLHAR:
        return
    expressao(_expressao_atual, olhar=(x, y))


def olhar_atual() -> tuple[float, float]:
    return _olhar_atual


def animar(nome: str) -> None:
    """Corre uma animação — uma sequência de caras com pausas."""
    if nome not in ANIMACOES:
        raise ValueError(
            f"Não existe a animação '{nome}'.\n"
            f"As que existem são: {', '.join(sorted(ANIMACOES))}\n"
            f"(Podes criar novas em config/expressoes.yaml)"
        )
    for passo, pausa in ANIMACOES[nome]:
        expressao(passo)
        # Em simulação não há painel para esperar. Sem isto, `pytest` demorava
        # 20 segundos em vez de 1 — e testes lentos deixam de se correr.
        if pausa and not config.a_simular():
            time.sleep(pausa)


def piscar() -> None:
    """Uma piscadela avulsa. (O piscar normal é automático — ver abaixo.)"""
    anterior = _expressao_atual
    expressao("a_piscar")
    time.sleep(0.09)
    expressao(anterior)


def comecar_a_piscar_sozinho() -> None:
    """Manda o ESP32 piscar por iniciativa própria.

    ⚠️ Isto acontece NO ESP32, não aqui. Um piscar comandado pelo Pi ficaria
       irregular sempre que o Whisper ou o OpenCV apanhassem o CPU — e um
       robô que pisca a soluçar parece avariado, não vivo.
    """
    if config.a_simular():
        config.sim("cara → piscar automático ligado")
        return
    _enviar("B 1")


def brilho(percentagem: int) -> None:
    """0 a 100. Baixo à noite, alto de dia."""
    percentagem = max(0, min(100, int(percentagem)))
    if config.a_simular():
        config.sim(f"cara → brilho {percentagem}%")
        return
    _enviar(f"L {percentagem}")


def atual() -> str:
    return _expressao_atual


def disponivel() -> bool:
    """O ESP32 responde?"""
    if config.a_simular():
        return True
    with _lock:
        if _abrir() is None:
            return False
        try:
            _porta.reset_input_buffer()
            _enviar_bruto("P")
            return b"OK" in _porta.readline()
        except Exception:  # noqa: BLE001
            return False


def apagar() -> None:
    """Apaga o painel. Chamado sempre que o programa termina."""
    global _porta
    if config.a_simular():
        config.sim("cara → apagada")
        return
    if _porta is not None:
        try:
            _enviar_bruto("L 0")
            time.sleep(0.05)
            _porta.close()
        except Exception:  # noqa: BLE001, S110
            pass
        _porta = None


atexit.register(apagar)
