"""COMANDOS QUE NÃO PASSAM PELO LLM.

╔══════════════════════════════════════════════════════════════════════════╗
║  PORQUE É QUE ISTO EXISTE                                                ║
║                                                                          ║
║  Há três ou quatro coisas que o robô tem de fazer SEMPRE, e à primeira:  ║
║  parar, e deixar de olhar. São a travagem de emergência e o interruptor  ║
║  da câmara.                                                              ║
║                                                                          ║
║  Um LLM acerta na ferramenta certa talvez 90% das vezes. Para "conta-me  ║
║  uma piada" isso é ótimo. Para "PÁRA" é inaceitável: uma em cada dez     ║
║  vezes o robô continuaria a andar, ou continuaria a olhar depois de a    ║
║  Lara lhe ter pedido para não olhar.                                     ║
║                                                                          ║
║  Regra: controlos de SEGURANÇA e de PRIVACIDADE nunca dependem do        ║
║  modelo. São comparações de texto, aqui, antes de o LLM sequer ver a     ║
║  frase. É a mesma ideia do pino OE dos PCA9685 — a rede de segurança     ║
║  tem de funcionar mesmo quando a parte inteligente falha.                ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import unicodedata

from robot.brain import companion, follow
from robot.hardware import arms, motors


# ⚠️ O PRÉ-ROLO PÔS A PALAVRA-CHAVE À FRENTE DE TUDO.
#
# Desde que o áudio vai para o mini em contínuo, o que chega aqui já não é
# «pára» — é «olá robô pára», porque o pré-rolo (ver wakeword.py) contém
# sempre a palavra mágica que acabou de ser dita. Com a comparação exata, o
# travão de emergência e o interruptor da câmara deixaram de funcionar: as
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
    follow.parar()      # primeiro o modo, senão a volta seguinte punha-o a andar outra vez
    motors.parar()
    arms.relaxar()
    return "Parei."


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
    return None


def frases_reservadas() -> list[str]:
    """Todas as frases que nunca chegam ao LLM. Usado nos testes."""
    return sorted({f for frases, _ in COMANDOS for f in frases})
