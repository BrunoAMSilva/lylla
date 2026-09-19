"""O CONTRATO — o que o cérebro (no mac mini) pode pedir ao robô (no Pi).

╔══════════════════════════════════════════════════════════════════════════╗
║  UM SÓ SÍTIO PARA A LISTA DE AÇÕES                                       ║
║                                                                          ║
║  O LLM corre no mac mini; os motores, os braços e os olhos estão no Pi.  ║
║  Os dois têm de concordar sobre o que "mover" ou "seguir" significam —  ║
║  e a única forma de nunca discordarem é lerem a lista do MESMO ficheiro. ║
║                                                                          ║
║    · o cérebro usa isto para construir o esquema JSON que obriga o LLM   ║
║      a responder com ações que existem, com argumentos que existem;      ║
║    · o Pi usa isto para validar o que recebe ANTES de mexer um motor.    ║
║                                                                          ║
║  Este ficheiro não importa hardware nenhum, de propósito: é só dados.    ║
║  Tem de poder ser lido no mac mini, onde não há motores.                 ║
╚══════════════════════════════════════════════════════════════════════════╝

A resposta do cérebro tem SEMPRE esta forma (ver cerebro/pensar.py):

    {
      "expressao": "feliz",                       ← a cara, ANTES de falar
      "fala": "Claro! Vou atrás de ti.",          ← o que diz
      "acoes": [                                  ← o que faz, depois de falar
        {"nome": "seguir", "argumentos": {"acao": "comecar"}}
      ]
    }

A cara vem em primeiro lugar por uma razão: o LLM gera o JSON por ordem, e
assim o Pi muda os olhos antes de a primeira palavra sair. Um robô que mostra
a emoção e depois fala parece vivo; um que fala e depois muda de cara parece
uma animação a atrasar-se.

Poucas ações, com opções fechadas. Os modelos pequenos escolhem bem entre 6
a 8; acima disso baralham-se. Coisas que o robô SABE (quem está à frente,
quanta bateria tem, a que distância está o obstáculo) não são ações: o Pi
manda-as no `contexto` de cada pergunta, e o LLM responde logo, sem mais uma
volta pela rede.
"""

from __future__ import annotations

import json
import math
from typing import Any

from robot.expressions import EXPRESSOES
from robot.gestures import GESTOS

# ---------------------------------------------------------------------------
# O catálogo
#
# Cada parâmetro é um bocado de JSON Schema (o que o Ollama e o llama.cpp
# percebem). `enum` e `minimum`/`maximum` são as únicas restrições que usamos —
# são as que o Pi sabe validar em validar(), lá em baixo.
# ---------------------------------------------------------------------------

def divisoes_da_casa() -> list[str]:
    """Os sítios com nome da planta (data/casa.json), se ela existir.

    ⚠️ Isto lê um ficheiro, ao contrário de todo o resto deste módulo — mas
    continua a não importar hardware nenhum, que é a regra que interessa: no
    mac mini corre na mesma. Se o ficheiro não estiver lá (por exemplo num
    mini onde só se copiou o código), a ação fica com um texto livre em vez
    de uma lista fechada, e quem valida o nome é o Pi, que tem a planta.
    """
    try:
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2]
        caminho = raiz / "data" / "casa.json"
        if not caminho.exists():
            return []
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return [d["nome"] for d in dados.get("divisoes", [])]
    except Exception:  # noqa: BLE001
        return []


def _parametro_sitio() -> dict:
    nomes = divisoes_da_casa()
    if nomes:
        return {"type": "string", "enum": nomes,
                "description": "A divisão da casa para onde ir."}
    return {"type": "string",
            "description": "A divisão da casa para onde ir (ex.: sala, cozinha)."}


