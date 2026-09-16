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
        return Recusa(f"Não sei o que é '{direcao}'. Só sei ir para a frente ou para trás.")
    # ⚠️ Um valor que não se percebe é uma RECUSA, não os 20 cm por omissão.
    #    Cair no valor por omissão é o robô inventar uma ordem que ninguém
    #    deu — e a única maneira de o notarmos era vê-lo andar. O _virar já
    #    fazia isto bem; o _mover não.
    try:
        cm = int(cm)
    except (TypeError, ValueError, OverflowError):
        return Recusa("Não percebi quantos centímetros.")
    if not 5 <= cm <= 50:
        return Recusa(f"{cm} cm é demasiado. Só ando entre 5 e 50 cm de cada vez.")

    # A segurança física manda sempre mais que o LLM.
    if direcao == "frente" and not sensors.caminho_livre():
        eyes.expressao("surpreso")
        return Recusa("Não posso — está alguma coisa à minha frente!")
    if sensors.ha_precipicio():
        return Recusa("Não posso — estou à beira de uma queda!")

    motors.andar_cm(cm if direcao == "frente" else -cm)
    return f"Andei {cm} cm para {'a frente' if direcao == 'frente' else 'trás'}."


def _virar(graus: int = 90, **_) -> str:
    try:
        graus = int(graus)
    except (TypeError, ValueError):
        return Recusa("Não percebi quantos graus.")
    if not -180 <= graus <= 180:
        return Recusa(f"{graus} graus é demasiado. Só rodo entre -180 e 180.")
    if sensors.ha_precipicio():
        return Recusa("Não me mexo — estou à beira de uma queda!")
    motors.virar_graus(graus)
    return f"Rodei {abs(graus)} graus para a {'direita' if graus > 0 else 'esquerda'}."


def _expressao(nome: str = "neutro", **_) -> str:
    if nome not in EXPRESSOES:
        return Recusa(f"Não sei fazer a cara '{nome}'. Sei fazer: {', '.join(sorted(EXPRESSOES))}.")
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
        return Recusa(f"Não sei fazer o gesto '{nome}'. Sei: {', '.join(sorted(GESTOS))}.")
    arms.gesto(nome)
    return f"Fiz o gesto: {nome.replace('_', ' ')}."


def _apontar(direcao: str = "frente", **_) -> str:
    try:
        arms.apontar(direcao)
    except ValueError as erro:
        return Recusa(str(erro))
    return f"Apontei para {direcao}."


def _garra(acao: str = "abrir", **_) -> str:
    if acao not in ("abrir", "fechar"):
        return Recusa("A minha mão só sabe abrir ou fechar.")
    arms.garra(acao)
    return "Abri a mão." if acao == "abrir" else "Fechei a mão."


def _bateria(**_) -> str:
    pct = power.percentagem()
    if pct is None:
        return Recusa("Não consigo medir a minha bateria.")
    if pct <= 20:
        return f"Tenho {pct}% de bateria. Estou com fome!"
    return f"Tenho {pct}% de bateria."


def _dancar(**_) -> str:
    import time

    if sensors.ha_precipicio():
        return Recusa("Aqui não danço — estou à beira de uma queda!")
    if not sensors.caminho_livre():
        eyes.expressao("surpreso")
        return Recusa("Não tenho espaço para dançar. Põe-me num sítio mais aberto!")
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
    return "Dancei!"


def _seguir(acao: str = "comecar", **_) -> str:
    """Liga ou desliga o modo seguir. A conta de segurança (D17) manda:
    com `seguir.ativo: false` no robot.yaml, o pedido é recusado com
    palavras, não ignorado em silêncio."""
    if acao not in ("comecar", "parar"):
        return Recusa("Só sei começar ou parar de seguir.")
    if acao == "parar":
        follow.parar()
        return "Fiquei aqui."
    if not follow.permitido():
        return Recusa("Ainda não me deixam andar atrás de ninguém. Fico aqui contigo.")
    if sensors.ha_precipicio():
        return Recusa("Não posso — estou à beira de uma queda!")
    follow.comecar()
    eyes.expressao("atento")
    return "Vou atrás de ti!"


