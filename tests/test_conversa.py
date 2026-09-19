"""A CONVERSA NOVA — memória por pessoa, perguntas que pedem explicação, as
pausas das crianças, os «hmm», as rotinas e o registo da cara só por voz.

    pytest tests/test_conversa.py
"""

from __future__ import annotations

import time

import pytest

from cerebro import pensar
from cerebro.memoria import Memoria
from robot import rotinas
from robot.brain.state import Maquina
from robot.voice import frases


# ---------------------------------------------------------------------------
# 1 · A memória é de cada pessoa
# ---------------------------------------------------------------------------


@pytest.fixture
def memoria(tmp_path):
    caminho = tmp_path / "memoria.json"
    caminho.write_text('{"partilhado": ["Bruno is Lara\'s father."],'
                       ' "pessoas": {"Lara": ["Lara loves cats."], "Bruno": ["Bruno audits websites."]}}')
    return Memoria(caminho)


@pytest.fixture
def cerebro_(memoria):
    c = pensar.Cerebro("teste", memoria=memoria)
    return c


def _sistema(c) -> str:
    return c.motor.ultimas_mensagens[0]["content"]


def test_o_que_o_bruno_contou_nao_aparece_a_lara(cerebro_):
    cerebro_.responder("olá", contexto={"pessoa": "Lara"})
    sistema = _sistema(cerebro_)
    assert "Lara loves cats." in sistema
    assert "Bruno is Lara's father." in sistema, "o partilhado vai para toda a gente"
    assert "audits" not in sistema, "o que o Bruno contou é do Bruno"


def test_o_historico_e_de_cada_pessoa(cerebro_):
    cerebro_.responder("I spent my day auditing", contexto={"pessoa": "Bruno"})
    cerebro_.responder("olá", contexto={"pessoa": "Lara"})
    mensagens = cerebro_.motor.ultimas_mensagens
    assert not any("auditing" in m["content"] for m in mensagens), \
        "a conversa do Bruno não entra na da Lara"
    cerebro_.responder("olá outra vez", contexto={"pessoa": "Bruno"})
    assert any("auditing" in m["content"] for m in cerebro_.motor.ultimas_mensagens)


def test_ela_guarda_o_que_a_pessoa_conta_sobre_si(cerebro_, memoria):
    r = cerebro_.responder("remember that I am in 5th grade", contexto={"pessoa": "Lara"})
    assert r["lembrar"] == ["i am in 5th grade"]
    assert "i am in 5th grade" in memoria.factos("Lara")
    assert "i am in 5th grade" not in memoria.factos("Bruno")
    # e sobrevive a um reinício
    assert "i am in 5th grade" in Memoria(memoria.caminho).factos("lara")


def test_de_quem_nao_conhece_nao_guarda_nada(cerebro_, memoria):
    antes = memoria.tudo()
    r = cerebro_.responder("remember that I love pizza", contexto={"pessoa": None})
    assert r["lembrar"] == []
    assert memoria.tudo() == antes


def test_a_memoria_nao_repete_factos(memoria):
    assert memoria.lembrar("Lara", ["Lara loves cats"]) == []
    assert memoria.lembrar("Lara", ["Lara has a cat called Nemo."]) == ["Lara has a cat called Nemo."]


def test_um_ficheiro_estragado_nao_cala_o_robo(tmp_path):
    caminho = tmp_path / "memoria.json"
    caminho.write_text("{isto não é json")
    assert Memoria(caminho).para_prompt("Lara") == ""


def test_ao_fim_de_15_minutos_comeca_uma_conversa_nova(cerebro_):
    cerebro_.responder("my favourite colour is green", contexto={"pessoa": "Lara"})
    chave = pensar.chave_de_sessao("lylla", "Lara")
    cerebro_._ultima_vez[chave] = time.time() - 16 * 60
    r = cerebro_.responder("olá", contexto={"pessoa": "Lara"})
    assert r["nova_conversa"] is True
    assert not any("green" in m["content"] for m in cerebro_.motor.ultimas_mensagens), \
        "passados 15 min fica só a memória, não a conversa"
    assert "Lara loves cats." in _sistema(cerebro_)


# ---------------------------------------------------------------------------
# 2 · Pensar só quando a pergunta pede uma explicação
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("texto,espera", [
    ("What are classes?", True), ("why is the sky blue", True),
    ("how does a robot see", True), ("O que são classes?", True),
    ("porque é que chove", True), ("explain gravity", True),
    ("hello", False), ("what is your name", False), ("how are you", False),
    ("dance!", False), ("estou triste porque choveu", False), ("what's up", False),
])
def test_quem_decide_se_se_pensa(texto, espera):
    assert pensar.pede_explicacao(texto) is espera


