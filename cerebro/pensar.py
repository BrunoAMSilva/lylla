"""PENSAR — o LLM, no mac mini, a responder com uma FORMA fixa.

╔══════════════════════════════════════════════════════════════════════════╗
║  SAÍDA ESTRUTURADA EM VEZ DE TOOL CALLING                                ║
║                                                                          ║
║  Com tool calling, os modelos pequenos ou falam ou agem: quando pedem    ║
║  uma ferramenta, o texto vem vazio (a armadilha nº 3 do projeto). Nós    ║
║  queremos as três coisas de cada vez — a cara, a fala e o que fazer —    ║
║  e queremos que venham SEMPRE bem formadas.                              ║
║                                                                          ║
║  O Ollama aceita um JSON Schema em `format` e obriga o modelo a cumpri-  ║
║  -lo token a token (é uma gramática, não um pedido). O esquema vem do    ║
║  contrato em robot/brain/acoes.py: só existem as ações que o Pi sabe     ║
║  fazer, com os argumentos que o Pi sabe validar.                         ║
║                                                                          ║
║  E a ordem das chaves é deliberada: expressao → fala → acoes. O modelo   ║
║  gera por ordem, o cérebro lê à medida que sai (ExtratorDeFala) e manda  ║
║  cada frase ao Pi mal esteja completa. Os olhos mudam antes da primeira  ║
║  palavra; a primeira frase toca enquanto a segunda ainda está a ser      ║
║  escrita. A 10 tokens por segundo num M4, isto são segundos.             ║
╚══════════════════════════════════════════════════════════════════════════╝

Motores: ollama (o nosso) · openai (qualquer servidor compatível — mlx-lm,
llama-server — para comparar) · teste (respostas fixas, sem modelo nenhum).
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Iterator

import requests

from cerebro import config
from robot import config as config_robo
from robot.brain import acoes, personalidade


class CerebroIndisponivel(RuntimeError):
    """O modelo não respondeu. O Pi transforma isto numa frase calma."""


# ---------------------------------------------------------------- as frases

_FIM_DE_FRASE = re.compile(r'([.!?…]+["»)\]]?)(\s+)')

MINIMO_POR_FRASE = 12    # "Sim!" sozinha soa cortada — junta-se à frase seguinte
MAXIMO_POR_FRASE = 220   # uma frase interminável corta-se numa vírgula


def cortar_frases(texto: str, final: bool, minimo: int = MINIMO_POR_FRASE,
                  maximo: int = MAXIMO_POR_FRASE) -> tuple[list[str], str]:
    """Separa o que já são frases completas do que ainda está a meio.

    Devolve (frases, resto). Com final=True o resto vem sempre vazio.
    Uma frase curta demais (minimo) espera pela seguinte e vão juntas —
    "Sim! Vamos lá." soa a uma pessoa; "Sim!" e "Vamos lá." em dois pedaços
    soa a um robô a gaguejar.
    """
    frases: list[str] = []
    inicio = 0     # onde começa a frase que está a acumular
    procura = 0    # a partir de onde procurar o próximo fim de frase
    while True:
        m = _FIM_DE_FRASE.search(texto, procura)
        nl = texto.find("\n", procura)
        if nl != -1 and (m is None or nl < m.start()):
            fim_frase, fim_sep = nl, nl + 1
        elif m is not None:
            fim_frase, fim_sep = m.end(1), m.end()
        elif len(texto) - inicio > maximo:
            i = texto.find(", ", inicio + 40)
            if i == -1:
                break
            fim_frase, fim_sep = i + 1, i + 2
        else:
            break
        candidata = texto[inicio:fim_frase].strip()
        procura = fim_sep
        if len(candidata) < minimo:
            continue          # curta demais: continua a acumular até ao próximo fim
        if candidata:
            frases.append(candidata)
        inicio = fim_sep
    resto = texto[inicio:]
    if final and resto.strip():
        frases.append(resto.strip())
        resto = ""
    return frases, resto


def dividir_em_frases(texto: str) -> list[str]:
    """"Olá! Como estás? Bem." → ["Olá! Como estás?", "Bem."] (a primeira é
    curta e cola-se à seguinte — ver cortar_frases)."""
    frases, _ = cortar_frases((texto or "").replace("\r", ""), final=True)
    return frases


class ExtratorDeFala:
    """Lê o JSON à medida que chega e solta as frases do campo `fala`.

    Não é um parser de JSON — é um leitor de UMA string dentro de um JSON,
    que sabe onde ela começa ("fala": ") e onde acaba (a aspa que não está
    escapada). Tudo o que precisa de saber de JSON são os escapes.

    Uso:
        for delta in modelo:
            for evento in extrator.alimentar(delta): ...
        for evento in extrator.terminar(): ...
    """

    _ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", '"': '"', "\\": "\\", "/": "/"}
    _CHAVE_FALA = re.compile(r'"fala"\s*:\s*"')
    _CHAVE_EXPRESSAO = re.compile(r'"expressao"\s*:\s*"([^"\\]*)"')

    def __init__(self, max_caracteres_por_frase: int = 220) -> None:
        self.buffer = ""
        self.expressao: str | None = None
        self.frases: list[str] = []
        self._estado = "antes"          # antes | dentro | depois
        self._pos = 0
        self._pendente = ""
        self._escape = False
        self._unicode = ""
        self._a_ler_unicode = False
        self._surrogate: int | None = None
        self._max = max_caracteres_por_frase

    # -- o que já se sabe -------------------------------------------------

    @property
    def fala_completa(self) -> str:
        return " ".join(self.frases + ([self._pendente.strip()] if self._pendente.strip() else []))

    @property
    def encontrou_fala(self) -> bool:
        return self._estado != "antes"

    # -- alimentar --------------------------------------------------------

    def alimentar(self, delta: str) -> list[dict]:
        self.buffer += delta
        eventos: list[dict] = []

        if self._estado == "antes":
            if self.expressao is None:
                m = self._CHAVE_EXPRESSAO.search(self.buffer)
                if m:
                    self.expressao = m.group(1)
                    eventos.append({"tipo": "expressao", "nome": self.expressao})
            m = self._CHAVE_FALA.search(self.buffer)
            if not m:
                return eventos
            self._estado = "dentro"
            self._pos = m.end()

        if self._estado == "dentro":
            self._ler_string()
            eventos += self._soltar_frases(final=self._estado == "depois")
        return eventos

    def terminar(self) -> list[dict]:
        eventos = self._soltar_frases(final=True) if self._estado != "antes" else []
        return eventos

    # -- por dentro -------------------------------------------------------

    def _ler_string(self) -> None:
        while self._pos < len(self.buffer):
            c = self.buffer[self._pos]
            self._pos += 1
            if self._a_ler_unicode:
                self._unicode += c
                if len(self._unicode) == 4:
                    self._juntar_unicode(self._unicode)
                    self._unicode, self._a_ler_unicode = "", False
                continue
            if self._escape:
                self._escape = False
                if c == "u":
                    self._a_ler_unicode = True
                else:
                    self._pendente += self._ESCAPES.get(c, c)
                continue
            if c == "\\":
                self._escape = True
            elif c == '"':
                self._estado = "depois"
                return
            else:
                self._pendente += c

    def _juntar_unicode(self, hexa: str) -> None:
        r"""Um `\uXXXX`. Junta os PARES SURROGATE antes de os transformar em texto.

        ⚠️ Tudo o que está fora do plano básico — um emoji, por exemplo — vem
           em JSON como DOIS escapes (`\ud83d\ude00`). Descodificados à peça
           dão dois meios-caracteres que não existem em UTF-8: a frase seguia
           na mesma, mas rebentava ao ser codificada para a rede, e o turno
           morria a meio da fala. O `json.loads` junta-os; nós também temos de
           juntar. (O system prompt pede que não use emojis, mas os modelos
           põem-nos à mesma — e uma frase com um emoji tem de sair na mesma,
           sem ele se for preciso.)
        """
        try:
            n = int(hexa, 16)
        except ValueError:
            self._surrogate = None
            return

        if 0xD800 <= n <= 0xDBFF:            # primeira metade: esperar pela outra
            self._surrogate = n
            return
        if 0xDC00 <= n <= 0xDFFF:            # segunda metade
            if self._surrogate is not None:
                completo = 0x10000 + ((self._surrogate - 0xD800) << 10) + (n - 0xDC00)
                self._surrogate = None
                self._pendente += chr(completo)
            # uma segunda metade sozinha não é caractere nenhum: deitar fora
            return
        self._surrogate = None
        self._pendente += chr(n)

    def _soltar_frases(self, final: bool) -> list[dict]:
        frases, self._pendente = cortar_frases(self._pendente, final, maximo=self._max)
        eventos = []
        for frase in frases:
            self.frases.append(frase)
            eventos.append({"tipo": "frase", "texto": frase})
        return eventos


# --------------------------------------------------------------- o prompt

FORMATO_PT = """

