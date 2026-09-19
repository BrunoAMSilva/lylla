"""COMANDOS QUE NÃO PASSAM PELO LLM.

O mac mini ainda transcreve a fala. Depois, o Pi compara o texto com esta
lista antes de o enviar ao modelo de linguagem. Isso evita uma decisão
probabilística do LLM, mas não elimina a dependência da rede nem do STT.

Uma ordem falada de paragem não substitui um controlo físico. Se o mini estiver
indisponível, o Pi não recebe texto para comparar.
"""

from __future__ import annotations

import re
import time
import unicodedata

from robot.brain import companion, follow
from robot.hardware import arms, motors
from robot.navigation import ir_para, procurar


# ⚠️ O PRÉ-ROLO PÔS A PALAVRA-CHAVE À FRENTE DE TUDO.
#
# Desde que o áudio vai para o mini em contínuo, o que chega aqui já não é
# «pára» — é «olá robô pára», porque o pré-rolo (ver wakeword.py) contém
# sempre a palavra mágica que acabou de ser dita. Com a comparação exata, o
# comando de paragem e o pedido de privacidade deixaram de funcionar: as
# duas coisas que este ficheiro existe para garantir.
#
# Por isso, antes de comparar, tira-se o que vier ANTES da palavra-chave.
# É de propósito mais estrito do que "acaba em pára": uma frase que por acaso
# termine numa destas palavras não pode parar o robô a meio de uma brincadeira.
PALAVRAS_CHAVE = ("ola robo", "ola lylla", "lylla", "ola roboo")


def _simplificar(texto: str) -> str:
    """minúsculas, sem acentos, sem pontuação — para comparar à vontade."""
    sem_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )
    return " ".join("".join(c if c.isalnum() else " " for c in sem_acentos).split())


def _parar_tudo() -> str:
    # ⚠️ PRIMEIRO OS MODOS, SÓ DEPOIS OS MOTORES.
    # Todos estes têm um um_passo() que o ciclo principal chama outra vez daqui
    # a um décimo de segundo. Parar os motores sem desligar o modo dá um robô
    # que pára meio segundo e volta a andar — que é exatamente o contrário do
    # que a Lara pediu, e a razão de este ficheiro existir.
    follow.parar()
    procurar.parar()    # também desliga o ir_para, que é quem ele usa
    ir_para.parar()
    motors.parar()
    arms.relaxar()
    return "Stopped."


def _horas() -> str:
    agora = time.localtime()
    return f"It's {agora.tm_hour}:{agora.tm_min:02d}." if agora.tm_min else \
        f"It's {agora.tm_hour} o'clock."


def _piscar() -> str:
    from robot.brain import tools

    return str(tools.executar("piscar_luzes", {"vezes": 3}))


def _diagnostico() -> str:
    from robot.brain import tools

    return str(tools.executar("diagnostico", {}))


# ⚠️ O volume é o único com NÚMERO, e por isso não cabe na lista de frases
#    exatas. Fica aqui em vez de ir para o catálogo do LLM pela mesma razão
#    que o «pára»: é uma ordem de utilidade, com uma resposta única e certa —
#    não há nada para o modelo decidir, e cada ação que lá não está é uma a
#    menos para ele escolher mal.
_VOLUME = re.compile(r"\bvolume\b.*?(\d{1,3})")


def _tentar_volume(frase: str) -> str | None:
    achou = _VOLUME.search(frase)
    if achou is None:
        return None
    from robot.brain import tools

    return str(tools.executar("volume", {"percentagem": min(100, int(achou.group(1)))}))


def _aprender_cara() -> str:
    """«Learn my face» — o registo só por voz, sem depender do LLM acertar.

    Devolve "" porque o registo já disse tudo o que havia a dizer."""
    from robot.brain import tools

    tools.executar("registar_cara", {"nome": ""})
    return ""


# Ordem importa: a primeira que casar é a que ganha.
COMANDOS: tuple[tuple[tuple[str, ...], object], ...] = (
    (
        (
            "para de olhar", "parar de olhar", "nao olhes", "nao olhes para mim",
            "deixa de olhar", "desliga a camara", "desligar a camara",
            "modo privado", "fecha os olhos",
        ),
        companion.parar_de_seguir,
    ),
    (
        (
            "podes olhar", "volta a olhar", "voltar a olhar", "liga a camara",
            "ligar a camara", "abre os olhos",
        ),
        companion.voltar_a_seguir,
    ),
    (
        ("para", "parar", "pare", "stop", "quieto", "para quieto"),
        _parar_tudo,
    ),
    (
        ("learn my face", "learn my face please", "remember my face", "register my face",
         "save my face", "add my face", "add a face", "add a new face", "learn a face",
         "learn a new face", "guarda a minha cara", "regista a minha cara",
         "adicionar uma cara", "adiciona uma cara", "adiciona a minha cara",
         "adicionar a minha cara", "adicionar uma face", "aprende uma cara",
         "aprender uma cara", "regista uma cara", "nova cara"),
        # («aprende a minha cara» fica para o comando da Lara, em meus_comandos.py)
        _aprender_cara,
    ),
    (
        ("que horas sao", "quais sao as horas", "diz me as horas", "horas"),
        _horas,
    ),
    (
        ("pisca as luzes", "piscar as luzes", "pisca", "pisca os olhos",
         "acende as luzes"),
        _piscar,
    ),
    (
        ("consegues detetar o chassis", "detetas o chassis", "tens chassis",
         "o que tens ligado", "o que e que tens ligado", "estas toda",
         "diagnostico", "faz um diagnostico"),
        _diagnostico,
    ),
)


def sem_palavra_chave(texto: str) -> str:
    """O que vem DEPOIS da palavra mágica, já simplificado.

    >>> sem_palavra_chave("Olá robô, pára!")
    'para'
    >>> sem_palavra_chave("conta-me uma história")
    'conta me uma historia'

    Usa a ÚLTIMA ocorrência: o pré-rolo pode trazer ruído ou meia palavra
    antes, e o que interessa é o que ela disse a seguir a chamá-lo.
    """
    limpo = _simplificar(texto)
    corte = 0
    for chave in PALAVRAS_CHAVE:
        posicao = limpo.rfind(chave)
        if posicao >= 0:
            corte = max(corte, posicao + len(chave))
    return limpo[corte:].strip()


def tentar(texto: str) -> str | None:
    """Se a frase for um comando direto, executa-o e devolve a resposta.

    Devolve None se não for — e aí a frase segue o caminho normal para o LLM.
    """
    if not texto:
        return None
    limpo = _simplificar(texto)
    sem_chave = sem_palavra_chave(texto)
    for frases, funcao in COMANDOS:
        if limpo in frases or sem_chave in frases:
            return funcao()

    for frase in (sem_chave, limpo):
        resposta = _tentar_volume(frase)
        if resposta is not None:
            return resposta

    # ⚠️ SÓ DEPOIS os comandos que a Lara ensinou (o `@comando` do lylla).
    # A ordem não é um pormenor. Nenhuma função dela pode tapar o «pára» nem o
    # «não olhes». Estes comandos continuam a depender do texto transcrito no
    # mini, mas nunca da decisão do LLM.
    from lylla import comandos as comandos_da_lara

    for frase in (sem_chave, limpo):
        resposta = comandos_da_lara.executar(frase)
        if resposta is not None:
            return resposta
    return None


def frases_reservadas() -> list[str]:
    """Todas as frases que nunca chegam ao LLM. Usado nos testes."""
    return sorted({f for frases, _ in COMANDOS for f in frases})
