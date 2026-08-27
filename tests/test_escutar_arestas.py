"""AS ARESTAS DO STREAMING — um teste por cada bug que já cá esteve.

    pytest tests/test_escutar_arestas.py

Saíram todos de uma revisão adversarial ao caminho novo, e todos eram reais.
Dois deles anulavam o desenho: a primeira frase chegava MAIS TARDE do que
pelo caminho antigo, e o «pára» tinha deixado de funcionar.
"""

from __future__ import annotations

import gc
import json
import threading
import time

import numpy as np
import pytest

from cerebro import falar, ouvir, pensar, servidor
from robot.brain import cerebro, comandos_diretos

fastapi_testclient = pytest.importorskip("fastapi.testclient")
pytest.importorskip("websockets")


def pcm(ms: int = 80) -> bytes:
    return np.zeros(int(16_000 * ms / 1000), dtype="<i2").tobytes()


# ---------------------------------------------------------------------------
# 1 · A primeira frase tem de sair ANTES de a última estar pronta
# ---------------------------------------------------------------------------


class ModeloLento(pensar.MotorTeste):
    """Um LLM que demora a escrever, como os de verdade."""

    def gerar(self, mensagens, esquema):
        self.usou_esquema = True
        self.estatisticas = {}
        conteudo = ('{"expressao":"feliz","fala":"Primeira frase aqui. '
                    'Segunda frase aqui. Terceira frase aqui.","acoes":[]}')
        for i in range(0, len(conteudo), 8):
            time.sleep(0.02)
            yield conteudo[i:i + 8]


def test_as_frases_saem_uma_a_uma_e_nao_todas_no_fim(tmp_path):
    """⚠️ O BUG: `list(gerador)` no endpoint corria o LLM e o TTS de TODAS as
    frases antes de o primeiro evento sair. Medido na altura: a primeira
    frase chegava ao robô 2,4× mais tarde do que pelo /v1/turno, e a cara
    mudava ao mesmo tempo que o áudio em vez de vir à frente.

    O endpoint feito para ser mais rápido era mais lento que o que substituía.
    """
    cerebro_lento = pensar.Cerebro("teste")
    cerebro_lento.motor = ModeloLento()
    app = servidor.criar_app(ouvir.Ouvido("teste"), cerebro_lento,
                             falar.Voz("teste", cache=tmp_path))

    with fastapi_testclient.TestClient(app) as cliente:
        with cliente.websocket_connect("/v1/escutar") as ws:
            ws.send_json({})
            ws.receive_json()
            ws.send_bytes(pcm())
            ws.receive_json()
            ws.send_json({"fim": True})

            inicio = time.perf_counter()
            quando: list[tuple[str, float]] = []
            while True:
                evento = ws.receive_json()
                quando.append((evento["tipo"], time.perf_counter() - inicio))
                if evento["tipo"] == "fim":
                    break

    tempos = dict()
    for tipo, t in quando:
        tempos.setdefault(tipo, t)          # a primeira vez de cada tipo
    frases = [t for tipo, t in quando if tipo == "frase"]

    assert len(frases) >= 2
    assert tempos["expressao"] < frases[0], "a cara muda antes de a fala sair"
    assert frases[0] < frases[-1] - 0.01, (
        f"as frases chegaram todas juntas: {frases} — o streaming morreu")
    assert frases[0] < tempos["fim"] * 0.8, (
        "a primeira frase só chegou ao pé do fim do turno")


# ---------------------------------------------------------------------------
# 2 · O «pára» com a palavra-chave à frente
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dito, esperado", [
    ("pára", "Parei."),
    ("olá robô pára", "Parei."),                       # ← o pré-rolo põe isto
    ("Olá robô, STOP!", "Parei."),
    ("olá lylla pára", "Parei."),
    ("olá robô não olhes para mim", "Pronto, deixei de olhar."),
    ("não olhes para mim", "Pronto, deixei de olhar."),
])
def test_o_travao_funciona_com_a_palavra_chave_a_frente(dito, esperado):
    """⚠️ O BUG: o pré-rolo contém SEMPRE a palavra mágica que acabou de ser
    dita, portanto o que chega já não é «pára» mas «olá robô pára». Com a
    comparação exata, o travão de emergência e o interruptor da câmara — as
    duas coisas que nunca podem depender do modelo — passaram a depender
    dele."""
    assert comandos_diretos.tentar(dito) == esperado


