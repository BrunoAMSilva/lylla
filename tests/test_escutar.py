"""ESCUTAR EM CONTÍNUO — o áudio a ir para o mini enquanto a Lara fala.

    pytest tests/test_escutar.py

Metade destes testes levantam um mini a sério numa porta livre e apontam-lhe
o cliente do Pi: o WebSocket é verdadeiro, o áudio é verdadeiro, só os
modelos é que não. É a única forma de provar a parte que interessa — que as
duas pontas trabalham AO MESMO TEMPO em vez de esperarem uma pela outra.
"""

from __future__ import annotations

import json
import threading
import time

import numpy as np
import pytest

from cerebro import falar, ouvir, pensar, servidor
from robot.brain import cerebro

fastapi_testclient = pytest.importorskip("fastapi.testclient")
pytest.importorskip("websockets")


def pcm(ms: int = 80) -> bytes:
    """Um bocado de PCM int16 do tamanho que o microfone dá."""
    return np.zeros(int(16_000 * ms / 1000), dtype="<i2").tobytes()


@pytest.fixture
def mini(tmp_path):
    app = servidor.criar_app(ouvir.Ouvido("teste"), pensar.Cerebro("teste"),
                             falar.Voz("teste", cache=tmp_path / "voz"))
    with fastapi_testclient.TestClient(app) as cliente:
        yield cliente


def eventos_ate_fim(ws) -> list[dict]:
    saida = []
    while True:
        evento = ws.receive_json()
        saida.append(evento)
        if evento["tipo"] == "fim":
            return saida


# ---------------------------------------------------------------------------
# 1 · O protocolo
# ---------------------------------------------------------------------------


def test_um_turno_completo_pelo_websocket(mini):
    with mini.websocket_connect("/v1/escutar") as ws:
        ws.send_json({"contexto": {"pessoa": "Lara"}, "sessao": "t"})
        assert ws.receive_json() == {"tipo": "pronto", "incremental": True}
        ws.send_bytes(pcm())
        assert ws.receive_json()["tipo"] == "parcial"
        ws.send_json({"fim": True})

        tipos = [e["tipo"] for e in eventos_ate_fim(ws)]

    assert tipos[0] == "ouvido"
    assert "frase" in tipos and tipos[-1] == "fim"


def test_o_parcial_chega_ANTES_de_a_frase_acabar(mini):
    """É isto a diferença toda. No /v1/turno não há nada até ao fim; aqui o
    mini já percebeu metade da frase enquanto ela ainda está a falar."""
    with mini.websocket_connect("/v1/escutar") as ws:
        ws.send_json({})
        ws.receive_json()
        ws.send_bytes(pcm())
        primeiro = ws.receive_json()
        assert primeiro["tipo"] == "parcial" and primeiro["texto"]
        # e ainda NÃO houve nenhum "fim" — a frase continua
        ws.send_json({"fim": True})
        assert eventos_ate_fim(ws)[-1]["tipo"] == "fim"


def test_o_silencio_nao_manda_uma_pergunta_vazia_ao_modelo(mini):
    with mini.websocket_connect("/v1/escutar") as ws:
        ws.send_json({})
        ws.receive_json()
        ws.send_json({"fim": True})
        assert ws.receive_json() == {"tipo": "ouvido", "texto": "", "duracao_s": 0.0,
                                     "tempo_ms": pytest.approx(0, abs=2000)}
        fim = ws.receive_json()
    assert fim["motivo"] == "nao_percebi"


def test_cancelar_a_meio_acaba_o_turno_sem_pensar(mini):
    """É o que um «pára» faz: interrompe já, sem esperar pelo modelo."""
    with mini.websocket_connect("/v1/escutar") as ws:
        ws.send_json({})
        ws.receive_json()
        ws.send_bytes(pcm())
        ws.receive_json()
        ws.send_json({"cancelar": True})
        fim = ws.receive_json()
    assert fim == {"tipo": "fim", "motivo": "cancelado"}


def test_se_o_pi_se_desligar_a_meio_o_mini_nao_estoira(mini):
    with mini.websocket_connect("/v1/escutar") as ws:
        ws.send_json({})
        ws.receive_json()
        ws.send_bytes(pcm())
    assert mini.get("/v1/saude").json()["ok"], "o serviço tem de continuar de pé"


