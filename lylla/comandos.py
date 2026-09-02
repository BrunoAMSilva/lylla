"""COMANDOS — ensinar palavras novas ao robô.

    from lylla import comando, voz

    @comando("adicionar face", "aprende a minha cara")
    def adicionar_face():
        voz.dizer("Como te chamas?")
        ...
        return "Já está!"

A partir daí, dizer «Olá Lylla, adicionar face» chama a função. O que ela
devolver (se devolver alguma coisa) é o que o robô responde.

╔══════════════════════════════════════════════════════════════════════════╗
║  ONDE É QUE ISTO ENTRA, E PORQUÊ ANTES DO LLM                            ║
║                                                                          ║
║  A frase que a Lara diz passa primeiro pelos comandos de SEGURANÇA       ║
║  («pára», «não olhes») — esses ganham sempre, e nem esta lista os pode   ║
║  tapar. Depois vem esta lista. Só se nada bater certo é que a frase vai  ║
║  para o LLM.                                                             ║
║                                                                          ║
║  A razão de os comandos dela não passarem pelo modelo é a mesma que já   ║
║  está escrita no comandos_diretos.py: um LLM acerta 90% das vezes, e     ║
║  uma função que só funciona nove em cada dez vezes não se consegue       ║
║  depurar. Aqui, ou a frase bate certo ou não bate — e vê-se porquê.      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import unicodedata
from typing import Callable

# frase simplificada → (função, frases originais)
_REGISTO: dict[str, tuple[Callable[[], object], str]] = {}


def _simplificar(texto: str) -> str:
    sem_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )
    return " ".join("".join(c if c.isalnum() else " " for c in sem_acentos).split())


def comando(*frases: str):
    """Decorador: liga uma função a uma ou mais frases ditas em voz alta."""
    def registar(funcao: Callable[[], object]) -> Callable[[], object]:
        for frase in frases:
            chave = _simplificar(frase)
            if chave:
                _REGISTO[chave] = (funcao, frase)
        return funcao
    return registar


def executar(frase_simplificada: str) -> str | None:
    """Corre o comando que corresponde à frase. None se não houver nenhum.

    Se a função da Lara rebentar, isto NÃO deixa o erro subir: o robô diz que
    não conseguiu e continua vivo. Um robô que morre por causa de uma função
    a meio de escrever é um robô que ela deixa de querer programar.
    """
    entrada = _REGISTO.get(frase_simplificada)
    if entrada is None:
        return None
    funcao, frase = entrada
    try:
        resposta = funcao()
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  o comando '{frase}' deu erro: {erro}")
        return "Enganei-me a fazer isso. Vê o que apareceu no ecrã."
    return str(resposta) if resposta is not None else "Feito!"


def conhecidos() -> list[str]:
    """As frases que já estão ensinadas, como foram escritas."""
    return sorted(frase for _, frase in _REGISTO.values())


def esquecer_todos() -> None:
    """Só para os testes."""
    _REGISTO.clear()
