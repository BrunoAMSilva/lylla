"""Testes da camada que a Lara usa.

    pytest tests/test_lylla.py

Existem por uma razão: o `lylla.py` é o ficheiro que ELA vai mexer. Se um
comando rebentar com um traceback de dez linhas, ela não aprende programação —
aprende que programar é assustador. Por isso o teste mais importante aqui é o
último: nenhum comando pode levantar uma exceção, nem com o robô desligado,
nem com um nome de cor inventado.

Tudo corre em simulação, portanto passa no Mac, no Pi e sem mBot2 nenhum.
"""

from __future__ import annotations

import pytest

from robot import config
from robot.hardware import mbot2, motors


@pytest.fixture(autouse=True)
def _em_simulacao(monkeypatch):
    monkeypatch.setenv("ROBO_SIMULAR", "1")
    config.a_simular.cache_clear()
    yield
    config.a_simular.cache_clear()


@pytest.fixture()
def lylla():
    import lylla as modulo

    modulo.no_chao()
    modulo.normal()
    return modulo


# ---------------------------------------------------------------------------
def test_a_ajuda_nao_mente(lylla, capsys):
    """Tudo o que está no `ajuda()` tem de existir, e ao contrário também.

    Uma ajuda desatualizada é pior do que nenhuma: manda a Lara escrever
    comandos que já não existem.
    """
    lylla.ajuda()
    texto = capsys.readouterr().out
    for comando in lylla.__all__:
        assert comando in texto, f"o comando '{comando}' não está no ajuda()"


def test_andar_devolve_quanto_andou(lylla):
    andou = lylla.andar(30)
    assert andou == pytest.approx(30, abs=1)


def test_andar_vai_aos_bocados_e_nao_passa_do_pedido(lylla):
    assert lylla.andar(25) <= 26


def test_nao_anda_mais_de_dois_metros_de_uma_vez(lylla):
    assert lylla.andar(500) == pytest.approx(200, abs=1)


def test_nao_anda_se_o_caminho_nao_estiver_livre(lylla, monkeypatch):
    monkeypatch.setattr(lylla.mover, "distancia", lambda: 5.0)
    assert lylla.andar(50) == 0.0


def test_em_cima_da_mesa_baixa_o_teto_da_velocidade(lylla):
    lylla.em_cima_da_mesa()
    teto = float(config.obter("secretaria.velocidade_max", 0.25))
    assert abs(motors._limitar(1.0)) <= teto + 1e-9
    lylla.no_chao()


def test_olhos_e_luz_desconhecidos_nao_rebentam(lylla, capsys):
    lylla.olhos("banana")
    lylla.luz("dourado")
    texto = capsys.readouterr().out
    assert "não conheço" in texto


def test_emocoes_e_cores_anunciadas_existem_mesmo(lylla):
    for emocao in mbot2.EMOCOES:
        assert mbot2.olhos(emocao) is True
    for cor in mbot2.CORES:
        assert mbot2.luz(cor) is True
    assert mbot2.luz("apagar") is True


def test_o_driver_aguenta_nao_haver_robo():
    """Em simulação nada disto tem hardware por baixo, e nada disto pode rebentar."""
    mbot2.velocidade(50, 50)
    mbot2.parar()
    mbot2.travar(False)
    mbot2.zerar()
    assert mbot2.andados_cm() == (0.0, 0.0)
    assert mbot2.rodou_graus() == 0.0
    assert mbot2.estado()["simulado"] is True


def test_o_conta_quilometros_funciona_ate_em_simulacao(lylla):
    """A Lara aprende no Mac. Uma lição que só funciona com o robô ligado é
    meia lição — por isso o modo simulação também conta os centímetros."""
    lylla.zerar()
    lylla.andar(30)
    assert lylla.quanto_andei() == pytest.approx(30, abs=3)
    lylla.zerar()
    lylla.virar_direita(90)
    assert mbot2.rodou_graus() > 0          # direita é positivo


def test_a_conta_dos_rpm_esta_certa():
    """18 cm/s em rodas de 8 cm são ~43 RPM. Se isto mudar, o robô anda a mais."""
    assert mbot2.cms_para_rpm(18.0) == pytest.approx(43.0, abs=1.0)
    assert mbot2.rpm_para_cms(43.0) == pytest.approx(18.0, abs=0.5)