@pytest.mark.parametrize("dito", [
    "conta-me uma história para adormecer",
    "vai buscar o carro para mim",
    "olá robô, faz uma dança",
    "olha para a câmara e sorri",
])
def test_uma_frase_normal_nao_para_o_robo_por_acaso(dito):
    """A correção não pode ser «acaba em pára»: uma frase que por acaso
    termine nessas palavras não pode travar o robô a meio da brincadeira."""
    assert comandos_diretos.tentar(dito) is None


def test_o_que_vem_depois_da_palavra_chave():
    assert comandos_diretos.sem_palavra_chave("Olá robô, pára!") == "para"
    assert comandos_diretos.sem_palavra_chave("conta-me uma história") == \
        "conta me uma historia"


# ---------------------------------------------------------------------------
# 3 · O erro do envio não se pode perder
# ---------------------------------------------------------------------------


def test_uma_falha_a_enviar_nao_vira_nao_percebi(monkeypatch):
    """⚠️ O BUG: o websocket-client devolve "" (não levanta) quando recebe um
    CLOSE. A excepção da thread de envio ficava numa lista que ninguém lia, o
    turno parecia ter corrido bem, e o robô dizia «Não percebi, podes
    repetir?» — a culpar a criança de um problema de rede."""
    pytest.importorskip("websocket")

    definicoes = {"cerebro.url": "http://127.0.0.1:8420"}
    monkeypatch.setattr(cerebro.config, "obter",
                        lambda caminho, omissao=None: definicoes.get(caminho, omissao))
    monkeypatch.setattr(cerebro.config, "a_simular", lambda: False)

    class LigacaoPartida:
        def send(self, *_a, **_k):
            raise BrokenPipeError("o mini reiniciou")

        def send_binary(self, *_a, **_k):
            raise BrokenPipeError("o mini reiniciou")

        def recv(self):
            time.sleep(0.05)
            return ""            # é isto que o websocket-client faz num CLOSE

        def settimeout(self, _t):
            pass

        def close(self):
            pass

    import websocket

    monkeypatch.setattr(websocket, "create_connection", lambda *a, **k: LigacaoPartida())

    with pytest.raises(cerebro.SemCerebro) as erro:
        list(cerebro.escutar(iter([pcm()])))
    assert "BrokenPipe" in str(erro.value)


# ---------------------------------------------------------------------------
# 4 · O tempo de ligar não pode ser o tempo do turno
# ---------------------------------------------------------------------------


def test_liga_se_com_o_tempo_curto_e_nao_com_o_do_turno(monkeypatch):
    """⚠️ O BUG: o `create_connection` usa o mesmo timeout para abrir e para
    esperar por dados, e o websocket-client engole em silêncio um
    `open_timeout=` que não conhece. Contra um mini que aceita o TCP mas não
    responde ao handshake, o robô ficava os 60 s do turno parado e calado —
    e nesse tempo a rede de segurança dos motores também não corria."""
    pytest.importorskip("websocket")
    import websocket

    definicoes = {"cerebro.url": "http://mini:8420",
                  "cerebro.timeout_ligar_s": 2, "cerebro.timeout_turno_s": 60}
    monkeypatch.setattr(cerebro.config, "obter",
                        lambda caminho, omissao=None: definicoes.get(caminho, omissao))
    monkeypatch.setattr(cerebro.config, "a_simular", lambda: False)

    usados = {}

    class Falsa:
        def settimeout(self, t):
            usados["depois"] = t

        def send(self, *_a):
            pass

        def send_binary(self, *_a):
            pass

        def recv(self):
            return ""

        def close(self):
            pass

    def create_connection(url, **opcoes):
        usados["ao_ligar"] = opcoes.get("timeout")
        assert "open_timeout" not in opcoes, "o websocket-client ignorava-o em silêncio"
        return Falsa()

    monkeypatch.setattr(websocket, "create_connection", create_connection)
    list(cerebro.escutar(iter([])))

    assert usados["ao_ligar"] == 2, "ligar tem de usar o tempo CURTO"
    assert usados["depois"] == 60, "e só depois se alarga para o do turno"


# ---------------------------------------------------------------------------
# 5 · O microfone tem de fechar sem esperar pelo coletor de lixo
# ---------------------------------------------------------------------------


