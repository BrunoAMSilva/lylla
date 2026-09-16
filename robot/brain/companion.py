"""O ROBÔ DE SECRETÁRIA — o que ele faz quando ninguém lhe pediu nada.

╔══════════════════════════════════════════════════════════════════════════╗
║  A LIÇÃO DO EILIK                                                        ║
║                                                                          ║
║  Dos três robôs de secretária que servem de referência — EMO, Eilik e    ║
║  Looi — o que as pessoas descrevem como mais VIVO é o Eilik. E o Eilik   ║
║  não tem câmara nenhuma. Tem três sensores de toque, expressões, e       ║
║  coisas que faz sozinho quando ninguém lhe liga: lê, pesca, faz          ║
║  exercício.                                                              ║
║                                                                          ║
║  Ou seja: a sensação de estar vivo não vem de reconhecer caras. Vem de   ║
║  REAGIR SEMPRE e de TER COISAS PARA FAZER. O reconhecimento de caras é   ║
║  o que torna a reação pessoal — é o bónus, não a base.                   ║
║                                                                          ║
║  Este módulo é a base. Corre em cada volta do ciclo principal, é barato, ║
║  e nunca fala sem ser chamado.                                           ║
╚══════════════════════════════════════════════════════════════════════════╝

    presente ──vê alguém──► segue com os olhos ──é a Lara?──► cumprimenta
        │                                                          │
        └──ninguém há 90 s──► entretém-se sozinho ◄────────────────┘
"""

from __future__ import annotations

import random
import time

from robot import config
from robot.hardware import arms, eyes, glow, motors, sensors
from robot.perception import attention

_ultimo_olhar = 0.0
_ultima_presenca = 0.0
_ultima_atividade = 0.0
_ja_cumprimentou: dict[str, float] = {}
_indice_atividade = 0
_a_seguir = True


def _cfg(chave: str, omissao):
    return config.obter(f"secretaria.{chave}", omissao)


def _pausa(segundos: float) -> None:
    """Espera — exceto em simulação, onde não há nada por que esperar."""
    if not config.a_simular():
        time.sleep(segundos)


def ligada() -> bool:
    return bool(_cfg("ativa", True))


# ---------------------------------------------------------------------------
# PRIVACIDADE — a Lara manda
# ---------------------------------------------------------------------------

def parar_de_seguir() -> str:
    """Desliga a câmara. Chamado pela voz ("para de olhar") ou por ferramenta.

    Nenhuma imagem sai da rede de casa em momento nenhum (§10.3), mas isso é
    uma promessa do software. Isto é o interruptor: a Lara diz e ele obedece,
    e os olhos deixam de mostrar o ponto — vê-se que parou.
    """
    global _a_seguir
    _a_seguir = False
    attention.esquecer()
    eyes.expressao("a_dormir")
    return "Pronto, deixei de olhar."


def voltar_a_seguir() -> str:
    global _a_seguir
    _a_seguir = True
    attention.esquecer()
    eyes.expressao("neutro")
    return "Já estou a ver outra vez."


def esta_a_seguir() -> bool:
    return _a_seguir


# ---------------------------------------------------------------------------
# ATIVIDADES — o que ele faz quando está sozinho
# ---------------------------------------------------------------------------

def _bocejar() -> None:
    eyes.animar("bocejar")


def _espreitar() -> None:
    """Olha à volta, como quem procura alguém."""
    for x, y in ((-0.8, 0.0), (0.8, 0.0), (0.0, -0.5), (0.0, 0.0)):
        eyes.olhar_para(x, y)
        _pausa(0.45)


def _esticar_os_bracos() -> None:
    arms.gesto("espreguicar")


def _distrair_se() -> None:
    eyes.animar("entediado")


