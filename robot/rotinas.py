"""ROTINAS — listas de pequenos enriquecimentos que dão vida ao robô.

Um ENRIQUECIMENTO é uma coisa pequena e instantânea que o robô faz para se
mostrar vivo: um bip, uma cor nas luzes, uma cara, um «hmm». Cada um vive no
módulo a que pertence (as luzes no glow.py, os sons no sons.py, os «hmm» no
enchimentos.py) e regista-se com um nome:

    @enriquecimento("luz.a_ouvir")
    def a_ouvir(): ...

Uma ROTINA é só uma lista desses nomes, para um momento da conversa:

    "ouvi": ["som.ouvi", "luz.a_pensar", "olhos.a_pensar"]

As rotinas por omissão estão aqui em baixo; a secção `rotinas:` do config/robot.yaml pode mudar
qualquer uma sem mexer em código — é um bom sítio para a Lara experimentar.

Duas regras que não se negoceiam:
  · um enriquecimento NUNCA bloqueia — o robô está a meio de uma conversa;
  · um enriquecimento NUNCA rebenta — um LED que falha não pode calar o robô.

Nomes com prefixo servem famílias inteiras sem registar uma a uma:
  `olhos.<cara>` → eyes.expressao(<cara>)     `gesto.<nome>` → gestures
"""

from __future__ import annotations

import importlib
from typing import Callable

from robot import config

_REGISTO: dict[str, Callable[[], object]] = {}
_PREFIXOS: dict[str, Callable[[str], object]] = {}
_carregado = False

# Os módulos que registam enriquecimentos. Importados só quando é preciso, para
# este ficheiro não arrastar hardware nenhum quando é importado.
MODULOS = ("robot.hardware.glow", "robot.voice.sons", "robot.voice.enchimentos")

# Os momentos de uma conversa, pela ordem em que acontecem.
ROTINAS_OMISSAO: dict[str, list[str]] = {
    # 1. OUVIR
    "acordar":       ["luz.a_ouvir", "olhos.atento", "som.a_ouvir"],
    # 3. CONFIRMAR — ela calou-se: reagir JÁ, antes de a rede responder
    "ouvi":          ["som.ouvi", "luz.a_pensar", "olhos.a_pensar"],
    "a_pensar":      ["voz.hmm"],                 # o mini vai ao LLM
    "a_pensar_muito": ["voz.deixa_pensar"],       # … e vai pensar a sério
    # 4. EXECUTAR
    "a_falar":       ["luz.a_falar"],
    "a_agir":        ["luz.a_agir"],
    "acabei":        ["luz.repouso"],
    # Quando corre mal
    "nao_ouvi":      ["luz.confusa", "olhos.triste"],
    "sem_cerebro":   ["luz.erro", "olhos.sem_rede"],
    # Fora da conversa
    "adormecer":     ["luz.a_dormir"],
    # O registo da cara (perception/registo.py)
    "foto_preparar": ["luz.preparar"],
    "foto_boa":      ["luz.boa", "som.boa"],
    "foto_ma":       ["luz.ma"],
    "registo_feito": ["luz.festa", "olhos.coracao", "som.festa"],
}


def enriquecimento(nome: str):
    """Decorador: regista uma função sem argumentos com este nome."""
    def registar(funcao):
        _REGISTO[nome] = funcao
        return funcao
    return registar


def familia(prefixo: str):
    """Decorador: regista uma função que recebe o resto do nome
    (`olhos.feliz` → funcao("feliz"))."""
    def registar(funcao):
        _PREFIXOS[prefixo] = funcao
        return funcao
    return registar


@familia("olhos")
def _olhos(nome: str) -> None:
    from robot.hardware import eyes

    eyes.expressao(nome)


@familia("gesto")
def _gesto(nome: str) -> None:
    from robot.brain import tools

    tools.executar("gesto", {"nome": nome})


def _carregar() -> None:
    global _carregado
    if _carregado:
        return
    _carregado = True
    for modulo in MODULOS:
        try:
            importlib.import_module(modulo)
        except Exception as erro:  # noqa: BLE001
            print(f"⚠️  rotinas: não carreguei {modulo} ({erro})")


def conhecidos() -> list[str]:
    _carregar()
    return sorted(_REGISTO) + [f"{p}.<nome>" for p in sorted(_PREFIXOS)]


def rotina(nome: str) -> list[str]:
    """Os passos de uma rotina: o robot.yaml (secção rotinas) ganha às omissões."""
    personalizadas = config.obter(f"rotinas.{nome}")
    if isinstance(personalizadas, list):
        return [str(p) for p in personalizadas]
    return list(ROTINAS_OMISSAO.get(nome, []))


def fazer(passo: str) -> bool:
    """Faz UM enriquecimento. Devolve False se não existir ou falhar."""
    _carregar()
    funcao = _REGISTO.get(passo)
    try:
        if funcao is not None:
            funcao()
            return True
        prefixo, _, resto = passo.partition(".")
        if prefixo in _PREFIXOS and resto:
            _PREFIXOS[prefixo](resto)
            return True
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  enriquecimento '{passo}' falhou: {erro}")
        return False
    print(f"⚠️  não conheço o enriquecimento '{passo}'. Há: {', '.join(conhecidos())}")
    return False


def correr(nome: str) -> None:
    """Corre todos os passos da rotina `nome`, por ordem. Nunca levanta."""
    for passo in rotina(nome):
        fazer(passo)
