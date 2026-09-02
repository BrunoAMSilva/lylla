"""OS COMANDOS DA LARA.

Este ficheiro é teu. Escreve aqui as funções que queres que a Lylla saiba
fazer quando lhe falas.

Para experimentares sem falar (e é assim que se começa):

    ROBO_SIMULAR=1 python3 -c "import meus_comandos; meus_comandos.adicionar_face()"

Quando estiver a funcionar no teclado, funciona por voz sem mudares nada:

    «Olá Lylla, adicionar face»
"""

from __future__ import annotations

from lylla import comando, mover, ver, voz


@comando("adicionar face", "aprende a minha cara", "decora a minha cara")
def adicionar_face() -> str:
    """Ensina uma cara nova ao robô, a conversar.

    Repara no que esta função NÃO faz: não sabe o que é uma câmara, nem uma
    assinatura de 128 números, nem porque é que oito fotografias são melhores
    do que uma. Isso é trabalho da biblioteca `ver`. Aqui só está a CONVERSA —
    que é a parte que tu decides.
    """
    voz.dizer("Como te chamas?")
    nome = voz.ouvir()

    if not nome:
        return "Não percebi o nome. Chama-me outra vez."

    voz.dizer(f"Muito bem, {nome}. Fica à minha frente e faz o que eu disser.")

    # O `aviso=voz.dizer` é o truque todo: a biblioteca dá as instruções, e nós
    # escolhemos que ela as DIGA em voz alta em vez de as escrever no ecrã.
    if ver.guardar_face(nome, aviso=voz.dizer):
        return f"Já conheço a {nome}!"
    return "Não consegui ver-te bem. Vamos tentar outra vez com mais luz."


@comando("quem conheces", "quem e que tu conheces")
def quem_conheces() -> str:
    """Diz as pessoas que o robô já sabe reconhecer."""
    pessoas = ver.conheces()
    if not pessoas:
        return "Ainda não conheço ninguém. Diz-me «adicionar face»."
    return "Conheço " + ", ".join(pessoas) + "."


@comando("da uma volta", "roda")
def dar_uma_volta() -> str:
    """Um exemplo curto, para veres a forma de um comando."""
    for _ in range(4):
        mover.virar_direita(90)
    return "Tonta!"