def test_uma_abertura_sem_json_e_recusada_com_calma(mini):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with mini.websocket_connect("/v1/escutar") as ws:
            ws.send_bytes("isto não é a mensagem de abertura".encode("utf-8"))
            ws.receive_json()
    assert mini.get("/v1/saude").json()["ok"]


# ---------------------------------------------------------------------------
# 2 · Com um motor que NÃO sabe transcrever à medida
# ---------------------------------------------------------------------------


def test_um_motor_de_janela_continua_a_servir(tmp_path):
    """O Whisper não transcreve à medida. O /v1/escutar tem de funcionar na
    mesma — o robô só perde a vantagem, não a capacidade."""
    ouvido = ouvir.Ouvido("teste")
    ouvido.motor.sessao = lambda lingua: ouvir.SessaoAcumulada(ouvido.motor, lingua)
    app = servidor.criar_app(ouvido, pensar.Cerebro("teste"),
                             falar.Voz("teste", cache=tmp_path))

    with fastapi_testclient.TestClient(app) as cliente:
        with cliente.websocket_connect("/v1/escutar") as ws:
            ws.send_json({})
            assert ws.receive_json() == {"tipo": "pronto", "incremental": False}
            for _ in range(3):
                ws.send_bytes(pcm())
            ws.send_json({"fim": True})
            eventos = eventos_ate_fim(ws)

    assert not [e for e in eventos if e["tipo"] == "parcial"], "não há parciais"
    assert eventos[0]["texto"], "mas a transcrição sai na mesma, no fim"


def test_a_saude_diz_se_o_motor_transcreve_a_medida(mini):
    assert mini.get("/v1/saude").json()["ouvir"]["incremental"] is True


# ---------------------------------------------------------------------------
# 3 · O cliente do Pi, contra um mini a sério
# ---------------------------------------------------------------------------


@pytest.fixture
def mini_a_serio(tmp_path, monkeypatch):
    """Um mini em uvicorn, numa porta livre, com o cliente do robô apontado
    para ele. Devolve as definições do robô, para o teste as mexer."""
    import uvicorn

    app = servidor.criar_app(ouvir.Ouvido("teste"), pensar.Cerebro("teste"),
                             falar.Voz("teste", cache=tmp_path / "mini"))
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    http = uvicorn.Server(config)
    fio = threading.Thread(target=http.run, daemon=True)
    fio.start()
    for _ in range(200):
        if http.started:
            break
        time.sleep(0.05)
    porta = http.servers[0].sockets[0].getsockname()[1]

    definicoes: dict[str, object] = {"cerebro.url": f"http://127.0.0.1:{porta}"}
    monkeypatch.setattr(cerebro.config, "obter",
                        lambda caminho, omissao=None: definicoes.get(caminho, omissao))
    monkeypatch.setattr(cerebro.config, "a_simular", lambda: False)
    monkeypatch.setattr(cerebro, "_avisado", False)
    yield definicoes
    http.should_exit = True
    fio.join(timeout=5)


def test_o_pi_fala_com_o_mini_pelo_websocket(mini_a_serio):
    pytest.importorskip("websocket")

    def pedacos():
        for _ in range(3):
            yield pcm()

    eventos = list(cerebro.escutar(pedacos(), contexto={"pessoa": "Lara"}))
    tipos = [e["tipo"] for e in eventos]

    assert tipos[0] == "pronto"
    assert "parcial" in tipos and "ouvido" in tipos and "frase" in tipos
    assert tipos[-1] == "fim"
    frases = [e for e in eventos if e["tipo"] == "frase"]
    assert all(f["audio"].startswith(b"RIFF") for f in frases), \
        "o áudio chega ao Pi já em bytes, pronto a tocar"