def test_uma_explicacao_liga_o_raciocinio_e_da_mais_frases(cerebro_):
    eventos = list(cerebro_.pensar("What are classes?", {"pessoa": "Lara"}))
    assert eventos[0] == {"tipo": "a_pensar", "explicar": True, "pessoa": "Lara"}
    opcoes = cerebro_.motor.ultimas_opcoes
    assert opcoes["extra"].get("think") is True
    assert opcoes["max_tokens"] >= 1000
    assert "explanation" in cerebro_.motor.ultimas_mensagens[-1]["content"] or \
        "explicação" in cerebro_.motor.ultimas_mensagens[-1]["content"]


def test_uma_conversa_normal_continua_rapida(cerebro_):
    eventos = list(cerebro_.pensar("olá", {"pessoa": "Lara"}))
    assert eventos[0]["explicar"] is False
    assert cerebro_.motor.ultimas_opcoes == {}


def test_as_regras_de_tutor_estao_sempre_la(cerebro_):
    cerebro_.responder("olá")
    sistema = _sistema(cerebro_)
    assert "HOW YOU HELP" in sistema or "COMO AJUDAS" in sistema


# ---------------------------------------------------------------------------
# 3 · No Pi: o «hmm» e o fim da frase
# ---------------------------------------------------------------------------


@pytest.fixture
def robo(monkeypatch):
    import robot.main as main
    from robot import config

    monkeypatch.setattr(config, "a_simular", lambda: False)
    corridas: list[str] = []
    ditas: list[str] = []
    monkeypatch.setattr(rotinas, "correr", lambda nome: corridas.append(nome))
    monkeypatch.setattr(main.speak, "falar", lambda t, esperar=True: ditas.append(str(t)))
    monkeypatch.setattr(main.speak, "tocar", lambda d, esperar=True: ditas.append("♪"))
    monkeypatch.setattr(main.speak, "esperar_acabar", lambda: None)
    monkeypatch.setattr(main.eyes, "expressao", lambda *a, **k: None)
    monkeypatch.setattr(main.eyes, "animar", lambda *a, **k: None)
    return main, corridas, ditas


def _turno(*eventos):
    def gerar():
        yield from eventos
    return gerar()


def test_o_hmm_sai_assim_que_o_mini_vai_pensar(robo):
    main, corridas, _ = robo
    main._consumir_turno(Maquina(), _turno(
        {"tipo": "ouvido", "texto": "hello"},
        {"tipo": "a_pensar", "explicar": False},
        {"tipo": "frase", "texto": "Hi!", "audio": b"x"},
        {"tipo": "resposta", "acoes": [], "recusadas": []},
        {"tipo": "fim"},
    ))
    assert corridas.index("a_pensar") < corridas.index("a_falar")


def test_uma_explicacao_leva_o_deixa_me_pensar(robo):
    main, corridas, _ = robo
    main._consumir_turno(Maquina(), _turno(
        {"tipo": "ouvido", "texto": "what are classes"},
        {"tipo": "a_pensar", "explicar": True},
        {"tipo": "frase", "texto": "Classes are…", "audio": b"x"},
        {"tipo": "fim"},
    ))
    assert "a_pensar_muito" in corridas and "a_pensar" not in corridas


def test_um_comando_direto_nao_leva_hmm(robo, monkeypatch):
    main, corridas, ditas = robo
    monkeypatch.setattr(main.comandos_diretos, "tentar", lambda t: "Stopped.")
    main._consumir_turno(Maquina(), _turno(
        {"tipo": "ouvido", "texto": "stop"},
        {"tipo": "a_pensar", "explicar": False},
    ))
    assert "a_pensar" not in corridas
    assert ditas == ["Stopped."]


def test_a_pausa_de_uma_crianca_no_principio_e_mais_comprida():
    import numpy as np

    from robot.voice import listen

    detetor = listen._Silencio(silencio_s=1.0)
    detetor.extra_inicio_s, detetor.fala_curta_s = 0.8, 1.5
    voz = np.full(1280, 0.2, dtype=np.float32)
    detetor.acabou(np.full(1280, 0.001, dtype=np.float32))   # a sala, antes de ela falar
    assert detetor.acabou(voz) is False
    assert detetor.progresso() < 0.01
    assert detetor.pausa_necessaria() == pytest.approx(1.8), "ainda mal começou a falar"
    for _ in range(25):                           # 2 s de fala
        detetor.acabou(voz)
    assert detetor.pausa_necessaria() == pytest.approx(1.0)