ACOES: dict[str, dict[str, Any]] = {
    "mover": {
        "descricao": "Anda para a frente ou para trás.",
        "parametros": {
            "direcao": {"type": "string", "enum": ["frente", "tras"]},
            "cm": {
                "type": "integer", "minimum": 5, "maximum": 50,
                "description": "Distância em centímetros.",
            },
        },
        "obrigatorios": ["direcao"],
    },
    "virar": {
        "descricao": "Roda no lugar. Negativo = esquerda, positivo = direita.",
        "parametros": {
            "graus": {"type": "integer", "minimum": -180, "maximum": 180},
        },
        "obrigatorios": ["graus"],
    },
    "gesto": {
        "descricao": (
            "Faz um gesto com os braços. Acena ao cumprimentar, festeja com boas "
            "notícias, encolhe os ombros quando não sabes."
        ),
        "parametros": {
            "nome": {"type": "string", "enum": sorted(GESTOS)},
        },
        "obrigatorios": ["nome"],
    },
    "apontar": {
        "descricao": "Aponta com o braço numa direção.",
        "parametros": {
            "direcao": {"type": "string", "enum": ["esquerda", "direita", "cima", "frente"]},
        },
        "obrigatorios": ["direcao"],
    },
    "garra": {
        "descricao": "Abre ou fecha a mão.",
        "parametros": {
            "acao": {"type": "string", "enum": ["abrir", "fechar"]},
        },
        "obrigatorios": ["acao"],
    },
    "dancar": {
        "descricao": "Faz uma pequena dança alegre.",
        "parametros": {},
        "obrigatorios": [],
    },
    "ir_para": {
        "descricao": (
            "Vai sozinha até uma divisão da casa, a contornar o que estiver pelo "
            "caminho ('vai à cozinha', 'anda até à sala'). Serve também para lhe "
            "DIZEREM onde está, com estou_aqui=true. Para seguir uma PESSOA usa "
            "'seguir', não isto."
        ),
        "parametros": {
            "sitio": _parametro_sitio(),
            "estou_aqui": {
                "type": "boolean",
                "description": (
                    "Põe a true quando te DIZEM onde estás ('estás na cozinha', "
                    "'isto é a sala') em vez de te mandarem ir. Ela não tem GPS: "
                    "de vez em quando precisa que lhe digam onde está."
                ),
            },
        },
        "obrigatorios": ["sitio"],
    },
    "seguir": {
        "descricao": (
            "Começa ou para de seguir a pessoa com quem estás a falar, andando "
            "atrás dela. Usa 'comecar' quando te pedem para ires atrás de alguém "
            "e 'parar' quando te pedem para ficares."
        ),
        "parametros": {
            "acao": {"type": "string", "enum": ["comecar", "parar"]},
        },
        "obrigatorios": ["acao"],
    },
    "ver_caras": {
        "descricao": (
            "Olha AGORA e diz quem vês ('vês alguma cara?', 'conheces quem está "
            "aí?'). Usa isto quando te perguntam pelo que estás a ver neste "
            "momento; o que vem entre parênteses retos no início da mensagem "
            "pode ter segundos e não serve para responder a uma pergunta direta."
        ),
        "parametros": {
            "so_conhecidas": {
                "type": "boolean",
                "description": (
                    "true quando perguntam por uma cara CONHECIDA; false quando "
                    "perguntam se vês alguma cara, seja de quem for."
                ),
            },
        },
        "obrigatorios": [],
    },
    "registar_cara": {
        "descricao": (
            "Aprende a cara de alguém, guiando a pessoa pelas poses em voz alta "
            "('learn my face', 'adiciona a minha cara'). Usa-a SEMPRE que to "
            "pedirem, mesmo que não conheças a pessoa — é para isso que serve; "
            "a câmara verifica sozinha se há alguém. Se não souberes o nome, "
            "deixa-o vazio: o robô pergunta-o, e pede licença antes."
        ),
        "parametros": {
            "nome": {"type": "string", "description": "O nome da pessoa, se o disseram."},
        },
        "obrigatorios": [],
    },
}


def expressoes_disponiveis() -> list[str]:
    """As caras que o LLM pode escolher. Vêm do config/expressoes.yaml."""
    return sorted(EXPRESSOES)


# ---------------------------------------------------------------------------
# Três vistas do mesmo catálogo
# ---------------------------------------------------------------------------


def esquema_json(expressoes: list[str] | None = None) -> dict:
    """O JSON Schema da resposta inteira — é isto que se manda ao Ollama em
    `format`, e que obriga o modelo a devolver exatamente esta forma.

    A ORDEM das chaves importa (expressao → fala → acoes): a gramática do
    llama.cpp respeita-a, e o cérebro conta com isso para começar a falar
    antes de o JSON estar completo.
    """
    expressoes = expressoes or expressoes_disponiveis()
    variantes = []
    for nome, acao in ACOES.items():
        argumentos: dict[str, Any] = {
            "type": "object",
            "properties": acao["parametros"],
            "required": list(acao["obrigatorios"]),
        }
        variantes.append({
            "type": "object",
            "properties": {
                "nome": {"type": "string", "enum": [nome]},
                "argumentos": argumentos,
            },
            "required": ["nome", "argumentos"],
        })
    return {
        "type": "object",
        "properties": {
            "expressao": {"type": "string", "enum": expressoes},
            "fala": {"type": "string"},
            "acoes": {"type": "array", "items": {"anyOf": variantes}},
        },
        "required": ["expressao", "fala", "acoes"],
    }


