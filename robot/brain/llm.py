"""O CÉREBRO GRANDE — cliente do Ollama que corre no Mac.

╔══════════════════════════════════════════════════════════════════════════╗
║  PORQUÊ O LLM NÃO CORRE NO ROBÔ                                          ║
║                                                                          ║
║  O Raspberry Pi 5 é bom a REAGIR DEPRESSA (ver, ouvir, mexer) e mau a    ║
║  PENSAR — um modelo de 12 mil milhões de parâmetros não cabe lá dentro.  ║
║  O Mac é o contrário.                                                    ║
║                                                                          ║
║  Então dividimos: reflexos no robô, raciocínio no Mac.                   ║
║  Tudo dentro de casa. Nada vai para a Internet.                          ║
╚══════════════════════════════════════════════════════════════════════════╝

Configurar o Mac (uma vez):

    launchctl setenv OLLAMA_HOST "0.0.0.0:11434"
    launchctl setenv OLLAMA_KEEP_ALIVE "-1"      # modelo fica sempre em RAM
    # reiniciar a app Ollama
    ollama pull gemma4:12b

Verificar a partir do robô:

    curl http://mac.local:11434/api/tags
"""

from __future__ import annotations

import json

import requests

from robot import config

_historico: list[dict] = []
_disponivel: bool | None = None

FRASES_OFFLINE = [
    "O meu cérebro grande está a dormir. Mas ainda te consigo ver e andar!",
    "Não consigo falar com o computador lá de casa. Está desligado?",
    "Hmm, estou com a cabeça vazia. Verifica se o Mac está ligado.",
]


def _url(caminho: str) -> str:
    host = config.obter("llm.host", "mac.local")
    porta = config.obter("llm.porta", 11434)
    return f"http://{host}:{porta}{caminho}"


def carregar_personalidade() -> str:
    """Lê o config/personalidade.txt — o system prompt que a Lara escreve."""
    ficheiro = config.CONFIG_DIR / "personalidade.txt"
    if ficheiro.exists():
        linhas = [
            linha for linha in ficheiro.read_text(encoding="utf-8").splitlines()
            if not linha.strip().startswith("#")
        ]
        return "\n".join(linhas).strip()
    return f"És o {config.nome_do_robo()}, um robô simpático. Falas português de Portugal."


def esta_ligado(timeout: float = 2.0) -> bool:
    """O Mac está a servir o LLM? Verificação rápida."""
    global _disponivel
    if config.a_simular():
        return True
    try:
        r = requests.get(_url("/api/tags"), timeout=timeout)
        _disponivel = r.status_code == 200
    except Exception:  # noqa: BLE001
        _disponivel = False
    return _disponivel


def modelos_disponiveis() -> list[str]:
    try:
        r = requests.get(_url("/api/tags"), timeout=3)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:  # noqa: BLE001
        return []


def perguntar(
    texto: str,
    contexto: str | None = None,
    ferramentas: list[dict] | None = None,
) -> dict:
    """Envia uma pergunta ao LLM.

    Devolve {"texto": str, "acoes": [ {"nome":…, "argumentos":…} ], "offline": bool}
    """
    if config.a_simular():
        config.sim(f'LLM ← "{texto}"')
        return {"texto": f"(simulação) Recebi: {texto}", "acoes": [], "offline": False}

    if not esta_ligado():
        import random

        return {"texto": random.choice(FRASES_OFFLINE), "acoes": [], "offline": True}

    sistema = carregar_personalidade()
    if contexto:
        sistema += f"\n\nCONTEXTO NESTE MOMENTO: {contexto}"

    mensagens = [{"role": "system", "content": sistema}]
    mensagens += _historico[-int(config.obter("llm.max_historico", 12)):]
    mensagens.append({"role": "user", "content": texto})

    corpo = {
        "model": config.obter("llm.modelo", "gemma4:12b"),
        "messages": mensagens,
        "stream": False,
        "options": {
            "temperature": float(config.obter("llm.temperatura", 0.7)),
            "num_predict": 200,
        },
    }
    if ferramentas:
        corpo["tools"] = ferramentas

    try:
        r = requests.post(
            _url("/api/chat"),
            json=corpo,
            timeout=float(config.obter("llm.timeout_s", 20)),
        )
        r.raise_for_status()
        mensagem = r.json().get("message", {})
    except requests.Timeout:
        return {
            "texto": "Estou a pensar devagar hoje… podes repetir?",
            "acoes": [],
            "offline": False,
        }
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Erro ao falar com o LLM: {erro}")
        return {
            "texto": "Baralhei-me toda. Diz outra vez?",
            "acoes": [],
            "offline": False,
        }

    resposta = (mensagem.get("content") or "").strip()

    acoes = []
    for chamada in mensagem.get("tool_calls", []) or []:
        funcao = chamada.get("function", {})
        argumentos = funcao.get("arguments", {})
        if isinstance(argumentos, str):
            try:
                argumentos = json.loads(argumentos)
            except json.JSONDecodeError:
                argumentos = {}
        acoes.append({"nome": funcao.get("name", ""), "argumentos": argumentos})

    _historico.append({"role": "user", "content": texto})
    if resposta:
        _historico.append({"role": "assistant", "content": resposta})

    return {"texto": _encurtar(resposta), "acoes": acoes, "offline": False}


def _encurtar(texto: str) -> str:
    """O robô FALA. Ninguém quer ouvir um parágrafo.

    O system prompt já pede respostas curtas, mas os LLMs nem sempre
    obedecem — por isso cortamos aqui também. Nunca confiar só no prompt.
    """
    maximo = int(config.obter("llm.max_frases", 3))
    if not texto:
        return texto
    partes, atual = [], ""
    for caracter in texto:
        atual += caracter
        if caracter in ".!?" and len(atual.strip()) > 2:
            partes.append(atual.strip())
            atual = ""
    if atual.strip():
        partes.append(atual.strip())
    return " ".join(partes[:maximo]) if partes else texto


def esquecer() -> None:
    """Apaga o histórico da conversa."""
    _historico.clear()
