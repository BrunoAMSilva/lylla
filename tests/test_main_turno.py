"""O CICLO DE UM TURNO — o que acontece entre a Lara falar e o robô responder.

    pytest tests/test_main_turno.py

Não há microfone nem coluna nestes testes: substitui-se o que grava e o que
toca, e verifica-se a ORDEM e as DECISÕES.

O teste mais importante deste ficheiro é o último: **com o mini desligado, o
robô continua a responder.** É a regra da casa nº 3 — um robô mudo à frente de
uma criança é um projeto acabado.
"""

from __future__ import annotations

import pytest

from robot.brain import cerebro
from robot.brain.state import Estado, Maquina
from robot.perception.attention import Observacao


@pytest.fixture
def robo(monkeypatch):
    """O robô com a boca, os ouvidos e o corpo substituídos por um caderno."""
    import robot.main as main
    from robot import config
    from robot.voice import speak

    monkeypatch.setattr(config, "a_simular", lambda: False)
    monkeypatch.setattr(main.config, "a_simular", lambda: False)

    registo: dict[str, list] = {"falado": [], "tocado": [], "caras": [], "acoes": []}
    monkeypatch.setattr(speak, "falar", lambda t, esperar=True: registo["falado"].append(str(t)))
    monkeypatch.setattr(speak, "tocar", lambda d, esperar=True: registo["tocado"].append(d))
    monkeypatch.setattr(speak, "esperar_acabar", lambda: None)
    monkeypatch.setattr(main.speak, "falar", lambda t, esperar=True: registo["falado"].append(str(t)))
    monkeypatch.setattr(main.speak, "tocar", lambda d, esperar=True: registo["tocado"].append(d))
    monkeypatch.setattr(main.speak, "esperar_acabar", lambda: None)
    monkeypatch.setattr(main.eyes, "expressao", lambda nome, olhar=None: registo["caras"].append(nome))
    # ⚠️ Sem isto, cada teste demorava 2 s: fingimos que não estamos em
    #    simulação, e o eyes.animar() passa a esperar as pausas de verdade
    #    (1,2 s só no "acordar"). Testes lentos deixam de se correr — e a
    #    animação não é o que este ficheiro está a testar.
    monkeypatch.setattr(main.eyes, "animar", lambda nome: registo["caras"].append(f"animar:{nome}"))
    monkeypatch.setattr(main.glow, "pulsar", lambda *a, **k: None)
    monkeypatch.setattr(main.glow, "respirar", lambda *a, **k: None)
    monkeypatch.setattr(main.contexto, "montar", lambda *a, **k: {"pessoa": "Lara"})

    def executar(nome, argumentos):
        registo["acoes"].append((nome, argumentos))
        return f"Fiz {nome}."

    monkeypatch.setattr(main.tools, "executar", executar)
    return main, registo


def _wav_curto(segundos: float = 0.5) -> bytes:
    import numpy as np

    return cerebro.para_wav(np.zeros(int(16_000 * segundos), dtype=np.float32))


def test_o_wav_sobrevive_a_ida_e_volta():
    """O que o Pi grava tem de voltar a ser áudio — e não por cortar 44 bytes
    de cabeçalho, que é o que parte com um WAV que traga blocos extra."""
    import numpy as np

    original = (np.sin(np.linspace(0, 40, 8000)) * 0.5).astype(np.float32)
    voltou = cerebro.de_wav(cerebro.para_wav(original))
    assert len(voltou) == len(original)
    assert np.allclose(voltou, original, atol=1e-4)


def test_de_wav_recusa_um_wav_com_o_cabecalho_deslocado():
    """Um WAV com um bloco LIST antes dos dados: pelo módulo `wave` lê-se
    bem; a cortar 44 bytes, sairia ruído sem erro nenhum."""
    import io
    import wave

    import numpy as np

    amostras = (np.ones(1000, dtype=np.float32) * 0.5)
    normal = cerebro.para_wav(amostras)
    # enfiar um bloco LIST de 30 bytes entre o cabeçalho e o 'data'
    i = normal.index(b"data")
    extra = b"LIST" + (22).to_bytes(4, "little") + b"INFOISFT" + b"x" * 14
    inchado = bytearray(normal[:i] + extra + normal[i:])
    inchado[4:8] = (len(inchado) - 8).to_bytes(4, "little")
    voltou = cerebro.de_wav(bytes(inchado))
    assert len(voltou) == 1000 and np.allclose(voltou, 0.5, atol=1e-4)


