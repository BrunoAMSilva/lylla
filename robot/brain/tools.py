"""AS FERRAMENTAS — o que o LLM pode mandar o robô fazer.

╔══════════════════════════════════════════════════════════════════════════╗
║  A REGRA MAIS IMPORTANTE DESTE FICHEIRO                                  ║
║                                                                          ║
║  NUNCA executar uma ação sem validar os parâmetros primeiro.             ║
║                                                                          ║
║  O LLM é um programa que se convence, não um programa que se comanda.    ║
║  Pode devolver mover(cm=5000) com toda a confiança do mundo. A nossa     ║
║  função é recusar — não obedecer.                                        ║
║                                                                          ║
║  Isto não é paranoia: é a mesma razão por que um site nunca confia no    ║
║  que o browser lhe envia.                                                ║
╚══════════════════════════════════════════════════════════════════════════╝

Poucas ferramentas, com opções fechadas. Os modelos pequenos funcionam bem
com 6 a 8; acima disso começam a baralhar-se. Estamos em 10 — acima do
confortável. Se o robô começar a escolher mal as ações, os primeiros cortes
são: juntar `gesto` e `expressao` numa só, e tirar `distancia_a_frente`
(que o robô raramente precisa de anunciar em voz alta).
"""

from __future__ import annotations

import inspect

from robot.expressions import EXPRESSOES
from robot.gestures import GESTOS
from robot.hardware import arms, eyes, glow, motors, power, sensors

# ---------------------------------------------------------------------------
# Descrição no formato que o Ollama espera (JSON Schema)
# ---------------------------------------------------------------------------

