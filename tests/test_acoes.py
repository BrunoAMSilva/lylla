"""Testes do CONTRATO entre o robô e o cérebro.

    pytest tests/test_acoes.py

Este ficheiro existe por uma razão: o LLM corre noutra máquina e pode
devolver qualquer coisa. O que o protege não é o modelo ser bom — é esta
validação. Se ela se partir, o robô passa a obedecer a números inventados,
e o primeiro sítio onde isso se nota é uma parede.
"""

from __future__ import annotations

import json

import pytest

from robot.brain import acoes


# ---------------------------------------------------------------------------
# 1 · O catálogo é coerente com o robô
# ---------------------------------------------------------------------------


def test_todas_as_acoes_tem_implementacao_no_pi():
    """Uma ação que o cérebro pode pedir e o Pi não sabe fazer é um robô que
    responde "não sei fazer isso" a uma coisa que ele próprio ofereceu."""
    from robot.brain import tools

    for nome in acoes.ACOES:
        assert nome in tools.IMPLEMENTACOES, f"falta implementar '{nome}' no tools.py"


def test_os_gestos_e_as_caras_do_catalogo_existem_mesmo():
    from robot.expressions import EXPRESSOES
    from robot.gestures import GESTOS

    assert set(acoes.ACOES["gesto"]["parametros"]["nome"]["enum"]) <= set(GESTOS)
    assert set(acoes.expressoes_disponiveis()) == set(EXPRESSOES)


def test_o_catalogo_e_pequeno():
    """Acima de 6-8 ferramentas os modelos pequenos começam a escolher mal.
    Se este teste falhar, a pergunta certa é o que se pode TIRAR."""
    assert len(acoes.ACOES) <= 8, f"{len(acoes.ACOES)} ações é demasiado para um modelo pequeno"


# ---------------------------------------------------------------------------
# 2 · O esquema JSON
# ---------------------------------------------------------------------------


def test_o_esquema_poe_a_cara_antes_da_fala():
    """A ordem não é estética: o modelo gera por ordem, e é isto que deixa o
    robô mudar de cara antes de a primeira palavra sair."""
    chaves = list(acoes.esquema_json()["properties"])
    assert chaves == ["expressao", "fala", "acoes"]


def test_o_esquema_e_json_valido_e_fechado():
    esquema = acoes.esquema_json()
    json.dumps(esquema)     # tem de ser serializável para ir no pedido
    assert esquema["required"] == ["expressao", "fala", "acoes"]
    nomes = {v["properties"]["nome"]["enum"][0] for v in esquema["properties"]["acoes"]["items"]["anyOf"]}
    assert nomes == set(acoes.ACOES)


def test_a_descricao_para_o_prompt_menciona_todas_as_acoes():
    texto = acoes.descricao_para_prompt()
    for nome in acoes.ACOES:
        assert nome in texto


# ---------------------------------------------------------------------------
# 3 · Validação — o que o robô recusa
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("acao", [
    {"nome": "mover", "argumentos": {"direcao": "frente", "cm": 20}},
    {"nome": "mover", "argumentos": {"direcao": "tras"}},          # cm é opcional
    {"nome": "virar", "argumentos": {"graus": -90}},
    {"nome": "dancar", "argumentos": {}},
    {"nome": "seguir", "argumentos": {"acao": "parar"}},
])
def test_aceita_o_que_e_valido(acao):
    ok, razao = acoes.validar(acao)
    assert ok, razao


@pytest.mark.parametrize("acao, pedaco", [
    ({"nome": "voar", "argumentos": {}}, "não existe"),
    ({"nome": "mover", "argumentos": {"direcao": "frente", "cm": 5000}}, "no máximo"),
    ({"nome": "mover", "argumentos": {"direcao": "frente", "cm": 1}}, "pelo menos"),
    ({"nome": "mover", "argumentos": {"direcao": "para cima"}}, "tem de ser um de"),
    ({"nome": "mover", "argumentos": {}}, "falta o argumento"),
    ({"nome": "virar", "argumentos": {"graus": "muitos"}}, "número inteiro"),
    ({"nome": "virar", "argumentos": {"graus": True}}, "número inteiro"),
    ({"nome": "gesto", "argumentos": {"nome": "salto mortal"}}, "tem de ser um de"),
    ({"nome": "dancar", "argumentos": {"depressa": True}}, "não tem o argumento"),
    ({"nome": "mover", "argumentos": "frente"}, "não são um objeto"),
    ("mover", "não é um objeto"),
    (None, "não é um objeto"),
])
def test_recusa_o_que_nao_e(acao, pedaco):
    ok, razao = acoes.validar(acao)
    assert not ok
    assert pedaco in razao, razao


def test_a_ordem_de_5000_cm_e_recusada_ate_no_pi():
    """A dupla validação é de propósito: o cérebro filtra, mas quem mexe os
    motores valida outra vez. É a mesma ideia do pino OE."""
    from robot.brain import tools

    resposta = tools.executar("mover", {"direcao": "frente", "cm": 5000})
    assert "não posso" in resposta.lower()


# ---------------------------------------------------------------------------
# 4 · Normalizar — fica com o bom e deita fora o resto
# ---------------------------------------------------------------------------


def test_normalizar_fica_com_as_boas_e_explica_as_mas():
    validas, recusadas = acoes.normalizar([
        {"nome": "virar", "argumentos": {"graus": 90.0}},   # float → int
        {"nome": "voar", "argumentos": {}},
        {"nome": "gesto", "argumentos": {"nome": "acenar"}},
        "lixo",
    ])
    assert validas == [
        {"nome": "virar", "argumentos": {"graus": 90}},
        {"nome": "gesto", "argumentos": {"nome": "acenar"}},
    ]
    assert isinstance(validas[0]["argumentos"]["graus"], int)
    assert len(recusadas) == 2


def test_normalizar_aguenta_lixo_absoluto():
    assert acoes.normalizar(None) == ([], ["as ações não vieram numa lista"])
    assert acoes.normalizar("mover") == ([], ["as ações não vieram numa lista"])
    assert acoes.normalizar([]) == ([], [])


# ---------------------------------------------------------------------------
# 5 · Recusas — o robô tem de DIZER quando não faz
# ---------------------------------------------------------------------------


def test_uma_recusa_sabe_se_reconhecer():
    """O robô só fala o resultado de uma ação quando ela NÃO aconteceu. Se
    isto se partir, ou ele repete-se («Andei 20 cm» a seguir a já o ter dito),
    ou fica parado à frente de uma parede sem dizer porquê."""
    from robot.brain import tools

    recusa = tools.executar("mover", {"direcao": "para cima"})
    assert isinstance(recusa, tools.Recusa)
    assert isinstance(recusa, str), "continua a ser uma string em todo o lado"

    feito = tools.executar("expressao", {"nome": "feliz"})
    assert not isinstance(feito, tools.Recusa)


@pytest.mark.parametrize("nome, argumentos", [
    ("mover", {"direcao": "frente", "cm": 5000}),
    ("virar", {"graus": 900}),
    ("gesto", {"nome": "salto mortal"}),
    ("garra", {"acao": "trincar"}),
    ("voar", {}),
    ("seguir", {"acao": "voar"}),
    ("seguir", {"acao": "comecar"}),        # `seguir.ativo` vem desligado (D17)
])
def test_o_que_o_robo_recusa_e_sempre_uma_recusa(nome, argumentos):
    from robot.brain import tools

    assert isinstance(tools.executar(nome, argumentos), tools.Recusa)