def _turno_falso(eventos):
    def turno(**_kwargs):
        yield from eventos

    return turno


# ---------------------------------------------------------------------------
# 1 · O caminho normal
# ---------------------------------------------------------------------------


def test_a_cara_muda_antes_de_a_primeira_frase_tocar(robo, monkeypatch):
    main, registo = robo
    ordem: list[str] = []
    monkeypatch.setattr(main.eyes, "expressao", lambda n, olhar=None: ordem.append(f"cara:{n}"))
    monkeypatch.setattr(main.speak, "tocar", lambda d, esperar=True: ordem.append(f"toca:{d.decode()}"))
    eventos = _turno_falso([
        {"tipo": "ouvido", "texto": "olá"},
        {"tipo": "expressao", "nome": "feliz"},
        {"tipo": "frase", "texto": "Olá!", "audio": b"um"},
        {"tipo": "frase", "texto": "Que bom ver-te.", "audio": b"dois"},
        {"tipo": "resposta", "fala": "Olá! Que bom ver-te.", "acoes": [], "recusadas": []},
        {"tipo": "fim", "tempo_ms": {"total": 900, "primeira_frase": 400}},
    ])

    main._consumir_turno(Maquina(), eventos())
    # (a máquina de estados também mexe nos olhos — o que interessa é que a
    #  cara que o cérebro escolheu chega ANTES de a primeira frase sair)
    assert ordem.index("cara:feliz") < ordem.index("toca:um")
    assert [o for o in ordem if o.startswith("toca:")] == ["toca:um", "toca:dois"], \
        "as frases tocam por ordem"


def test_as_acoes_so_acontecem_depois_de_ele_falar(robo, monkeypatch):
    """Um robô que arranca a andar a meio da frase assusta. Fala primeiro."""
    main, registo = robo
    ordem: list[str] = []
    monkeypatch.setattr(main.speak, "tocar", lambda d, esperar=True: ordem.append("fala"))
    monkeypatch.setattr(main.speak, "esperar_acabar", lambda: ordem.append("esperou"))
    monkeypatch.setattr(main.tools, "executar", lambda n, a: ordem.append(f"ação:{n}") or "feito")
    eventos = _turno_falso([
        {"tipo": "ouvido", "texto": "dança"},
        {"tipo": "frase", "texto": "Olha!", "audio": b"x"},
        {"tipo": "resposta", "fala": "Olha!", "acoes": [{"nome": "dancar", "argumentos": {}}],
         "recusadas": []},
        {"tipo": "fim", "tempo_ms": {}},
    ])

    main._consumir_turno(Maquina(), eventos())
    assert ordem == ["fala", "esperou", "ação:dancar"]


def test_uma_frase_sem_audio_e_dita_a_mesma(robo, monkeypatch):
    """Se o TTS falhar no mini, a frase chega em texto — e o Pi diz-a com a
    voz que tiver. Melhor uma voz feia do que silêncio."""
    main, registo = robo
    eventos = _turno_falso([
        {"tipo": "ouvido", "texto": "olá"},
        {"tipo": "frase", "texto": "Olá!", "audio": None, "erro_voz": "o Piper morreu"},
        {"tipo": "resposta", "fala": "Olá!", "acoes": [], "recusadas": []},
        {"tipo": "fim", "tempo_ms": {}},
    ])
    main._consumir_turno(Maquina(), eventos())
    assert registo["falado"] == ["Olá!"]


# ---------------------------------------------------------------------------
# 2 · Segurança e privacidade não dependem do modelo
# ---------------------------------------------------------------------------


def test_um_comando_direto_nao_espera_pela_resposta_do_modelo(robo, monkeypatch):
    """«Pára» tem de funcionar à primeira, 100% das vezes. Assim que a
    transcrição chega, o turno acaba ali — o resto da resposta é ignorado."""
    main, registo = robo
    parou = []
    monkeypatch.setattr(main.comandos_diretos, "tentar",
                        lambda t: "Parei." if t == "pára" else None)
    eventos = _turno_falso([
        {"tipo": "ouvido", "texto": "pára"},
        {"tipo": "frase", "texto": "Claro, vou já!", "audio": b"x"},
        {"tipo": "resposta", "fala": "Claro, vou já!",
         "acoes": [{"nome": "mover", "argumentos": {"direcao": "frente"}}], "recusadas": []},
        {"tipo": "fim", "tempo_ms": {}},
    ])

    main._consumir_turno(Maquina(), eventos())
    assert registo["falado"] == ["Parei."]
    assert registo["tocado"] == [], "o que o modelo já tinha escrito não chega a sair"
    assert registo["acoes"] == [], "e muito menos a mexer os motores"