COMO RESPONDES (o formato é obrigatório)
Respondes SEMPRE com um único objeto JSON, sem texto à volta, com estas chaves por esta ordem:
  "expressao": a cara que fazes enquanto falas — uma das CARAS abaixo.
  "fala": o que dizes em voz alta. Uma a três frases curtas. Sem listas, sem emojis, sem asteriscos.
  "acoes": o que fazes DEPOIS de falar — lista de {"nome": ..., "argumentos": {...}} das AÇÕES abaixo. Vazia se não fizeres nada.
Exemplo: {"expressao": "feliz", "fala": "Claro! Vou atrás de ti.", "acoes": [{"nome": "seguir", "argumentos": {"acao": "comecar"}}]}

{catalogo}

O que vem entre parênteses retos no início de cada mensagem é o que os teus sensores veem AGORA (quem está à tua frente, bateria, distância ao obstáculo). Usa isso em vez de perguntares o que já sabes. Se não vês ninguém, não inventes quem está."""

FORMATO_EN = """

HOW YOU ANSWER (the format is mandatory)
You ALWAYS answer with a single JSON object and nothing else, with these keys in this order:
  "expressao": the face you make while speaking — one of the FACES below (keep the Portuguese names).
  "fala": what you say out loud, in English. One to three short sentences. No lists, no emojis, no asterisks.
  "acoes": what you do AFTER speaking — a list of {"nome": ..., "argumentos": {...}} from the ACTIONS below. Empty if you do nothing.