def _ir_para(sitio: str = "", estou_aqui: bool = False, **_) -> str:
    """Manda-a atravessar a casa até uma divisão.

    Aqui não há conta nenhuma: quem decide é o robot/navigation/ir_para.py,
    que tem a planta, o piloto treinado e — sobretudo — os sensores por cima
    de tudo. Esta função só traduz o resultado para uma frase.
    """
    if not isinstance(sitio, str) or not sitio.strip():
        return Recusa("Não me disseste para onde.")

    # «Estás na cozinha» — não é uma viagem, é uma correção. E se estivermos a
    # meio de um jogo às escondidas, é a resposta que ele estava à espera.
    if estou_aqui in (True, "true", "True", 1):
        if procurar.a_perguntar():
            estado, mensagem = procurar.responder(sitio)
            return mensagem if estado != "recusa" else Recusa(mensagem)
        erro = navegar.assumir(sitio)
        return Recusa(erro) if erro else f"Está bem, estou {navegar.com_artigo(sitio, 'em')}."

    if sensors.ha_precipicio():
        return Recusa("Não posso — estou à beira de uma queda!")
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
        return Recusa("Não tenho os olhos a funcionar — não consigo ver nada.")
    try:
        from robot.perception import camera

        imagem = camera.tirar_foto()
    except Exception as erro:  # noqa: BLE001
        return Recusa(f"Não consegui tirar a foto: {erro}")
    if imagem is None:
        return Recusa("A câmara não me deu imagem nenhuma.")

    caras = faces.detetar(imagem)
    if not caras:
        return "Não vejo cara nenhuma."

    nome = faces.quem_esta_a_ver(imagem)
    if so_conhecidas:
        return f"Sim, é {nome}." if nome else "Vejo uma cara, mas não sei de quem é."
    quantas = ("uma cara" if len(caras) == 1 else f"{len(caras)} caras")
    return f"Vejo {quantas}" + (f", e uma é a da {nome}." if nome else ", mas não conheço ninguém.")


def _registar_cara(nome: str = "", **_) -> str:
    from robot.perception import registo
    from robot.voice import speak

    # `esperar=True`: cada pose tem de ser OUVIDA antes de a foto sair. Com a
    # fila assíncrona o robô tirava as oito fotos enquanto ainda dizia a
    # primeira instrução.
    return registo.registar_pela_voz(nome, lambda t: speak.falar(t, esperar=True))


def _volume(percentagem: int = 70, **_) -> str:
    from robot.voice import speak

    ficou = speak.definir_volume(int(percentagem) / 100.0)
    if ficou == 0:
        return "Fiquei em silêncio. Diz-me para voltar a falar."
    return f"Volume nos {round(ficou * 100)} por cento."


def _piscar_luzes(vezes: int = 3, **_) -> str:
    import time

    if not glow.disponivel():
        return Recusa("Não tenho luzes ligadas.")
    antes = glow.nivel_atual().get("base", 0.0)
    glow.parar_animacao()
    for _i in range(int(vezes)):
        glow.tudo(1.0)
        time.sleep(0.12)
        glow.tudo(0.0)
        time.sleep(0.12)
    glow.tudo(antes)
    return f"Pisquei {int(vezes)} vezes."


def _diagnostico(**_) -> str:
    """O que está mesmo ligado. Sem isto, «não consigo» pode ser qualquer coisa."""
    from robot.hardware import mbot2
    from robot.perception import camera, faces

    tenho, faltam = [], []
    for etiqueta, presente in (
        ("o chassis do mBot2", mbot2.disponivel()),
        ("a câmara", camera.disponivel()),
        ("os olhos que reconhecem caras", faces.disponivel()),
        ("os braços", arms.disponivel()),
        ("as luzes", glow.disponivel()),
    ):
        (tenho if presente else faltam).append(etiqueta)

    partes = []
    if tenho:
        partes.append("Tenho " + ", ".join(tenho) + ".")
    if faltam:
        partes.append("Falta-me " + ", ".join(faltam) + ".")
    return " ".join(partes) or "Não consigo verificar nada."


def _olhar(direcao: str = "frente", **_) -> str:
    destinos = {
        "frente": (0.0, 0.0), "esquerda": (-0.8, 0.0), "direita": (0.8, 0.0),
        "cima": (0.0, -0.7), "baixo": (0.0, 0.6),
    }
    x, y = destinos.get(direcao, (0.0, 0.0))
    eyes.olhar_para(x, y)
    return f"A olhar para {'a ' + direcao if direcao != 'frente' else 'a frente'}."


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
        return Recusa(f"Não sei fazer '{nome}'.")
    if not isinstance(argumentos, dict):
        argumentos = {}

    # O contrato primeiro: se a ação está no catálogo, os argumentos têm de
    # bater certo com ele. O cérebro já filtrou, mas o Pi é quem mexe os
    # motores — e quem mexe os motores não confia em ninguém.
    if nome in acoes.ACOES:
        ok, razao = acoes.validar({"nome": nome, "argumentos": argumentos})
        if not ok:
            return Recusa(f"Não posso fazer isso assim ({razao}).")

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
        return Recusa(f"Tentei mas não consegui: {erro}")