def test_o_pi_manda_o_audio_ENQUANTO_le_as_respostas(mini_a_serio):
    """A prova de que as duas pontas trabalham ao mesmo tempo: o primeiro
    parcial chega ao Pi enquanto o gerador de áudio ainda está a produzir.

    Se o cliente enviasse tudo primeiro e só depois lesse, este teste nunca
    veria um parcial antes do último pedaço."""
    pytest.importorskip("websocket")

    enviados = []
    parcial_a_meio = threading.Event()

    def pedacos():
        for i in range(6):
            enviados.append(i)
            time.sleep(0.05)
            yield pcm()

    for evento in cerebro.escutar(pedacos()):
        if evento["tipo"] == "parcial" and len(enviados) < 6:
            parcial_a_meio.set()

    assert parcial_a_meio.is_set(), "o Pi só leu depois de enviar tudo"


def test_um_cancelamento_do_lado_do_pi_para_o_turno(mini_a_serio):
    pytest.importorskip("websocket")

    parar = threading.Event()

    def pedacos():
        for _ in range(50):
            yield pcm()

    eventos = []
    for evento in cerebro.escutar(pedacos(), cancelar=parar.is_set):
        eventos.append(evento)
        if evento["tipo"] == "parcial":
            parar.set()

    assert eventos[-1]["motivo"] == "cancelado"
    assert not [e for e in eventos if e["tipo"] == "frase"]


def test_com_o_mini_desligado_o_escutar_levanta_semcerebro(monkeypatch):
    pytest.importorskip("websocket")

    definicoes = {"cerebro.url": "http://127.0.0.1:9", "cerebro.timeout_ligar_s": 1}
    monkeypatch.setattr(cerebro.config, "obter",
                        lambda caminho, omissao=None: definicoes.get(caminho, omissao))
    monkeypatch.setattr(cerebro.config, "a_simular", lambda: False)

    with pytest.raises(cerebro.SemCerebro):
        list(cerebro.escutar(iter([pcm()])))


# ---------------------------------------------------------------------------
# 4 · O pré-rolo — o princípio da frase não se perde
# ---------------------------------------------------------------------------


def test_o_pre_rolo_guarda_o_que_veio_antes_da_palavra_chave():
    """Entre ouvir «Olá robô» e abrir a gravação passa-se tempo, e as
    crianças não esperam. O que ficou em buffer é a primeira coisa a ir."""
    from robot.voice import wakeword

    wakeword.esquecer_pre_rolo()
    assert wakeword.pre_rolo() is None

    for i in range(5):
        wakeword._pre_rolo.append(np.full(wakeword.BLOCO, i, dtype=np.int16))

    guardado = wakeword.pre_rolo()
    assert len(guardado) == 5 * wakeword.BLOCO
    assert guardado[0] == 0 and guardado[-1] == 4, "pela ordem em que foi ouvido"

    wakeword.esquecer_pre_rolo()
    assert wakeword.pre_rolo() is None


def test_o_pre_rolo_nao_cresce_para_sempre():
    """É uma fila circular: 1,6 s e mais nada. Um buffer sem limite num robô
    que fica horas à espera da palavra é uma fuga de memória — e, pior, é
    guardar áudio da casa que ninguém pediu para guardar."""
    from robot.voice import wakeword

    wakeword.esquecer_pre_rolo()
    for _ in range(500):
        wakeword._pre_rolo.append(np.zeros(wakeword.BLOCO, dtype=np.int16))

    segundos = len(wakeword.pre_rolo()) / wakeword.TAXA
    assert segundos <= wakeword.SEGUNDOS_DE_PRE_ROLO + 0.1
    wakeword.esquecer_pre_rolo()


def test_o_pcm_do_pi_e_o_que_o_mini_espera():
    """O que sai do microfone e o que o de_pcm16 lê têm de ser a mesma coisa.
    Um engano aqui não dá erro nenhum: dá ruído transcrito."""
    original = (np.sin(np.linspace(0, 40, 8000)) * 0.5).astype(np.float32)
    bytes_pcm = (original * 32767).astype("<i2").tobytes()
    voltou = ouvir.de_pcm16(bytes_pcm)
    assert len(voltou) == len(original)
    assert np.allclose(voltou, original, atol=1e-3)


def test_um_numero_impar_de_bytes_nao_rebenta():
    """Um pedaço cortado a meio de uma amostra pela rede."""
    assert len(ouvir.de_pcm16(b"\x00\x01\x02")) == 1