def descricao_para_prompt(expressoes: list[str] | None = None) -> str:
    """A lista de ações em texto, para o system prompt do LLM."""
    expressoes = expressoes or expressoes_disponiveis()
    linhas = []
    for nome, acao in ACOES.items():
        partes = []
        for pnome, p in acao["parametros"].items():
            if "enum" in p:
                partes.append(f"{pnome}: {'|'.join(str(v) for v in p['enum'])}")
            elif "minimum" in p or "maximum" in p:
                partes.append(f"{pnome}: {p.get('minimum', '')}..{p.get('maximum', '')}")
            else:
                partes.append(pnome)
        assinatura = f"{nome}({', '.join(partes)})"
        linhas.append(f"- {assinatura} — {acao['descricao']}")
    return (
        "CARAS que podes fazer (campo `expressao`): " + ", ".join(expressoes) + "\n"
        "AÇÕES que podes pedir (lista `acoes`, pode ir vazia):\n" + "\n".join(linhas)
    )


def ferramentas_ollama() -> list[dict]:
    """O mesmo catálogo no formato de *tool calling* do Ollama.

    Não é o que o cérebro usa (usa a saída estruturada, ver esquema_json),
    mas é útil para experiências: qualquer modelo que faça tool calling
    recebe exatamente as mesmas ações.
    """
    ferramentas = []
    for nome, acao in ACOES.items():
        ferramentas.append({
            "type": "function",
            "function": {
                "name": nome,
                "description": acao["descricao"],
                "parameters": {
                    "type": "object",
                    "properties": acao["parametros"],
                    "required": list(acao["obrigatorios"]),
                },
            },
        })
    return ferramentas


# ---------------------------------------------------------------------------
# Validação — a mesma nos dois lados
# ---------------------------------------------------------------------------


def validar(acao: Any) -> tuple[bool, str]:
    """(True, "") se a ação existir e os argumentos baterem certo com o
    catálogo; (False, porquê) se não. Nunca levanta exceções: o LLM pode
    devolver qualquer coisa, e qualquer coisa tem de dar uma resposta calma.
    """
    if not isinstance(acao, dict):
        return False, "a ação não é um objeto"
    nome = acao.get("nome")
    if nome not in ACOES:
        return False, f"não existe a ação '{nome}'"
    argumentos = acao.get("argumentos") or {}
    if not isinstance(argumentos, dict):
        return False, f"os argumentos de '{nome}' não são um objeto"

    especificacao = ACOES[nome]
    for obrigatorio in especificacao["obrigatorios"]:
        if obrigatorio not in argumentos:
            return False, f"falta o argumento '{obrigatorio}' em '{nome}'"

    for pnome, valor in argumentos.items():
        p = especificacao["parametros"].get(pnome)
        if p is None:
            return False, f"'{nome}' não tem o argumento '{pnome}'"
        if "enum" in p and valor not in p["enum"]:
            return False, f"'{pnome}' tem de ser um de {p['enum']}, não '{valor}'"
        if p.get("type") == "integer":
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                return False, f"'{pnome}' tem de ser um número inteiro"
            # ⚠️ NaN passa por QUALQUER comparação: `nan < 5` e `nan > 50` são
            #    os dois falsos, portanto escorregava pelos limites abaixo e
            #    só rebentava lá à frente, no int(). E o `json.loads` aceita
            #    o literal NaN, por isso um modelo pode mesmo devolvê-lo.
            if isinstance(valor, float) and (math.isnan(valor) or math.isinf(valor)):
                return False, f"'{pnome}' não é um número que eu perceba"
            if "minimum" in p and valor < p["minimum"]:
                return False, f"'{pnome}' tem de ser pelo menos {p['minimum']}"
            if "maximum" in p and valor > p["maximum"]:
                return False, f"'{pnome}' tem de ser no máximo {p['maximum']}"
    return True, ""


def normalizar(acoes: Any) -> tuple[list[dict], list[str]]:
    """Fica com as ações válidas, na forma canónica; devolve também as
    razões pelas quais deitou fora as outras (para o registo, não para a
    Lara ouvir).
    """
    validas: list[dict] = []
    recusadas: list[str] = []
    if not isinstance(acoes, list):
        return validas, ["as ações não vieram numa lista"]
    for acao in acoes:
        ok, razao = validar(acao)
        if ok:
            argumentos = dict(acao.get("argumentos") or {})
            for pnome, valor in list(argumentos.items()):
                if ACOES[acao["nome"]]["parametros"][pnome].get("type") == "integer":
                    argumentos[pnome] = int(valor)
            validas.append({"nome": acao["nome"], "argumentos": argumentos})
        else:
            recusadas.append(razao)
    return validas, recusadas
