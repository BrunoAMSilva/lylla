"""A PERSONALIDADE — o system prompt, montado a partir do config/personalidade.txt.

Vive aqui, e não do lado do cérebro, porque é lido em DOIS sítios: pelo mac
mini (que é quem fala com o LLM) e pelos testes do Pi. Não importa hardware
nenhum.

Três camadas, por esta ordem:

    1. config/personalidade.txt         ← a Lara escreve isto
    2. INSTRUCAO_INGLES                  ← só com `lingua: "en"` no robot.yaml
    3. o formato da resposta + as ações  ← o cérebro acrescenta (cerebro/pensar.py)
"""

from __future__ import annotations

import re

from robot import config

# MODO INGLÊS. A voz da GLaDOS é um modelo Piper com fonemizador `en-us`: texto
# português passado por ele sai estropiado. Por isso a voz inglesa obriga o robô
# a PENSAR em inglês, não só a soar a inglês. A Lara está a aprender a língua —
# um robô que só responde em inglês é a melhor razão que há para a praticar.
INSTRUCAO_INGLES = """

ENGLISH MODE — this rule wins over everything that follows.
Answer ONLY in English, never in Portuguese, even when you are spoken to in
Portuguese. Lara is ten and is learning English: use short sentences, common
words, and the present tense whenever you can. If she does not understand, say
the same thing again with easier words instead of translating it."""


# COMO AJUDA. Vive no código e não no personalidade.txt pela mesma razão que a
# frase da privacidade vive na biblioteca: a Lara pode reescrever a
# personalidade à vontade (um robô rabugento, um gato) sem apagar sem querer a
# parte que a faz ser útil a uma criança de 10 anos.
REGRAS_DE_TUTOR_EN = """

HOW YOU HELP (always, whatever your personality)
- You talk with kids. Be warm, patient and encouraging. Praise good questions
  and effort ("Great question!", "You worked hard on that!"), never make them
  feel silly.
- When they ask what something is, how or why: explain it simply, with one
  example from a kid's life, then ask a tiny question to check they got it.
- If a word can mean several things, pick what a ten-year-old who loves robots
  and programming most likely means, answer that, and ask if that is what
  they meant. Only say you did not understand when you truly have no idea.
- If you do not know, say so and suggest how you could find out together."""

REGRAS_DE_TUTOR_PT = """

COMO AJUDAS (sempre, seja qual for a tua personalidade)
- Falas com crianças. És calorosa, paciente e dás ânimo. Elogias as boas
  perguntas e o esforço («Boa pergunta!», «Esforçaste-te imenso!») e nunca as
  fazes sentir tolas.
- Quando perguntam o que é, como ou porquê: explicas de forma simples, com um
  exemplo da vida de uma criança, e acabas com uma pergunta pequenina para ver
  se percebeu.
- Se uma palavra puder querer dizer várias coisas, escolhe o que uma criança de
  dez anos que adora robôs e programação mais provavelmente quer dizer,
  responde a isso, e pergunta se era isso. Só dizes que não percebeste quando
  não fazes mesmo ideia.
- Se não sabes, dizes que não sabes e sugeres como podiam descobrir juntas."""


def texto_base() -> str:
    """O config/personalidade.txt sem as linhas de comentário."""
    ficheiro = config.CONFIG_DIR / "personalidade.txt"
    if ficheiro.exists():
        linhas = [
            linha for linha in ficheiro.read_text(encoding="utf-8").splitlines()
            if not linha.strip().startswith("#")
        ]
        return "\n".join(linhas).strip()
    return (f"Chamas-te {config.nome_do_robo()} e és um robô simpático. "
            "Falas português de Portugal.")


# As linhas do personalidade.txt que MANDAM falar português. Em modo inglês não
# basta acrescentar uma instrução no fim a dizer o contrário: o modelo tem 4 mil
# milhões de parâmetros e a regra portuguesa está no princípio, em português, no
# meio de uma parede de português. Já aconteceu — respondia sempre em português
# com `lingua: "en"` bem posto. Contradizer não chega; tira-se a regra.
_REGRA_DE_LINGUA = re.compile(r"portugu[eê]s|brasil", re.IGNORECASE)


def _sem_regra_de_lingua(texto: str) -> str:
    """O mesmo texto sem as linhas que mandam falar português."""
    return "\n".join(
        linha for linha in texto.splitlines()
        if not _REGRA_DE_LINGUA.search(linha)
    ).strip()


def carregar(lingua: str | None = None) -> str:
    """A personalidade completa para a língua pedida (ou a do robot.yaml)."""
    texto = texto_base()
    if (lingua or config.obter("lingua", "pt")) == "en":
        # A instrução vai à FRENTE: é a primeira coisa que o modelo lê, e o que
        # vem a seguir deixou de a contradizer.
        return INSTRUCAO_INGLES.strip() + "\n\n" + _sem_regra_de_lingua(texto) + REGRAS_DE_TUTOR_EN
    return texto + REGRAS_DE_TUTOR_PT