def test_sem_ela_comecar_a_falar_nao_espera_para_sempre(monkeypatch):
    import numpy as np

    from robot.voice import listen

    detetor = listen._Silencio()
    detetor.espera_inicio_s = 0.0
    assert detetor.acabou(np.zeros(1280, dtype=np.float32)) is True
    assert detetor.falou is False


# ---------------------------------------------------------------------------
# 4 · Rotinas
# ---------------------------------------------------------------------------


def test_um_enriquecimento_que_nao_existe_nao_rebenta(capsys):
    assert rotinas.fazer("luz.que_nao_existe") is False
    assert "não conheço" in capsys.readouterr().out


def test_um_enriquecimento_que_falha_nao_rebenta():
    @rotinas.enriquecimento("teste.rebenta")
    def _rebenta():
        raise RuntimeError("LED queimado")

    assert rotinas.fazer("teste.rebenta") is False


def test_o_robot_yaml_ganha_as_omissoes(monkeypatch):
    monkeypatch.setattr(rotinas.config, "obter",
                        lambda c, o=None: ["olhos.coracao"] if c == "rotinas.ouvi" else o)
    assert rotinas.rotina("ouvi") == ["olhos.coracao"]
    assert rotinas.rotina("acordar") == rotinas.ROTINAS_OMISSAO["acordar"]


def test_as_rotinas_por_omissao_so_usam_enriquecimentos_que_existem():
    conhecidos = set(rotinas.conhecidos())
    for nome, passos in rotinas.ROTINAS_OMISSAO.items():
        for passo in passos:
            prefixo = passo.split(".")[0]
            assert passo in conhecidos or f"{prefixo}.<nome>" in conhecidos, (nome, passo)


# ---------------------------------------------------------------------------
# 5 · O registo da cara só por voz
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("resposta,nome", [
    ("My name is Lara", "Lara"), ("I'm lara.", "Lara"), ("Lara!", "Lara"),
    ("chamo-me Lara", "Lara"), ("sou o Bruno", "Bruno"), ("yes", None),
    ("", None), ("I don't want to tell you my name today", None),
])
def test_percebe_o_nome(resposta, nome):
    from robot.perception import registo

    assert registo.extrair_nome(resposta) == nome


@pytest.mark.parametrize("resposta,sim", [
    ("yes", True), ("Yes, sure!", True), ("okay", True), ("sim, pode", True),
    ("no", False), ("no thanks", False), ("", False), ("simulation", False),
])
def test_o_sim_tem_de_ser_claro(resposta, sim):
    assert frases.e_um_sim(resposta) is sim


@pytest.fixture
def camara(monkeypatch):
    from robot import config
    from robot.perception import camera, faces

    monkeypatch.setattr(config, "a_simular", lambda: False)
    monkeypatch.setattr(camera, "disponivel", lambda: True)
    monkeypatch.setattr(camera, "tirar_foto", lambda: "imagem")
    monkeypatch.setattr(faces, "detetar", lambda img: ["cara"])
    monkeypatch.setattr(faces, "assinatura", lambda img, cara: [0.1] * 128)
    guardadas: dict = {}
    monkeypatch.setattr(faces, "guardar_pessoa", lambda n, v: guardadas.update({n: len(v)}))
    monkeypatch.setattr(faces, "carregar_conhecidos", lambda: None)
    monkeypatch.setattr(rotinas, "correr", lambda nome: None)
    monkeypatch.setattr("robot.perception.registo._segundos_para_posar", lambda: 0)
    return guardadas


def test_o_registo_pergunta_o_nome_e_a_licenca(camara):
    from robot.perception import registo

    ditas: list[str] = []
    respostas = iter(["My name is Lara", "yes"])
    registo.registar_pela_voz("", ditas.append, ouvir=lambda: next(respostas), fotos=3)
    assert camara == {"Lara": 3}
    assert ditas[0] == frases.dizer("registo_qual_nome")
    assert ditas[1] == frases.dizer("registo_privacidade", nome="Lara"), \
        "a privacidade é dita ANTES de qualquer foto"
    assert ditas[-1] == frases.dizer("registo_feito", nome="Lara")


