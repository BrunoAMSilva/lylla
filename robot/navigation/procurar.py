"""ÀS ESCONDIDAS — procurar uma pessoa pela casa.

Isto não é um algoritmo novo: é o `ir_para` usado sete vezes seguidas, com
duas ideias por cima.

  1. A ORDEM POR ONDE PROCURA NÃO É AO ACASO. Vai primeiro aos sítios onde
     já encontrou aquela pessoa antes, e entre dois sítios igualmente
     prováveis vai ao mais perto. É a estratégia que qualquer pessoa usa a
     jogar às escondidas com um irmão, e é a razão de o robô parecer que
     está a jogar em vez de estar a patrulhar.

  2. AO CHEGAR A UMA DIVISÃO, DÁ UMA VOLTA SOBRE SI. A câmara vê ~60° e a
     Lara pode estar atrás da porta. Entrar e ir logo embora era garantir
     não a encontrar.

A memória vive em data/esconderijos.json e é uma contagem, não uma rede: cada
vez que a encontra na cozinha, a cozinha sobe um ponto. É a coisa mais burra
que funciona — e, ao contrário de uma rede, a Lara pode abrir o ficheiro e
perceber porque é que ele foi primeiro à cozinha.

⚠️ NÃO ESTÁ NO CATÁLOGO DE AÇÕES DO LLM, e é uma decisão, não um esquecimento:
   o acoes.py avisa que os modelos pequenos escolhem bem entre 6 a 8 ações e
   que acima disso se baralham. Com o `ir_para` já vamos em oito. Para pôr o
   jogo na boca da Lara, ver o fim de docs/navegacao.md — são seis linhas —
   e vigiar se o modelo continua a acertar nas outras ações. Hoje joga-se com
   `python scripts/escondidas.py`.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

from robot import config
from robot.hardware import motors
from robot.navigation import ir_para

RAIZ = Path(__file__).resolve().parents[2]
FICHEIRO_MEMORIA = RAIZ / "data" / "esconderijos.json"


@dataclass
class Passo:
    razao: str = "parado"
    terminou: bool = False
    encontrou: bool = False
    onde: str | None = None


_activo = False
_quem = ""
_por_visitar: list[int] = []
_fase = "parado"          # "a_ir" · "a_espreitar" · "parado"
_espreita_ate = 0.0
_visitadas: list[str] = []
_alvo_nome = ""
_perdida = False
_inicio = 0.0


def _cfg(chave: str, omissao):
    return config.obter(f"navegacao.{chave}", omissao)


# ---------------------------------------------------------------------------
# A memória dos esconderijos
# ---------------------------------------------------------------------------

def memoria() -> dict:
    try:
        return json.loads(FICHEIRO_MEMORIA.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _guardar(mem: dict) -> None:
    try:
        FICHEIRO_MEMORIA.parent.mkdir(parents=True, exist_ok=True)
        FICHEIRO_MEMORIA.write_text(json.dumps(mem, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Não consegui guardar os esconderijos: {erro}")


def aprender(quem: str, divisao: str) -> None:
    """Encontrei-a aqui. Da próxima venho cá primeiro."""
    mem = memoria()
    de_quem = mem.setdefault(quem.lower(), {})
    de_quem[divisao] = int(de_quem.get(divisao, 0)) + 1
    _guardar(mem)


def esquecer(quem: str | None = None) -> None:
    """Para quando o jogo fica previsível — ou para a Lara poder fazer batota."""
    if quem is None:
        _guardar({})
        return
    mem = memoria()
    mem.pop(quem.lower(), None)
    _guardar(mem)


# ---------------------------------------------------------------------------
# Por onde começar
# ---------------------------------------------------------------------------

def ordem_de_procura(quem: str) -> list[int]:
    """As divisões, da mais provável para a menos provável.

    pontos = quantas vezes já a encontrei ali  −  o que me custa lá chegar

    Os pesos estão à vista de propósito: subir o 2.0 faz um robô teimoso, que
    vai sempre ao mesmo sítio; subir o 0.3 faz um robô preguiçoso, que
    percorre a casa por ordem de distância. O jogo interessante está no meio.
    """
    casa = ir_para._casa
    if casa is None:
        return []
    mem = memoria().get(quem.lower(), {})
    pontos = []
    for k, divisao in enumerate(casa.divisoes):
        if not any(z == k for z in casa.zona):
            continue
        campo = casa.campo_ate(k)
        d = casa.distancia_em(campo, ir_para._pose.x, ir_para._pose.y)
        if not math.isfinite(d):
            continue                      # sem porta: não vale a pena tentar
        vezes = int(mem.get(divisao.nome, 0))
        pontos.append((vezes * 2.0 - (d / 100.0) * 0.3, k))
    pontos.sort(reverse=True)
    return [k for _, k in pontos]


# ---------------------------------------------------------------------------
# Jogar
# ---------------------------------------------------------------------------

def comecar(quem: str = "Lara") -> tuple[str, str]:
    global _activo, _quem, _por_visitar, _fase, _visitadas, _inicio
    erro = ir_para.carregar()
    if erro:
        return ("recusa", erro)
    if not ir_para.permitido():
        return ("recusa", "I'm not allowed to walk around the house on my own yet.")
    _quem = quem or "Lara"
    _por_visitar = ordem_de_procura(_quem)
    if not _por_visitar:
        return ("recusa", "I don't know where to start looking.")
    _visitadas = []
    _activo = True
    _fase = "parado"
    _inicio = time.monotonic()
    _proxima_divisao()
    return ("a_procurar", f"Ready or not, here I come! I'll start {_onde_vou()}.")


def parar() -> None:
    global _activo, _fase
    _activo = False
    _fase = "parado"
    ir_para.parar()
    motors.parar()


def a_procurar() -> bool:
    return _activo


def estado() -> dict:
    return {"a_procurar": _activo, "quem": _quem, "fase": _fase,
            "ja_vi": list(_visitadas), "faltam": len(_por_visitar)}


def _onde_vou() -> str:
    return ir_para.em_ingles(_alvo_nome, "por") if _alvo_nome else "right here"


def _proxima_divisao() -> bool:
    """Aponta à divisão seguinte da lista.

    False quer dizer «não há para onde ir» — e há duas maneiras muito
    diferentes de isso acontecer: já vi a casa toda, ou já não sei onde
    estou. A segunda não é o fim do jogo, é uma pergunta (ver _perdida).
    """
    global _fase, _alvo_nome, _perdida
    casa = ir_para._casa
    _perdida = False
    while _por_visitar:
        k = _por_visitar.pop(0)
        nome = _alvo_nome = casa.divisoes[k].nome
        estado, mensagem = ir_para.comecar(nome)
        if estado == "a_ir":
            _fase = "a_ir"
            return True
        if estado == "ja_estou":
            _visitadas.append(nome)
            _comecar_a_espreitar()
            return True
        if mensagem == ir_para.PERDIDA:
            # A odometria gastou-se. Numa casa não há como corrigir isto
            # sozinho — mas há uma pessoa mesmo ali, a jogar. Perguntar-lhe é
            # a correção mais barata que existe, e dá um jogo melhor do que
            # um robô que desiste sem dizer porquê.
            _por_visitar.insert(0, k)
            _perdida = True
            _fase = "a_perguntar"
            return False
    _fase = "parado"
    _alvo_nome = ""
    return False


def _comecar_a_espreitar() -> None:
    global _fase, _espreita_ate
    _fase = "a_espreitar"
    _espreita_ate = time.monotonic() + float(_cfg("segundos_a_espreitar", 6.0))


def um_passo(obs) -> Passo:
    """Uma volta do jogo. `obs` é a observação da câmara (attention.Observacao).

    Quem chama isto é o ciclo principal, ~10x por segundo, e passa-lhe o que
    a câmara está a ver neste instante.
    """
    global _fase
    if not _activo:
        return Passo()

    casa = ir_para._casa

    # --- encontrou? Isto vem antes de tudo, inclusive a meio do caminho ----
    if obs is not None and getattr(obs, "presente", False) and obs.nome:
        if obs.nome.lower() == _quem.lower():
            onde = _divisao_atual()
            if onde:
                aprender(_quem, onde)
            parar()
            return Passo(razao="encontrei", terminou=True, encontrou=True, onde=onde)

    if _fase == "a_ir":
        passo = ir_para.um_passo()
        if passo.razao == "precipício":
            parar()
            return Passo(razao="precipício", terminou=True)
        if passo.terminou:
            nome = casa.divisoes[ir_para._destino].nome if casa else "?"
            _visitadas.append(nome)
            if passo.chegou:
                _comecar_a_espreitar()
                return Passo(razao=f"cheguei {ir_para.com_artigo(nome)}, vou espreitar")
            # não chegou (perdeu-se, encravou): tenta a divisão seguinte
            if not _proxima_divisao():
                if _perdida:
                    motors.parar()
                    return Passo(razao="onde estou", terminou=True)
                parar()
                return Passo(razao="desisti", terminou=True)
            return Passo(razao=f"não consegui ir {ir_para.com_artigo(nome)}, vou tentar outro sítio")
        return Passo(razao="a caminho")

    if _fase == "a_espreitar":
        if time.monotonic() < _espreita_ate:
            v = float(_cfg("velocidade_espreitar", 0.22))
            motors.mover(-v, v)          # uma volta lenta sobre si própria
            return Passo(razao="a espreitar")
        motors.parar()
        if not _proxima_divisao():
            if _perdida:
                motors.parar()
                return Passo(razao="onde estou", terminou=True)
            parar()
            return Passo(razao="não te encontrei", terminou=True)
        return Passo(razao="não estás aqui, vou ao próximo sítio")

    if _fase == "a_perguntar":
        motors.parar()
        return Passo(razao="à espera que me digam onde estou")

    return Passo()


def a_perguntar() -> bool:
    """Está parada à espera que alguém lhe diga em que divisão está."""
    return _activo and _fase == "a_perguntar"


def responder(divisao: str) -> tuple[str, str]:
    """«Estás na cozinha.» — repõe a posição e o jogo continua de onde ia."""
    if not _activo:
        return ("recusa", "We're not playing right now.")
    erro = ir_para.assumir(divisao)
    if erro:
        return ("recusa", erro)
    if not _proxima_divisao():
        parar()
        return ("fim", "I looked in the whole house. Where are you?")
    return ("a_procurar", f"Aha! Then I'll keep looking {_onde_vou()}.")


def _divisao_atual() -> str | None:
    casa = ir_para._casa
    if casa is None:
        return None
    cx = int(ir_para._pose.x // casa.cm)
    cy = int(ir_para._pose.y // casa.cm)
    if not casa.dentro(cx, cy):
        return None
    z = casa.zona[casa.i(cx, cy)]
    return casa.divisoes[z].nome if z >= 0 else None