def test_nao_fica_um_ciclo_de_referencias_a_segurar_o_microfone(monkeypatch):
    """⚠️ O BUG: guardar o OBJETO da excepção segurava o traceback → o frame
    do enviar() → o gerador de áudio → o microfone ABERTO. A volta seguinte
    do ciclo tentava abrir o microfone para a palavra-chave e apanhava
    "Device unavailable" até o coletor de ciclos passar."""
    pytest.importorskip("websocket")
    import websocket

    definicoes = {"cerebro.url": "http://mini:8420"}
    monkeypatch.setattr(cerebro.config, "obter",
                        lambda caminho, omissao=None: definicoes.get(caminho, omissao))
    monkeypatch.setattr(cerebro.config, "a_simular", lambda: False)

    class Falsa:
        """Aceita a abertura e uns bocados de áudio, e depois cai — que é o
        cenário real: o mini a reiniciar a meio de uma frase."""

        def __init__(self):
            self.enviados = 0

        def settimeout(self, _t):
            pass

        def send(self, *_a):
            pass

        def send_binary(self, *_a):
            self.enviados += 1
            if self.enviados > 2:
                raise BrokenPipeError("o mini caiu a meio da frase")

        def recv(self):
            time.sleep(0.02)
            return ""

        def close(self):
            pass

    monkeypatch.setattr(websocket, "create_connection", lambda *a, **k: Falsa())

    aberto = []          # faz de conta que é o sd.InputStream

    def microfone():
        aberto.append(True)
        try:
            for _ in range(50):
                yield pcm()
        finally:
            aberto.pop()

    gc.disable()
    try:
        with pytest.raises(cerebro.SemCerebro):
            list(cerebro.escutar(microfone()))
        assert not aberto, (
            "o microfone ficou aberto — a volta seguinte do ciclo apanha "
            "'Device unavailable' e o robô deixa de responder à palavra mágica")
    finally:
        gc.enable()


# ---------------------------------------------------------------------------
# 6 · Uma escuta de cada vez
# ---------------------------------------------------------------------------


def test_duas_escutas_ao_mesmo_tempo_nao_se_estragam():
    """⚠️ O BUG: o `transcribe_stream()` do Parakeet MUDA o modelo (põe a
    atenção em local ao entrar, repõe ao sair). O modelo é partilhado, por
    isso a segunda sessão a fechar reponha a atenção enquanto a primeira
    ainda ouvia — e a transcrição saía lixo, sem erro nenhum."""
    lock = threading.Lock()

    class ModeloFalso:
        def __init__(self):
            self.atencao = "rel_pos"

        def transcribe_stream(self, context_size, depth):
            modelo = self

            class Gestor:
                def __enter__(self_):
                    modelo.atencao = "local"
                    return self_

                def __exit__(self_, *_a):
                    modelo.atencao = "rel_pos"

                def add_audio(self_, _a):
                    assert modelo.atencao == "local", "modelo em estado errado"

                @property
                def result(self_):
                    return type("R", (), {"text": "olá"})()

            return Gestor()

    modelo = ModeloFalso()
    primeira = ouvir.SessaoParakeet(modelo, (256, 256), 1, lock)
    with pytest.raises(RuntimeError, match="ouvir outra pessoa"):
        ouvir.SessaoParakeet(modelo, (256, 256), 1, _LockOcupado(lock))

    primeira.adicionar(np.zeros(100, dtype=np.float32))
    primeira.fechar()
    # agora já dá
    segunda = ouvir.SessaoParakeet(modelo, (256, 256), 1, lock)
    segunda.fechar()


class _LockOcupado:
    """Um lock que nunca cede — é o que a segunda sessão encontra."""

    def __init__(self, real):
        self._real = real

    def acquire(self, timeout=None):
        return False

    def release(self):
        pass


# ---------------------------------------------------------------------------
# 7 · O robô nunca fica calado
# ---------------------------------------------------------------------------


@pytest.fixture
def robo(monkeypatch):
    import robot.main as main
    from robot import config

    monkeypatch.setattr(config, "a_simular", lambda: False)
    monkeypatch.setattr(main.config, "a_simular", lambda: False)
    dito: list[str] = []
    monkeypatch.setattr(main.speak, "falar", lambda t, esperar=True: dito.append(str(t)))
    monkeypatch.setattr(main.speak, "tocar", lambda d, esperar=True: None)
    monkeypatch.setattr(main.speak, "esperar_acabar", lambda: None)
    monkeypatch.setattr(main.eyes, "expressao", lambda *a, **k: None)
    monkeypatch.setattr(main.eyes, "animar", lambda *a, **k: None)
    monkeypatch.setattr(main.tools, "executar", lambda n, a: "feito")
    return main, dito


