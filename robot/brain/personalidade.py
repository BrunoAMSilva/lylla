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

from robot import config

# MODO INGLÊS. A voz da GLaDOS é um modelo Piper com fonemizador `en-us`: texto
# português passado por ele sai estropiado. Por isso a voz inglesa obriga o robô
# a PENSAR em inglês, não só a soar a inglês. A Lara está a aprender a língua —
# um robô que só responde em inglês é a melhor razão que há para a praticar.
INSTRUCAO_INGLES = """

ENGLISH MODE — this overrides the language rules above.
Answer ONLY in English, never in Portuguese, even when you are spoken to in
Portuguese. Lara is ten and is learning English: use short sentences, common
words, and the present tense whenever you can. If she does not understand, say
the same thing again with easier words instead of translating it."""


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


def carregar(lingua: str | None = None) -> str:
    """A personalidade completa para a língua pedida (ou a do robot.yaml)."""
    texto = texto_base()
    if (lingua or config.obter("lingua", "pt")) == "en":
        texto += INSTRUCAO_INGLES
    return texto