def test_uma_recusa_e_dita_em_voz_alta(robo, monkeypatch):
    """«Não posso, está aí uma parede» TEM de sair — senão o robô fica parado
    sem explicação, que é como as coisas parecem avariadas."""
    from robot.brain import tools

    main, registo = robo
    monkeypatch.setattr(main.tools, "executar",
                        lambda n, a: tools.Recusa("Não posso — está aí uma parede!"))
    maquina = Maquina()
    main._executar([{"nome": "mover", "argumentos": {"direcao": "frente"}}], maquina)
    assert registo["falado"] == ["Não posso — está aí uma parede!"]


def test_o_que_correu_bem_nao_e_repetido(robo, monkeypatch):
    """O robô já disse «Vou dançar!». Dizer «Dancei!» a seguir é repetir-se."""
    main, registo = robo
    monkeypatch.setattr(main.tools, "executar", lambda n, a: "Dancei!")
    main._executar([{"nome": "dancar", "argumentos": {}}], Maquina())
    assert registo["falado"] == []


# ---------------------------------------------------------------------------
# 3 · O QUE INTERESSA MESMO: o mini desligado
# ---------------------------------------------------------------------------


def test_sem_mini_o_robo_explica_se_em_vez_de_emudecer(robo, monkeypatch):
    """Já não há Whisper nem Ollama no Pi: sem o mini, o robô não percebe o
    que lhe dizem. O que NÃO pode acontecer é ficar calado — a Lara tem de
    saber que ele a ouviu e não a percebeu."""
    main, registo = robo
    from robot.brain import cerebro

    def sem_cerebro(*_a, **_k):
        raise cerebro.SemCerebro("o mini está desligado")
        yield  # noqa: pragma

    monkeypatch.setattr(main.cerebro, "escutar", sem_cerebro)
    monkeypatch.setattr(main.listen, "escutar_em_directo", lambda *a, **k: iter([b""]))
    monkeypatch.setattr(main.contexto, "montar", lambda *a, **k: {})

    main.uma_interacao(Maquina())
    assert registo["falado"] == [main.FRASE_SEM_CEREBRO]


def test_um_turno_sem_fala_nenhuma_admite_que_nao_percebeu(robo, monkeypatch):
    """O mini respondeu, mas sem uma única frase. O robô admite-o em vez de
    executar a ação em silêncio."""
    main, registo = robo

    def sem_fala(*_a, **_k):
        yield {"tipo": "ouvido", "texto": "acena"}
        yield {"tipo": "resposta", "fala": "", "acoes": [], "recusadas": []}
        yield {"tipo": "fim", "tempo_ms": {}}

    main._consumir_turno(Maquina(), sem_fala())
    assert registo["falado"] == ["Não percebi. Podes repetir?"]


def test_se_a_ligacao_cair_a_meio_o_que_ja_foi_dito_conta(robo, monkeypatch):
    """O mini disse a primeira frase e a rede caiu. Isso NÃO é um turno
    perdido — o robô já respondeu, e repetir tudo pelo caminho antigo seria
    ele dizer a mesma coisa duas vezes."""
    main, registo = robo

    def meio_turno(**_kwargs):
        yield {"tipo": "ouvido", "texto": "olá"}
        yield {"tipo": "frase", "texto": "Olá, Lara!", "audio": b"x"}
        raise cerebro.SemCerebro("a rede caiu")

    assert main._consumir_turno(Maquina(), meio_turno()) is True
    assert registo["tocado"] == [b"x"]


def test_um_silencio_nao_manda_uma_pergunta_vazia_ao_modelo(robo, monkeypatch):
    main, registo = robo
    eventos = _turno_falso([
        {"tipo": "ouvido", "texto": ""},
        {"tipo": "fim", "motivo": "nao_percebi", "tempo_ms": {}},
    ])
    main._consumir_turno(Maquina(), eventos())
    assert registo["falado"] == ["Não percebi. Podes repetir?"]
