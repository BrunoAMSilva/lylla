"""O QUE O ROBÔ SABE NESTE MOMENTO — o contexto que vai com cada pergunta.

Antes, para saber quem estava à frente, o LLM tinha de pedir uma ferramenta,
esperar pelo resultado e pensar outra vez: duas voltas pela rede para uma
coisa que o Pi já sabia. Agora vai tudo na primeira mensagem.

Barato de propósito: só lê o que já está em memória ou custa milissegundos.
Nada aqui pode demorar — isto corre antes de CADA frase.
"""

from __future__ import annotations

import time


def montar(maquina=None, obs=None, pessoa: str | None = None) -> dict:
    """O contexto para o cérebro. Nunca levanta: um sensor avariado não pode
    impedir o robô de responder.

    ⚠️ Se receber uma observação (`obs`) do modo secretária, usa-a em vez de
       tirar uma foto nova. Isto está no caminho crítico — corre depois de a
       Lara acabar de falar e antes de o pedido sair — e o `companion.tick()`
       já olhou há décimas de segundo. Tirar outra foto aqui era somar 50 a
       100 ms ao silêncio antes da resposta, por uma informação que já
       tínhamos.
    """
    from robot import config
    from robot.brain import companion, follow
    from robot.hardware import motors, power, sensors

    contexto: dict = {}

    if pessoa is None and obs is not None:
        pessoa = obs.nome if getattr(obs, "presente", False) else None
    elif pessoa is None and companion.esta_a_seguir():
        try:
            from robot.perception import faces

            pessoa = faces.quem_esta_a_ver()
        except Exception:  # noqa: BLE001
            pessoa = None
    if pessoa is None and maquina is not None and getattr(maquina, "pessoa", None):
        # Ninguém à vista agora, mas há dois segundos estava alguém a falar
        # com ele — e a pessoa continua a ser essa. Um robô que se esquece de
        # com quem estava a falar assim que ela desvia a cara parece avariado.
        if getattr(maquina, "tempo_sem_interacao", 999) < 30:
            pessoa = maquina.pessoa
    contexto["pessoa"] = pessoa      # None diz ao cérebro "não vês ninguém"

    try:
        pct = power.percentagem()
        if pct is not None:
            contexto["bateria_pct"] = pct
    except Exception:  # noqa: BLE001
        pass

    if not config.a_simular():
        try:
            distancia = sensors.distancia_cm()
            if distancia is not None:
                contexto["distancia_cm"] = round(float(distancia))
        except Exception:  # noqa: BLE001
            pass

    try:
        contexto["modo"] = motors.modo_atual()
    except Exception:  # noqa: BLE001
        pass

    if follow.a_seguir():
        contexto["a_seguir"] = True
    if not companion.esta_a_seguir():
        contexto["nota"] = "a câmara está desligada porque te pediram para não olhares"
    contexto["hora"] = time.strftime("%H:%M")
    return contexto