def test_sem_um_sim_nao_se_guarda_nada(camara):
    from robot.perception import registo

    ditas: list[str] = []
    respostas = iter(["no"])
    registo.registar_pela_voz("Lara", ditas.append, ouvir=lambda: next(respostas), fotos=3)
    assert camara == {}
    assert ditas[-1] == frases.dizer("registo_sem_licenca")


def test_uma_foto_ma_diz_o_que_mudar(camara, monkeypatch):
    from robot.perception import faces, registo

    caras = iter([[], ["a", "b"], ["c"], ["c"], ["c"]])
    monkeypatch.setattr(faces, "detetar", lambda img: next(caras))
    ditas: list[str] = []
    registo.registar_pela_voz("Lara", ditas.append, ouvir=lambda: "yes", fotos=3)
    assert frases.dizer("registo_nao_vejo") in ditas
    assert frases.dizer("registo_muitos") in ditas
    assert camara == {"Lara": 3}


def test_learn_my_face_nao_depende_do_llm(monkeypatch):
    from robot.brain import comandos_diretos, tools

    pedidos = []
    monkeypatch.setattr(tools, "executar", lambda n, a: pedidos.append((n, a)) or "")
    assert comandos_diretos.tentar("Learn my face!") == ""
    assert pedidos == [("registar_cara", {"nome": ""})]


# ---------------------------------------------------------------------------
# 6 · Uma cara desconhecida NÃO é «não vejo ninguém»
# ---------------------------------------------------------------------------


def test_uma_cara_desconhecida_chega_ao_cerebro_como_alguem(cerebro_):
    """⚠️ O BUG (19/09/2026): «adiciona uma cara» → «não vejo ninguém», com a
    pessoa à frente da câmara. O contexto dizia «you see nobody you know»."""
    cerebro_.responder("add my face please", contexto={"pessoa": None, "ve_alguem": True})
    pedido = cerebro_.motor.ultimas_mensagens[-1]["content"]
    assert "someone you don't know" in pedido or "alguém que ainda não conheces" in pedido
    assert "nobody" not in pedido


def test_sem_ninguem_a_frente_continua_a_dizer_que_nao_ve(cerebro_):
    cerebro_.responder("olá", contexto={"pessoa": None, "ve_alguem": False})
    pedido = cerebro_.motor.ultimas_mensagens[-1]["content"]
    assert "nobody" in pedido or "não vês ninguém" in pedido


def test_o_contexto_distingue_ver_de_conhecer(monkeypatch):
    from robot.brain import contexto
    from robot.perception.attention import Observacao

    ctx = contexto.montar(obs=Observacao(presente=True, nome=None))
    assert ctx["pessoa"] is None and ctx["ve_alguem"] is True


@pytest.mark.parametrize("frase", ["Adiciona uma cara", "adicionar uma cara", "Add my face!"])
def test_adicionar_uma_cara_vai_direto_ao_registo(frase, monkeypatch):
    from robot.brain import comandos_diretos, tools

    pedidos = []
    monkeypatch.setattr(tools, "executar", lambda n, a: pedidos.append(n) or "")
    assert comandos_diretos.tentar(frase) == ""
    assert pedidos == ["registar_cara"]


# ---------------------------------------------------------------------------
# 7 · Reconhecer logo a seguir a registar
# ---------------------------------------------------------------------------


def test_escalar_uma_cara_leva_os_cinco_pontos_com_ela():
    """⚠️ O BUG: só a caixa era escalada; o alignCrop usava olhos e boca da
    imagem pequena, e ninguém era reconhecido."""
    import numpy as np

    from robot.perception import faces

    cara = np.arange(15, dtype=np.float32)       # x y w h + 5 pontos + confiança
    grande = faces.escalar_cara(cara, 2.0, 3.0)
    assert list(grande[0:14:2]) == [x * 2 for x in range(0, 14, 2)]
    assert list(grande[1:14:2]) == [y * 3 for y in range(1, 14, 2)]
    assert grande[14] == 14, "a confiança não é uma coordenada"
    assert cara[4] == 4, "a original não muda"


def test_as_caras_das_rotinas_existem_mesmo():
    from robot.expressions import EXPRESSOES

    for nome, passos in rotinas.ROTINAS_OMISSAO.items():
        for passo in passos:
            if passo.startswith("olhos."):
                assert passo.split(".", 1)[1] in EXPRESSOES, (nome, passo)