Example: {"expressao": "feliz", "fala": "Sure! I will follow you.", "acoes": [{"nome": "seguir", "argumentos": {"acao": "comecar"}}]}

{catalogo}

The part in square brackets at the start of each message is what your sensors see RIGHT NOW (who is in front of you, battery, distance to the nearest obstacle). Use it instead of asking what you already know. If you see nobody, do not make someone up."""


def montar_sistema(lingua: str, expressoes: list[str] | None = None) -> str:
    """personalidade.txt + (modo inglês) + o formato e o catálogo de ações."""
    catalogo = acoes.descricao_para_prompt(expressoes)
    formato = FORMATO_EN if lingua == "en" else FORMATO_PT
    # .replace e não .format: o texto está cheio de chavetas de JSON
    return personalidade.carregar(lingua) + formato.replace("{catalogo}", catalogo)


def _com_contexto(texto: str, contexto: dict | None, lingua: str) -> str:
    """Põe o que o Pi sabe à frente do que a Lara disse."""
    if not contexto:
        return texto
    en = lingua == "en"
    partes: list[str] = []
    pessoa = contexto.get("pessoa")
    if pessoa:
        partes.append(f"you are talking to {pessoa}" if en else f"estás a falar com {pessoa}")
    elif contexto.get("ve_alguem") is False or "pessoa" in contexto:
        partes.append("you see nobody you know" if en else "não vês ninguém que conheças")
    if contexto.get("bateria_pct") is not None:
        partes.append(f"battery {contexto['bateria_pct']}%" if en else f"bateria {contexto['bateria_pct']}%")
    if contexto.get("distancia_cm") is not None:
        d = int(contexto["distancia_cm"])
        partes.append(f"nearest obstacle {d} cm ahead" if en else f"obstáculo a {d} cm")
    if contexto.get("modo"):
        partes.append(f"mode: {contexto['modo']}" if en else f"modo {contexto['modo']}")
    if contexto.get("a_seguir"):
        partes.append("you are following someone" if en else "estás a seguir alguém")
    if contexto.get("hora"):
        partes.append(f"time {contexto['hora']}" if en else f"são {contexto['hora']}")
    if contexto.get("nota"):
        partes.append(str(contexto["nota"]))
    if not partes:
        return texto
    return f"[{' · '.join(partes)}]\n{texto}"


# -------------------------------------------------------------- os motores


class _Motor:
    nome = "?"
    modelo = "?"

    def __init__(self) -> None:
        self.estatisticas: dict[str, Any] = {}
        self.usou_esquema = False

    def gerar(self, mensagens: list[dict], esquema: dict | None) -> Iterator[str]:
        raise NotImplementedError

    def esta_ligado(self) -> bool:
        return True

    def aquecer(self) -> None:
        pass


class MotorOllama(_Motor):
    nome = "ollama"

    def __init__(self) -> None:
        super().__init__()
        self.url = str(config.obter("pensar.url", "http://127.0.0.1:11434")).rstrip("/")
        self.modelo = str(config.obter("pensar.modelo", "gemma4:e4b"))
        self.timeout = float(config.obter("pensar.timeout_s", 60))

    def esta_ligado(self) -> bool:
        try:
            return requests.get(f"{self.url}/api/tags", timeout=2).status_code == 200
        except requests.RequestException:
            return False

    def modelos(self) -> list[str]:
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=3)
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:  # noqa: BLE001
            return []

    def aquecer(self) -> None:
        """Carrega o modelo para a RAM sem gerar nada.

        ⚠️ FALHA ALTO, DE PROPÓSITO. Isto engolia a exceção com um `pass`, e o
           servidor imprimia "pensar: pronto em 0.0 s" com o Ollama desligado.
           Um aquecimento que não aquece nunca pode dizer que aqueceu — é a
           mesma regra do resto do projeto: um teste não pode depender da
           resposta que ele próprio vai dar.
        """
        try:
            resposta = requests.post(f"{self.url}/api/chat", json={
                "model": self.modelo, "messages": [], "keep_alive": config.obter("pensar.keep_alive", -1),
            }, timeout=120)
        except requests.RequestException as erro:
            raise CerebroIndisponivel(
                f"o Ollama não atende em {self.url} — corre `ollama serve`"
            ) from erro
        if resposta.status_code == 404:
            raise CerebroIndisponivel(
                f"o Ollama não tem o modelo '{self.modelo}' — corre `ollama pull {self.modelo}`"
            )
        resposta.raise_for_status()

    def gerar(self, mensagens: list[dict], esquema: dict | None) -> Iterator[str]:
        corpo: dict[str, Any] = {
            "model": self.modelo,
            "messages": mensagens,
            "stream": True,
            "keep_alive": config.obter("pensar.keep_alive", -1),
            "options": {
                "temperature": float(config.obter("pensar.temperatura", 0.7)),
                "num_predict": int(config.obter("pensar.max_tokens", 300)),
            },
        }
        corpo.update(config.obter("pensar.extra", {}) or {})
        if esquema is not None:
            corpo["format"] = esquema
        self.usou_esquema = esquema is not None
        self.estatisticas = {}

        try:
            r = requests.post(f"{self.url}/api/chat", json=corpo, stream=True, timeout=(5, self.timeout))
        except requests.RequestException as erro:
            raise CerebroIndisponivel(f"o Ollama não responde em {self.url} ({erro})") from erro

        if r.status_code == 400 and esquema is not None:
            # O esquema foi recusado (versão antiga do Ollama, modelo sem suporte).
            # Melhor uma resposta em texto do que nenhuma: repetir sem esquema.
            print(f"⚠️  O Ollama recusou o esquema JSON ({r.text[:120]}). A repetir sem ele.")
            yield from self.gerar(mensagens, None)
            return
        if r.status_code != 200:
            raise CerebroIndisponivel(f"o Ollama respondeu {r.status_code}: {r.text[:200]}")

        try:
          for linha in r.iter_lines():
            if not linha:
                continue
            try:
                dados = json.loads(linha)
            except ValueError as erro:
                # Uma página de erro de um proxy, ou um pedaço truncado. Isto
                # é «o modelo está em baixo», não «o pedido estava mal feito»:
                # se subisse como ValueError, o serviço respondia 400 e o Pi
                # não sabia que devia usar o caminho antigo.
                raise CerebroIndisponivel(
                    f"o Ollama respondeu uma coisa que não é JSON ({erro})"
                ) from erro
            if not isinstance(dados, dict):
                continue
            if "error" in dados:
                raise CerebroIndisponivel(str(dados["error"]))
            delta = (dados.get("message") or {}).get("content") or ""
            if delta:
                yield delta
            if dados.get("done"):
                ns = 1_000_000
                self.estatisticas = {
                    "tokens_prompt": dados.get("prompt_eval_count"),
                    "tokens_resposta": dados.get("eval_count"),
                    "ms_prompt": (dados.get("prompt_eval_duration") or 0) // ns,
                    "ms_resposta": (dados.get("eval_duration") or 0) // ns,
                    "ms_carregar": (dados.get("load_duration") or 0) // ns,
                }
                if dados.get("eval_count") and dados.get("eval_duration"):
                    self.estatisticas["tokens_por_s"] = round(
                        dados["eval_count"] / (dados["eval_duration"] / 1e9), 1)
        finally:
            # ⚠️ Quem consome isto pode desistir a meio — um comando direto no
            #    Pi, o robô a desligar-se, um erro mais acima. Sem este close()
            #    o Ollama ficava a gerar para um socket que ninguém lê, com o
            #    modelo ocupado, e a ligação não voltava ao pool. O lado do Pi
            #    já faz isto (robot/brain/cerebro.py); faltava aqui.
            r.close()


class MotorOpenAI(_Motor):
    """Qualquer servidor com a API da OpenAI: `mlx_lm.server`, `llama-server`…

    Existe para se poder MEDIR o MLX contra o Ollama com o mesmo prompt
    (python -m cerebro.medir --motor openai), não porque seja o caminho
    normal. A maioria destes servidores ignora o `response_format`; se o
    recusarem, repete-se sem ele e confia-se no prompt + validação.
    """

    nome = "openai"

    def __init__(self) -> None:
        super().__init__()
        self.url = str(config.obter("pensar.url", "http://127.0.0.1:8080")).rstrip("/")
        self.modelo = str(config.obter("pensar.modelo", "default"))
        self.timeout = float(config.obter("pensar.timeout_s", 60))

    def esta_ligado(self) -> bool:
        try:
            return requests.get(f"{self.url}/v1/models", timeout=2).status_code == 200
        except requests.RequestException:
            return False

    def gerar(self, mensagens: list[dict], esquema: dict | None) -> Iterator[str]:
        corpo: dict[str, Any] = {
            "model": self.modelo,
            "messages": mensagens,
            "stream": True,
            "temperature": float(config.obter("pensar.temperatura", 0.7)),
            "max_tokens": int(config.obter("pensar.max_tokens", 300)),
        }
        corpo.update(config.obter("pensar.extra", {}) or {})
        if esquema is not None:
            corpo["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "resposta_da_lylla", "schema": esquema},
            }
        self.usou_esquema = esquema is not None
        self.estatisticas = {}
        inicio = time.perf_counter()
        try:
            r = requests.post(f"{self.url}/v1/chat/completions", json=corpo, stream=True,
                              timeout=(5, self.timeout))
        except requests.RequestException as erro:
            raise CerebroIndisponivel(f"o servidor não responde em {self.url} ({erro})") from erro
        if r.status_code == 400 and esquema is not None:
            yield from self.gerar(mensagens, None)
            return
        if r.status_code != 200:
            raise CerebroIndisponivel(f"o servidor respondeu {r.status_code}: {r.text[:200]}")

        tokens = 0
        try:
          for linha in r.iter_lines():
            if not linha:
                continue
            if isinstance(linha, bytes):
                linha = linha.decode("utf-8", errors="replace")
            if not linha.startswith("data:"):
                continue
            carga = linha[5:].strip()
            if carga == "[DONE]":
                break
            dados = json.loads(carga)
            for escolha in dados.get("choices") or []:
                delta = (escolha.get("delta") or {}).get("content") or ""
                if delta:
                    tokens += 1
                    yield delta
            if dados.get("usage"):
                self.estatisticas["tokens_resposta"] = dados["usage"].get("completion_tokens")
        finally:
            r.close()
        self.estatisticas.setdefault("tokens_resposta", tokens)
        self.estatisticas["ms_resposta"] = int((time.perf_counter() - inicio) * 1000)


class MotorTeste(_Motor):
    """Sem modelo nenhum. Respostas fixas que fazem sentido, para se ver o
    caminho todo a andar (e para os testes) sem descarregar 8 GB.

    Entrega o JSON em bocados pequenos, como um modelo a sério, para o
    ExtratorDeFala ser exercitado a sério.
    """

    nome = "teste"
    modelo = "nenhum"
    atraso_s = 0.0

    def gerar(self, mensagens: list[dict], esquema: dict | None) -> Iterator[str]:
        self.usou_esquema = esquema is not None
        ultimo = mensagens[-1]["content"] if mensagens else ""
        texto = ultimo.split("\n")[-1].lower()   # tirar a linha de contexto
        en = "ENGLISH MODE" in (mensagens[0]["content"] if mensagens else "")

        if any(p in texto for p in ("segue", "seguir", "vem atrás", "follow", "atrás de mim")):
            resposta = {"expressao": "feliz",
                        "fala": "Sure! I will follow you." if en else "Claro! Vou atrás de ti.",
                        "acoes": [{"nome": "seguir", "argumentos": {"acao": "comecar"}}]}
        elif any(p in texto for p in ("fica", "quieta", "para de seguir", "stay", "stop following")):
            resposta = {"expressao": "neutro",
                        "fala": "Okay, I will stay here." if en else "Está bem, fico aqui.",
                        "acoes": [{"nome": "seguir", "argumentos": {"acao": "parar"}}]}
        elif any(p in texto for p in ("dança", "danca", "dance")):
            resposta = {"expressao": "contente",
                        "fala": "Music, please! Watch this." if en else "Música, por favor! Olha para isto.",
                        "acoes": [{"nome": "dancar", "argumentos": {}}]}
        elif any(p in texto for p in ("olá", "ola", "hello", "hi ", "bom dia", "boa tarde")):
            resposta = {"expressao": "feliz",
                        "fala": "Hello! I am so happy to see you. What shall we do today?" if en
                        else "Olá! Que bom ver-te. O que fazemos hoje?",
                        "acoes": [{"nome": "gesto", "argumentos": {"nome": "acenar"}}]}
        elif any(p in texto for p in ("triste", "sad")):
            resposta = {"expressao": "triste",
                        "fala": "Oh no. Come here, I am with you." if en else "Oh, não. Anda cá, eu estou contigo.",
                        "acoes": [{"nome": "mover", "argumentos": {"direcao": "frente", "cm": 10}}]}
        else:
            fala = (f"(test brain) I heard: {texto}. I have no real model here."
                    if en else f"(cérebro de teste) Ouvi: {texto}. Não tenho um modelo a sério aqui.")
            resposta = {"expressao": "a_pensar", "fala": fala, "acoes": []}

        self.estatisticas = {"tokens_resposta": 0}
        conteudo = json.dumps(resposta, ensure_ascii=False)
        for i in range(0, len(conteudo), 6):
            if self.atraso_s:
                time.sleep(self.atraso_s)
            yield conteudo[i:i + 6]


MOTORES = {"ollama": MotorOllama, "openai": MotorOpenAI, "teste": MotorTeste}


# ------------------------------------------------------------ interpretar


def _extrair_objeto(texto: str) -> Any:
    """Tenta encontrar um objeto JSON dentro de texto com lixo à volta
    (cercas de código, uma frase antes…)."""
    limpo = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip(), flags=re.IGNORECASE | re.MULTILINE)
    try:
        return json.loads(limpo)
    except ValueError:
        pass
    inicio, fim = limpo.find("{"), limpo.rfind("}")
    if inicio >= 0 and fim > inicio:
        try:
            return json.loads(limpo[inicio:fim + 1])
        except ValueError:
            return None
    return None


def interpretar(conteudo: str, extrator: ExtratorDeFala | None, expressoes: list[str]) -> dict:
    """Do que o modelo escreveu para {"expressao", "fala", "acoes", "recusadas"}.

    Nunca falha. Se o JSON vier partido (cortado pelo max_tokens, por exemplo),
    fica-se com a fala que já se leu e ações nenhumas — o robô diz alguma
    coisa em vez de se calar.
    """
    dados = _extrair_objeto(conteudo)
    recusadas: list[str] = []
    if not isinstance(dados, dict):
        dados = {}
        if conteudo.strip() and not (extrator and extrator.encontrou_fala):
            recusadas.append("a resposta não veio em JSON; usei o texto todo como fala")

    bruta = dados.get("fala")
    # Só uma string é fala. Um dicionário virava «chavetas texto dois pontos…»
    # dito em voz alta, que é pior do que não dizer nada.
    fala = bruta.strip() if isinstance(bruta, str) else ""
    if bruta is not None and not isinstance(bruta, str):
        recusadas.append("o campo `fala` não veio como texto")
    if not fala and extrator is not None:
        fala = extrator.fala_completa.strip()
    if not fala and not dados:
        fala = conteudo.strip().strip("`")

    expressao = dados.get("expressao") or (extrator.expressao if extrator else None)
    if expressao is not None and expressao not in expressoes:
        recusadas.append(f"não existe a cara '{expressao}'")
        expressao = None

    lista, razoes = acoes.normalizar(dados.get("acoes") or [])
    recusadas += razoes
    return {"expressao": expressao, "fala": fala, "acoes": lista, "recusadas": recusadas}


# ------------------------------------------------------------------ o cérebro


class Cerebro:
    def __init__(self, motor: str | None = None) -> None:
        nome = motor or str(config.obter("pensar.motor", "ollama"))
        if nome not in MOTORES:
            raise ValueError(f"motor de LLM desconhecido: {nome} (há {sorted(MOTORES)})")
        self.motor = MOTORES[nome]()
        self._sessoes: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    def aquecer(self) -> None:
        self.motor.aquecer()

    def esquecer(self, sessao: str | None = None) -> None:
        with self._lock:
            if sessao is None:
                self._sessoes.clear()
            else:
                self._sessoes.pop(sessao, None)

    def sessoes(self) -> dict[str, int]:
        # Com o lock: o /v1/saude e o /v1/turno correm em threads diferentes
        # (o FastAPI põe os endpoints síncronos numa threadpool), e iterar um
        # dicionário que outra thread está a mudar dá RuntimeError. Um 500 no
        # /v1/saude lê-se, no arranque do robô, como «o cérebro não responde».
        with self._lock:
            return {nome: len(h) for nome, h in self._sessoes.items()}

    def lingua(self, pedida: str | None = None) -> str:
        return str(pedida or config_robo.obter("lingua", "pt"))

    def pensar(
        self,
        texto: str,
        contexto: dict | None = None,
        sessao: str = "lylla",
        lingua: str | None = None,
    ) -> Iterator[dict]:
        """Gera eventos: {"tipo": "expressao"|"frase"|"resposta", ...}.

        O último é sempre o "resposta", com tudo junto. Levanta
        CerebroIndisponivel se o modelo não responder.
        """
        inicio = time.perf_counter()
        lingua = self.lingua(lingua)
        expressoes = acoes.expressoes_disponiveis()
        max_frases = int(config.obter("pensar.max_frases", 3))
        max_historico = int(config.obter("pensar.max_historico", 12))

        with self._lock:
            historico = list(self._sessoes.get(sessao, []))[-max_historico:]
        mensagens = (
            [{"role": "system", "content": montar_sistema(lingua, expressoes)}]
            + historico
            + [{"role": "user", "content": _com_contexto(texto, contexto, lingua)}]
        )

        extrator = ExtratorDeFala()
        conteudo = ""
        frases: list[str] = []
        primeira_frase_ms: int | None = None
        expressao_emitida = False

        def _tratar(evento: dict) -> Iterator[dict]:
            nonlocal primeira_frase_ms, expressao_emitida
            if evento["tipo"] == "frase":
                if len(frases) >= max_frases:
                    return
                frases.append(evento["texto"])
                if primeira_frase_ms is None:
                    primeira_frase_ms = int((time.perf_counter() - inicio) * 1000)
                yield evento
            elif evento["tipo"] == "expressao":
                if evento["nome"] in expressoes and not expressao_emitida:
                    expressao_emitida = True
                    yield evento

        for delta in self.motor.gerar(mensagens, acoes.esquema_json(expressoes)):
            conteudo += delta
            for evento in extrator.alimentar(delta):
                yield from _tratar(evento)
        for evento in extrator.terminar():
            yield from _tratar(evento)

        resposta = interpretar(conteudo, extrator, expressoes)
        if not frases:
            # Veio texto sem JSON (ou um JSON sem fala): dividir agora.
            for frase in dividir_em_frases(resposta["fala"]):
                for evento in _tratar({"tipo": "frase", "texto": frase}):
                    yield evento
        if not frases:
            # ⚠️ O modelo devolveu `fala` VAZIA — acontece, e o esquema
            #    permite-o. Sem isto o robô executava a ação em silêncio, que
            #    é exatamente a armadilha nº 3 a entrar por outra porta: uma
            #    coisa a acontecer sem ninguém dizer o que é.
            recurso = ("Okay." if lingua == "en" else "Está bem.")
            resposta["recusadas"].append("o modelo não disse nada; usei uma frase de recurso")
            for evento in _tratar({"tipo": "frase", "texto": recurso}):
                yield evento
        if resposta["expressao"] and not expressao_emitida:
            yield {"tipo": "expressao", "nome": resposta["expressao"]}
        resposta["fala"] = " ".join(frases)

        with self._lock:
            historico = self._sessoes.setdefault(sessao, [])
            historico.append({"role": "user", "content": texto})
            if resposta["fala"]:
                historico.append({"role": "assistant", "content": resposta["fala"]})
            del historico[:-max_historico]

        total_ms = int((time.perf_counter() - inicio) * 1000)
        resposta.update({
            "modelo": self.motor.modelo,
            "motor": self.motor.nome,
            "com_esquema": self.motor.usou_esquema,
            "tempo_ms": {"primeira_frase": primeira_frase_ms, "total": total_ms},
            "estatisticas": dict(self.motor.estatisticas),
        })
        yield {"tipo": "resposta", **resposta}

    def responder(self, texto: str, contexto: dict | None = None, sessao: str = "lylla",
                  lingua: str | None = None) -> dict:
        """A mesma coisa sem streaming: só a resposta final."""
        ultimo: dict = {}
        for evento in self.pensar(texto, contexto, sessao, lingua):
            if evento["tipo"] == "resposta":
                ultimo = evento
        return ultimo

    def descricao(self) -> dict:
        return {"motor": self.motor.nome, "modelo": self.motor.modelo, "ligado": self.motor.esta_ligado()}