# Estes cinco nomes do `__all__` não são comandos para chamar sem argumentos:
# são as bibliotecas e o decorador. O resto tem de funcionar à seca.
NAO_SAO_COMANDOS = ("mover", "ver", "voz", "luzes", "comandos", "comando")


def test_nenhum_comando_rebenta(lylla):
    """O teste que interessa: chamar tudo, sem argumentos, sem robô."""
    for nome in lylla.__all__:
        if nome in NAO_SAO_COMANDOS:
            continue
        funcao = getattr(lylla, nome)
        if nome == "esperar":
            funcao(0)
            continue
        funcao()           # se algum destes levantar, o teste falha aqui


# ---------------------------------------------------------------------------
# As bibliotecas e os comandos que a Lara escreve
# ---------------------------------------------------------------------------
def test_as_bibliotecas_existem_todas(lylla):
    """`from lylla import ver, voz, mover, luzes, comandos` tem de funcionar."""
    for nome in ("mover", "ver", "voz", "luzes", "comandos"):
        assert hasattr(lylla, nome), f"falta a biblioteca {nome}"


def test_um_comando_ensinado_e_encontrado_pela_frase(lylla):
    from robot.brain import comandos_diretos

    lylla.comandos.esquecer_todos()

    @lylla.comando("fazer o pino")
    def _():
        return "Feito o pino!"

    assert comandos_diretos.tentar("Olá Lylla, fazer o pino") == "Feito o pino!"
    assert comandos_diretos.tentar("fazer o pino") == "Feito o pino!"
    lylla.comandos.esquecer_todos()


def test_um_comando_da_lara_nunca_tapa_o_para(lylla):
    """⚠️ O teste mais importante deste ficheiro.

    Se ela ensinar (à experiência, ou por engano) a palavra «pára», a travagem
    de emergência tem de continuar a ganhar. Segurança primeiro, mesmo contra
    código nosso.
    """
    from robot.brain import comandos_diretos

    lylla.comandos.esquecer_todos()

    @lylla.comando("para")
    def _():
        return "isto nunca devia aparecer"

    assert comandos_diretos.tentar("Olá Lylla, pára") != "isto nunca devia aparecer"
    lylla.comandos.esquecer_todos()


def test_um_comando_que_rebenta_nao_mata_o_robo(lylla):
    from robot.brain import comandos_diretos

    lylla.comandos.esquecer_todos()

    @lylla.comando("comando marado")
    def _():
        raise ValueError("erro de propósito")

    resposta = comandos_diretos.tentar("comando marado")
    assert resposta and "Enganei-me" in resposta
    lylla.comandos.esquecer_todos()


def test_o_arranque_carrega_os_comandos_da_lara(lylla, monkeypatch):
    import sys

    from robot import main

    lylla.comandos.esquecer_todos()
    monkeypatch.delitem(sys.modules, "meus_comandos", raising=False)

    main._carregar_comandos_da_lara()

    assert "adicionar face" in lylla.comandos.conhecidos()
    assert "da uma volta" in lylla.comandos.conhecidos()
    lylla.comandos.esquecer_todos()


def test_um_erro_nos_comandos_da_lara_nao_impede_o_arranque(lylla, monkeypatch, capsys):
    from robot import main

    def falhar(_nome):
        raise SyntaxError("parêntesis em falta")

    monkeypatch.setattr(main.importlib, "import_module", falhar)

    main._carregar_comandos_da_lara()

    assert "Não consegui carregar meus_comandos.py" in capsys.readouterr().out


def test_guardar_face_diz_a_privacidade_antes_de_qualquer_pose(lylla):
    """A frase sobre o que fica guardado vem SEMPRE em primeiro lugar."""
    ditas = []
    lylla.ver.guardar_face("Teste", aviso=ditas.append)
    assert ditas, "não disse nada nenhuma"
    assert ditas[0] == lylla.ver.PRIVACIDADE
    assert any("olha para mim" in d for d in ditas)


def test_guardar_face_em_simulacao_nao_guarda_nada(lylla):
    assert lylla.ver.guardar_face("Teste", aviso=lambda _: None) is False