FERRAMENTAS = [
    {
        "type": "function",
        "function": {
            "name": "mover",
            "description": "Faz o robô andar para a frente ou para trás.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direcao": {"type": "string", "enum": ["frente", "tras"]},
                    "cm": {
                        "type": "integer",
                        "description": "Distância em centímetros, entre 5 e 50.",
                    },
                },
                "required": ["direcao"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "virar",
            "description": "Roda o robô no lugar. Negativo = esquerda, positivo = direita.",
            "parameters": {
                "type": "object",
                "properties": {
                    "graus": {
                        "type": "integer",
                        "description": "Entre -180 e 180.",
                    }
                },
                "required": ["graus"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "expressao",
            "description": "Muda a cara do robô. Usa isto sempre que a emoção mudar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string", "enum": sorted(EXPRESSOES)},
                },
                "required": ["nome"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quem_esta_aqui",
            "description": "Olha com a câmara e diz quem é a pessoa que está à frente.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "distancia_a_frente",
            "description": "Mede a distância em centímetros ao obstáculo mais próximo.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gesto",
            "description": (
                "Faz um gesto com os braços. Usa isto sempre que for natural: "
                "acena ao cumprimentar, festeja quando há boas notícias, "
                "encolhe os ombros quando não sabes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string", "enum": sorted(GESTOS)},
                },
                "required": ["nome"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apontar",
            "description": "Aponta com o braço numa direção.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direcao": {
                        "type": "string",
                        "enum": ["esquerda", "direita", "cima", "frente"],
                    },
                },
                "required": ["direcao"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "garra",
            "description": "Abre ou fecha a mão do robô.",
            "parameters": {
                "type": "object",
                "properties": {
                    "acao": {"type": "string", "enum": ["abrir", "fechar"]},
                },
                "required": ["acao"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quanta_bateria",
            "description": "Diz quanta bateria resta ao robô.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dancar",
            "description": "Faz uma pequena dança alegre.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ---------------------------------------------------------------------------
# As implementações — cada uma valida antes de agir
# ---------------------------------------------------------------------------

def _mover(direcao: str = "frente", cm: int = 20, **_) -> str:
    if direcao not in ("frente", "tras"):
        return f"Não sei o que é '{direcao}'. Só sei ir para a frente ou para trás."
    try:
        cm = int(cm)
    except (TypeError, ValueError):
        cm = 20
    if not 5 <= cm <= 50:
        return f"{cm} cm é demasiado. Só ando entre 5 e 50 cm de cada vez."

    # A segurança física manda sempre mais que o LLM.
    if direcao == "frente" and not sensors.caminho_livre():
        eyes.expressao("surpreso")
        return "Não posso — está alguma coisa à minha frente!"
    if sensors.ha_precipicio():
        return "Não posso — estou à beira de uma queda!"

    motors.andar_cm(cm if direcao == "frente" else -cm)
    return f"Andei {cm} cm para {'a frente' if direcao == 'frente' else 'trás'}."


def _virar(graus: int = 90, **_) -> str:
    try:
        graus = int(graus)
    except (TypeError, ValueError):
        return "Não percebi quantos graus."
    if not -180 <= graus <= 180:
        return f"{graus} graus é demasiado. Só rodo entre -180 e 180."
    if sensors.ha_precipicio():
        return "Não me mexo — estou à beira de uma queda!"
    motors.virar_graus(graus)
    return f"Rodei {abs(graus)} graus para a {'direita' if graus > 0 else 'esquerda'}."


def _expressao(nome: str = "neutro", **_) -> str:
    if nome not in EXPRESSOES:
        return f"Não sei fazer a cara '{nome}'. Sei fazer: {', '.join(sorted(EXPRESSOES))}."
    eyes.expressao(nome)
    return f"Fiquei com cara de {nome.replace('_', ' ')}."


def _quem_esta_aqui(**_) -> str:
    from robot.perception import faces

    nome = faces.quem_esta_a_ver()
    return f"É a/o {nome}." if nome else "Não vejo ninguém que eu conheça."


def _distancia(**_) -> str:
    return f"O obstáculo mais próximo está a {sensors.distancia_cm():.0f} centímetros."


def _gesto(nome: str = "acenar", **_) -> str:
    if nome not in GESTOS:
        return f"Não sei fazer o gesto '{nome}'. Sei: {', '.join(sorted(GESTOS))}."
    arms.gesto(nome)
    return f"Fiz o gesto: {nome.replace('_', ' ')}."


def _apontar(direcao: str = "frente", **_) -> str:
    try:
        arms.apontar(direcao)
    except ValueError as erro:
        return str(erro)
    return f"Apontei para {direcao}."


def _garra(acao: str = "abrir", **_) -> str:
    if acao not in ("abrir", "fechar"):
        return "A minha mão só sabe abrir ou fechar."
    arms.garra(acao)
    return "Abri a mão." if acao == "abrir" else "Fechei a mão."


def _bateria(**_) -> str:
    pct = power.percentagem()
    if pct is None:
        return "Não consigo medir a minha bateria."
    if pct <= 20:
        return f"Tenho {pct}% de bateria. Estou com fome!"
    return f"Tenho {pct}% de bateria."


def _dancar(**_) -> str:
    import time

    if sensors.ha_precipicio():
        return "Aqui não danço — estou à beira de uma queda!"
    if not sensors.caminho_livre():
        eyes.expressao("surpreso")
        return "Não tenho espaço para dançar. Põe-me num sítio mais aberto!"
    eyes.expressao("feliz")
    glow.pulsar("base", periodo=0.35)
    for _i in range(2):
        motors.direita()
        arms.pose("festa")
        time.sleep(0.3)
        motors.esquerda()
        arms.pose("encolher_ombros")
        time.sleep(0.3)
    motors.parar()
    arms.pose("descanso")
    eyes.animar("contente")
    glow.respirar("base")
    return "Dancei!"


IMPLEMENTACOES = {
    "mover": _mover,
    "virar": _virar,
    "expressao": _expressao,
    "quem_esta_aqui": _quem_esta_aqui,
    "distancia_a_frente": _distancia,
    "gesto": _gesto,
    "apontar": _apontar,
    "garra": _garra,
    "quanta_bateria": _bateria,
    "dancar": _dancar,
}


def executar(nome: str, argumentos: dict) -> str:
    """Executa uma ação pedida pelo LLM, com validação.

    ⚠️ NUNCA RE-EXECUTAR. Uma versão anterior deste código apanhava o
       TypeError e voltava a chamar a função sem argumentos. Parecia
       defensivo, mas se o erro viesse de DENTRO da função — já depois de o
       robô ter andado — a segunda chamada mandava-o andar outra vez, com os
       valores por omissão. O robô fazia duas coisas por uma ordem.

       Em vez disso, filtramos os argumentos ANTES de chamar.
    """
    funcao = IMPLEMENTACOES.get(nome)
    if funcao is None:
        return f"Não sei fazer '{nome}'."
    if not isinstance(argumentos, dict):
        argumentos = {}

    # Deitar fora parâmetros que o LLM inventou, antes de chamar seja o que for.
    parametros = inspect.signature(funcao).parameters
    aceita_extra = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in parametros.values()
    )
    if not aceita_extra:
        argumentos = {k: v for k, v in argumentos.items() if k in parametros}

    try:
        return funcao(**argumentos)
    except Exception as erro:  # noqa: BLE001
        return f"Tentei mas não consegui: {erro}"
