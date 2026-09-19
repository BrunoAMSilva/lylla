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

A LISTA de ações (nomes, argumentos, limites) vive em robot/brain/acoes.py —
é o contrato entre o Pi e o cérebro no mac mini, e os dois leem-no do mesmo
ficheiro. Aqui ficam só as IMPLEMENTAÇÕES: o que cada ação faz ao hardware,
e a validação de segurança (sensores, precipício) que só o Pi pode fazer.

Há implementações a mais em relação ao catálogo (expressao, quem_esta_aqui,
distancia_a_frente, quanta_bateria). Já não são ações do LLM — o Pi manda
essa informação no `contexto` de cada pergunta, o que poupa uma volta pela
rede — mas continuam a servir aos scripts de teste e aos comandos diretos.
"""

from __future__ import annotations

import inspect

from robot.brain import acoes, follow
from robot.expressions import EXPRESSOES
from robot.gestures import GESTOS
from robot.hardware import arms, eyes, glow, motors, power, sensors
from robot.navigation import ir_para as navegar
from robot.navigation import procurar

# ---------------------------------------------------------------------------
# O catálogo, no formato de tool calling do Ollama (para experiências; o
# cérebro usa a saída estruturada — ver acoes.esquema_json)
# ---------------------------------------------------------------------------

FERRAMENTAS = acoes.ferramentas_ollama()


# ---------------------------------------------------------------------------
# As implementações — cada uma valida antes de agir
# ---------------------------------------------------------------------------


class Recusa(str):
    """Uma resposta que quer dizer «NÃO fiz o que me pediste».

    Continua a ser uma string em todo o lado — imprime-se, formata-se e vai
    para o LLM exatamente como antes. Serve só para quem chama poder
    distinguir, sem adivinhar pelo texto:

      · «Andei 20 cm.»                    → o robô já disse o que ia fazer.
                                             Falar isto outra vez é repetir-se.
      · «Não posso, está aí uma parede.»  → TEM de sair em voz alta, senão o
                                             robô fica parado sem explicação.

    Antes isto adivinhava-se por `resultado.startswith("Não")`, o que falha à
    primeira frase que comece de outra maneira.
    """

def _mover(direcao: str = "frente", cm: int = 20, **_) -> str:
    if direcao not in ("frente", "tras"):
        return Recusa(f"I don't know what '{direcao}' means. I can only go forward or back.")
    # ⚠️ Um valor que não se percebe é uma RECUSA, não os 20 cm por omissão.
    #    Cair no valor por omissão é o robô inventar uma ordem que ninguém
    #    deu — e a única maneira de o notarmos era vê-lo andar. O _virar já
    #    fazia isto bem; o _mover não.
    try:
        cm = int(cm)
    except (TypeError, ValueError, OverflowError):
        return Recusa("I didn't get how many centimetres.")
    if not 5 <= cm <= 50:
        return Recusa(f"{cm} centimetres is too much. I only move 5 to 50 centimetres at a time.")

    # A segurança física manda sempre mais que o LLM.
    if direcao == "frente" and not sensors.caminho_livre():
        eyes.expressao("surpreso")
        return Recusa("I can't, something is in front of me!")
    if sensors.ha_precipicio():
        return Recusa("I can't, I'm right at an edge!")

    motors.andar_cm(cm if direcao == "frente" else -cm)
    return f"I moved {cm} centimetres {'forward' if direcao == 'frente' else 'back'}."


def _virar(graus: int = 90, **_) -> str:
    try:
        graus = int(graus)
    except (TypeError, ValueError):
        return Recusa("I didn't get how many degrees.")
    if not -180 <= graus <= 180:
        return Recusa(f"{graus} degrees is too much. I only turn up to 180.")
    if sensors.ha_precipicio():
        return Recusa("I won't move, I'm right at an edge!")
    motors.virar_graus(graus)
    return f"I turned {abs(graus)} degrees to the {'right' if graus > 0 else 'left'}."


def _expressao(nome: str = "neutro", **_) -> str:
    if nome not in EXPRESSOES:
        return Recusa(f"I don't know the face '{nome}'. I know: {', '.join(sorted(EXPRESSOES))}.")
    eyes.expressao(nome)
    return f"Now I look {nome.replace('_', ' ')}."


def _quem_esta_aqui(**_) -> str:
    from robot.perception import faces

    nome = faces.quem_esta_a_ver()
    return f"It's {nome}." if nome else "I don't see anyone I know."


def _distancia(**_) -> str:
    return f"The closest thing is {sensors.distancia_cm():.0f} centimetres away."


def _gesto(nome: str = "acenar", **_) -> str:
    if nome not in GESTOS:
        return Recusa(f"I don't know the gesture '{nome}'. I know: {', '.join(sorted(GESTOS))}.")
    arms.gesto(nome)
    return f"I did the gesture: {nome.replace('_', ' ')}."


def _apontar(direcao: str = "frente", **_) -> str:
    try:
        arms.apontar(direcao)
    except ValueError as erro:
        print(f"   ↯ apontar: {erro}")
        return Recusa("I can't point there.")
    return f"I pointed {({'esquerda': 'left', 'direita': 'right', 'cima': 'up'}).get(direcao, 'ahead')}."


def _garra(acao: str = "abrir", **_) -> str:
    if acao not in ("abrir", "fechar"):
        return Recusa("My hand can only open or close.")
    arms.garra(acao)
    return "I opened my hand." if acao == "abrir" else "I closed my hand."


def _bateria(**_) -> str:
    pct = power.percentagem()
    if pct is None:
        return Recusa("I can't measure my battery.")
    if pct <= 20:
        return f"I have {pct}% battery. I'm hungry!"
    return f"I have {pct}% battery."


def _dancar(**_) -> str:
    import time

    if sensors.ha_precipicio():
        return Recusa("I won't dance here, I'm right at an edge!")
    if not sensors.caminho_livre():
        eyes.expressao("surpreso")
        return Recusa("I don't have room to dance. Put me somewhere more open!")
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
    # ⚠️ `expressao`, não `animar`: "contente" é uma CARA (config/expressoes.yaml
    #    → expressoes), não uma animação. O animar() levantava ValueError e a
    #    dança acabava com o robô a recitar a lista de animações que existem.
    #    Passou despercebido enquanto o resultado das ações não era falado.
    eyes.expressao("contente")
    glow.respirar("base")
    return "I danced!"


def _seguir(acao: str = "comecar", **_) -> str:
    """Liga ou desliga o modo seguir. A conta de segurança (D17) manda:
    com `seguir.ativo: false` no robot.yaml, o pedido é recusado com
    palavras, não ignorado em silêncio."""
    if acao not in ("comecar", "parar"):
        return Recusa("I can only start or stop following.")
    if acao == "parar":
        follow.parar()
        return "I'm staying here."
    if not follow.permitido():
        return Recusa("I'm not allowed to follow people yet. I'll stay here with you.")
    if sensors.ha_precipicio():
        return Recusa("I can't, I'm right at an edge!")
    follow.comecar()
    eyes.expressao("atento")
    return "I'm coming with you!"


def _ir_para(sitio: str = "", estou_aqui: bool = False, **_) -> str:
    """Manda-a atravessar a casa até uma divisão.

    Aqui não há conta nenhuma: quem decide é o robot/navigation/ir_para.py,
    que tem a planta, o piloto treinado e — sobretudo — os sensores por cima
    de tudo. Esta função só traduz o resultado para uma frase.
    """
    if not isinstance(sitio, str) or not sitio.strip():
        return Recusa("You didn't tell me where to go.")

    # «Estás na cozinha» — não é uma viagem, é uma correção. E se estivermos a
    # meio de um jogo às escondidas, é a resposta que ele estava à espera.
    if estou_aqui in (True, "true", "True", 1):
        if procurar.a_perguntar():
            estado, mensagem = procurar.responder(sitio)
            return mensagem if estado != "recusa" else Recusa(mensagem)
        erro = navegar.assumir(sitio)
        return Recusa(erro) if erro else f"Okay, I'm {navegar.em_ingles(sitio, 'em')}."

    if sensors.ha_precipicio():
        return Recusa("I can't, I'm right at an edge!")
    estado, mensagem = navegar.comecar(sitio)
    if estado == "recusa":
        return Recusa(mensagem)
    if estado == "ja_estou":
        eyes.expressao("contente")
        return mensagem
    eyes.expressao("atento")
    return mensagem


def _ver_caras(so_conhecidas: bool = False, **_) -> str:
    """Olha AGORA. Não usa o contexto: a pergunta é sobre este instante."""
    from robot.perception import faces

    if not faces.disponivel():
        return Recusa("My eyes aren't working, I can't see anything.")
    try:
        from robot.perception import camera

        imagem = camera.tirar_foto()
    except Exception as erro:  # noqa: BLE001
        return Recusa(f"I couldn't take the photo: {erro}")
    if imagem is None:
        return Recusa("My camera didn't give me a picture.")

    caras = faces.detetar(imagem)
    if not caras:
        return "I don't see any faces."

    nome = faces.quem_esta_a_ver(imagem)
    if so_conhecidas:
        return f"Yes, it's {nome}." if nome else "I see a face, but I don't know who it is."
    quantas = ("one face" if len(caras) == 1 else f"{len(caras)} faces")
    return f"I see {quantas}" + (f", and one is {nome}." if nome else ", but I don't know anyone.")


def _registar_cara(nome: str = "", **_) -> str:
    """O registo inteiro por voz (ver perception/registo.py). Ele próprio diz
    tudo, incluindo o resultado — por isso nada daqui volta a ser falado."""
    from robot.hardware import glow
    from robot.perception import registo
    from robot.voice import listen, speak

    # `esperar=True`: cada pose tem de ser OUVIDA antes de a foto sair. Com a
    # fila assíncrona o robô tirava as oito fotos enquanto ainda dizia a
    # primeira instrução.
    return registo.registar_pela_voz(
        nome, lambda t: speak.falar(t, esperar=True),
        ouvir=lambda: listen.ouvir(ao_progresso=glow.progresso_escuta))


def _volume(percentagem: int = 70, **_) -> str:
    from robot.voice import speak

    ficou = speak.definir_volume(int(percentagem) / 100.0)
    if ficou == 0:
        return "I'm quiet now. Tell me to talk again."
    return f"Volume at {round(ficou * 100)} percent."


def _piscar_luzes(vezes: int = 3, **_) -> str:
    import time

    if not glow.disponivel():
        return Recusa("I don't have any lights connected.")
    antes = glow.nivel_atual().get("base", 0.0)
    glow.parar_animacao()
    for _i in range(int(vezes)):
        glow.tudo(1.0)
        time.sleep(0.12)
        glow.tudo(0.0)
        time.sleep(0.12)
    glow.tudo(antes)
    return f"I blinked {int(vezes)} times."


def _diagnostico(**_) -> str:
    """O que está mesmo ligado. Sem isto, «não consigo» pode ser qualquer coisa."""
    from robot.hardware import mbot2
    from robot.perception import camera, faces

    tenho, faltam = [], []
    for etiqueta, presente in (
        ("the mBot2 chassis", mbot2.disponivel()),
        ("the camera", camera.disponivel()),
        ("face recognition", faces.disponivel()),
        ("the arms", arms.disponivel()),
        ("the lights", glow.disponivel()),
    ):
        (tenho if presente else faltam).append(etiqueta)

    partes = []
    if tenho:
        partes.append("I have " + ", ".join(tenho) + ".")
    if faltam:
        partes.append("I'm missing " + ", ".join(faltam) + ".")
    return " ".join(partes) or "I can't check anything."


def _olhar(direcao: str = "frente", **_) -> str:
    destinos = {
        "frente": (0.0, 0.0), "esquerda": (-0.8, 0.0), "direita": (0.8, 0.0),
        "cima": (0.0, -0.7), "baixo": (0.0, 0.6),
    }
    x, y = destinos.get(direcao, (0.0, 0.0))
    eyes.olhar_para(x, y)
    return f"Looking {({'esquerda': 'left', 'direita': 'right', 'cima': 'up', 'baixo': 'down'}).get(direcao, 'ahead')}."


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
    "seguir": _seguir,
    "ir_para": _ir_para,
    "ver_caras": _ver_caras,
    "registar_cara": _registar_cara,
    "volume": _volume,
    "piscar_luzes": _piscar_luzes,
    "diagnostico": _diagnostico,
    "olhar": _olhar,
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
        return Recusa(f"I don't know how to do '{nome}'.")
    if not isinstance(argumentos, dict):
        argumentos = {}

    # O contrato primeiro: se a ação está no catálogo, os argumentos têm de
    # bater certo com ele. O cérebro já filtrou, mas o Pi é quem mexe os
    # motores — e quem mexe os motores não confia em ninguém.
    if nome in acoes.ACOES:
        ok, razao = acoes.validar({"nome": nome, "argumentos": argumentos})
        if not ok:
            # A razão fica no terminal: vem em português do acoes.py, e a voz
            # é inglesa. Em voz alta chega dizer que não.
            print(f"   ↯ {nome}: {razao}")
            return Recusa("I can't do it like that.")

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
        return Recusa(f"I tried but I couldn't: {erro}")