@pytest.mark.parametrize("rebenta", [
    ValueError("Invalid base64-encoded string"),
    KeyError("tipo"),
    RuntimeError("uma coisa que nunca previmos"),
    TypeError("nem isto"),
])
def test_seja_qual_for_o_erro_o_robo_diz_alguma_coisa(robo, rebenta):
    """⚠️ O BUG: só o SemCerebro e o ValueError estavam apanhados, e o ramo do
    ValueError nem sequer falava. Qualquer outra coisa subia até ao ciclo
    principal e o robô ficava com cara de surpreso, calado, dois segundos."""
    from robot.brain.state import Maquina

    main, dito = robo

    def eventos():
        yield {"tipo": "ouvido", "texto": "olá"}
        raise rebenta

    main._consumir_turno(Maquina(), eventos())
    assert dito, f"o robô ficou calado com {type(rebenta).__name__}"


def test_um_comando_direto_fecha_a_ligacao(robo):
    """⚠️ O BUG: o robô dizia «Parei.» e saía, mas o mini continuava a pensar,
    a sintetizar, e a ESCREVER NO HISTÓRICO uma resposta que nunca foi dita.
    Ao fim de uns turnos o modelo raciocinava sobre uma conversa inventada."""
    from robot.brain.state import Maquina

    main, dito = robo
    fechado = []

    def eventos():
        try:
            yield {"tipo": "ouvido", "texto": "olá robô pára"}
            yield {"tipo": "frase", "texto": "isto nunca devia sair", "audio": b"x"}
        finally:
            fechado.append(True)

    main._consumir_turno(Maquina(), eventos())

    assert dito == ["Parei."]
    assert fechado, "a ligação tem de ser fechada, não abandonada"


# ---------------------------------------------------------------------------
# 8 · Contas certas: o pré-rolo não é tempo de fala
# ---------------------------------------------------------------------------


def test_o_pre_rolo_nao_conta_como_tempo_de_fala(tmp_path):
    """⚠️ O BUG: o pré-rolo (1,6 s de áudio anterior à palavra-chave) era
    contado como tempo em que a Lara esteve a falar. O número que serve para
    afinar o silêncio e comparar os caminhos saía sempre inflacionado."""
    app = servidor.criar_app(ouvir.Ouvido("teste"), pensar.Cerebro("teste"),
                             falar.Voz("teste", cache=tmp_path))
    with fastapi_testclient.TestClient(app) as cliente:
        with cliente.websocket_connect("/v1/escutar") as ws:
            ws.send_json({})
            ws.receive_json()
            for _ in range(25):                    # 2,0 s de áudio ao todo
                ws.send_bytes(pcm())
            ws.receive_json()                      # o primeiro parcial
            ws.send_json({"fim": True, "pre_rolo_s": 1.6})
            while True:
                evento = ws.receive_json()
                if evento["tipo"] == "ouvido":
                    break
    assert evento["duracao_s"] == pytest.approx(0.4, abs=0.05), \
        "2,0 s enviados − 1,6 s de pré-rolo = 0,4 s de fala"


def test_a_escuta_sabe_quanto_pre_rolo_enviou(monkeypatch):
    """O cliente não pode adivinhar: o pré-rolo pode ser mais curto que 1,6 s
    (o robô acabou de arrancar) ou não existir de todo."""
    from robot import config
    from robot.voice import listen, wakeword

    monkeypatch.setattr(config, "a_simular", lambda: False)
    monkeypatch.setattr(listen.config, "a_simular", lambda: False)
    wakeword.esquecer_pre_rolo()
    for _ in range(10):                            # 10 × 80 ms = 0,8 s
        wakeword._pre_rolo.append(np.zeros(wakeword.BLOCO, dtype=np.int16))

    escuta = listen.escutar_em_directo()
    primeiro = next(iter(escuta))
    assert escuta.pre_rolo_s == pytest.approx(0.8, abs=0.01)
    assert len(primeiro) == 10 * wakeword.BLOCO * 2      # int16
    escuta.close()

    wakeword.esquecer_pre_rolo()
    escuta = listen.escutar_em_directo()
    for _ in escuta:                               # sem microfone, acaba já
        break
    assert escuta.pre_rolo_s == 0.0
    escuta.close()


def test_dancar_acaba_com_uma_cara_e_nao_com_um_erro():
    """⚠️ O BUG: o `_dancar` acabava com `eyes.animar("contente")`, mas
    "contente" é uma CARA, não uma animação. A dança acabava com o robô a
    recitar a lista de animações que existem. Passou despercebido enquanto o
    resultado das ações não era falado em voz alta."""
    from robot.brain import tools

    resposta = tools.executar("dancar", {})
    assert not isinstance(resposta, tools.Recusa), resposta
    assert resposta == "Dancei!"