def _dar_uma_volta() -> None:
    """Uma voltinha no sítio. SÓ roda — nunca anda em frente.

    ⚠️ Numa secretária, rodar no sítio não pode cair de lado nenhum. Andar em
       frente pode. Por isso a atividade ociosa é sempre uma rotação, e mesmo
       assim só acontece se os sensores de precipício disserem que sim.
    """
    if not _cfg("andar", True):
        return
    if config.obter("seguranca.verificar_precipicio", True) and sensors.ha_precipicio():
        eyes.expressao("surpreso")
        return
    # ⚠️ mover() em vez de virar_graus(): virar_graus usa a velocidade do
    #    config, que é a de andar no chão. Na secretária queremos MUITO menos.
    v = float(_cfg("velocidade_max", 0.25))
    lado = random.choice((-1, 1))
    motors.mover(-v * lado, v * lado)
    _pausa(float(_cfg("duracao_voltinha_s", 0.35)))
    motors.parar()


ATIVIDADES = (
    ("bocejar", _bocejar),
    ("espreitar", _espreitar),
    ("esticar os braços", _esticar_os_bracos),
    ("distrair-se", _distrair_se),
    ("dar uma volta", _dar_uma_volta),
)


def _entreter_se() -> str | None:
    """Faz uma coisa. Sempre a seguinte da lista, nunca duas iguais seguidas."""
    global _indice_atividade, _ultima_atividade

    intervalo = float(_cfg("intervalo_atividades_s", 45.0))
    if time.monotonic() - _ultima_atividade < intervalo:
        return None

    nome, funcao = ATIVIDADES[_indice_atividade % len(ATIVIDADES)]
    _indice_atividade += 1
    _ultima_atividade = time.monotonic()
    try:
        funcao()
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  A atividade '{nome}' falhou: {erro}")
        motors.parar()
    return nome


# ---------------------------------------------------------------------------
# O CICLO
# ---------------------------------------------------------------------------

def tick(maquina=None, mexer: bool = True) -> attention.Observacao:
    """Uma volta do comportamento de secretária.

    Chamado do ciclo principal ~10x por segundo. Não bloqueia, não fala, e
    devolve o que viu para quem quiser usar.

    Com `mexer=False` continua a VER e a olhar — só não se entretém sozinho,
    que é a única parte que precisa de motores e braços.
    """
    global _ultima_presenca

    if not ligada() or not _a_seguir:
        return attention.Observacao()

    agora = time.monotonic()
    if agora - _ultimo_olhar < 1.0 / float(_cfg("fps_deteccao", 10)):
        return attention.Observacao()

    obs = _observar_agora()

    if obs.presente:
        _ultima_presenca = agora
        eyes.olhar_para(obs.x, obs.y)
        if obs.chegou_agora:
            _reagir_a_chegada(obs)
    elif obs.saiu_agora:
        eyes.expressao("neutro", olhar=(0.0, 0.0))
    else:
        sozinho_ha = agora - _ultima_presenca
        if mexer and sozinho_ha > float(_cfg("segundos_ate_atividade", 90.0)):
            _entreter_se()

    return obs


def _observar_agora() -> attention.Observacao:
    global _ultimo_olhar
    _ultimo_olhar = time.monotonic()
    return attention.observar()


def _reagir_a_chegada(obs: attention.Observacao) -> None:
    """Alguém chegou. Reage SEMPRE — mas só com a cara, nunca com a boca.

    ⚠️ Não fala. Foi decisão do projeto: o robô vive na secretária onde a Lara
       estuda, e um robô que comenta sozinho de cinco em cinco minutos deixa
       de ser companhia e passa a ser interrupção. Falar exige a palavra-chave.
    """
    if obs.nome:
        agora = time.monotonic()
        arrefecimento = float(_cfg("arrefecimento_saudacao_s", 900.0))
        if agora - _ja_cumprimentou.get(obs.nome, -1e9) > arrefecimento:
            _ja_cumprimentou[obs.nome] = agora
            eyes.animar("gosto_de_ti")
            arms.acenar(1)
            glow.pulsar("peito")
            return
        eyes.expressao("contente", olhar=(obs.x, obs.y))
    else:
        eyes.expressao("surpreso", olhar=(obs.x, obs.y))


def reiniciar() -> None:
    """Para os testes."""
    global _ultimo_olhar, _ultima_presenca, _ultima_atividade
    global _indice_atividade, _a_seguir
    _ultimo_olhar = 0.0
    _ultima_presenca = time.monotonic()
    _ultima_atividade = 0.0
    _indice_atividade = 0
    _a_seguir = True
    _ja_cumprimentou.clear()
    attention.esquecer()
