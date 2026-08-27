"""AS ARESTAS — um teste por cada bug que já cá esteve.

    pytest tests/test_cerebro_arestas.py

Nenhum destes casos foi imaginado: saíram todos de uma revisão adversarial ao
código do cérebro, e todos rebentavam mesmo. Ficam aqui para não voltarem.

O padrão é sempre o mesmo, e é o que torna estes bugs perigosos: **nada
estoira à vista**. O robô cala-se a meio de uma frase, ou diz duas coisas ao
mesmo tempo, ou anda 20 cm que ninguém lhe pediu. Ninguém liga isso ao
ficheiro onde o erro está.
"""

from __future__ import annotations

import json

import pytest

from cerebro import pensar
from robot.brain import acoes, tools


# ---------------------------------------------------------------------------
# 1 · Um emoji matava o turno a meio da fala
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("escapado, esperado", [
    (r"😀", "😀"),        # emoji
    (r"🎵", "🎵"),        # nota musical
    (r"ção", "ção"),      # BMP, sempre funcionou
])
def test_um_caractere_fora_do_plano_basico_nao_parte_a_fala(escapado, esperado):
    """Um emoji vem em JSON como DOIS escapes. Descodificados à peça davam
    dois meios-caracteres que não existem em UTF-8: a frase seguia, mas
    rebentava ao ser codificada para a rede — e o turno morria ali, sem
    `resposta` e sem `fim`. A Lara ouvia meia resposta e depois silêncio."""
    texto = '{"expressao":"feliz","fala":"Olha isto. Um ' + escapado + ' para ti.","acoes":[]}'

    for tamanho in (1, 3, 7, 1000):
        extrator = pensar.ExtratorDeFala()
        eventos = []
        for i in range(0, len(texto), tamanho):
            eventos += extrator.alimentar(texto[i:i + tamanho])
        eventos += extrator.terminar()

        assert extrator.fala_completa == json.loads(texto)["fala"]
        assert esperado in extrator.fala_completa
        # o que mata mesmo: isto tem de poder ir para a rede
        json.dumps(eventos, ensure_ascii=False).encode("utf-8")


def test_meia_surrogate_sozinha_nao_rebenta():
    extrator = pensar.ExtratorDeFala()
    eventos = extrator.alimentar(r'{"fala": "solta \ud83d fim."}') + extrator.terminar()
    json.dumps(eventos, ensure_ascii=False).encode("utf-8")


def test_o_turno_sobrevive_a_um_emoji_de_ponta_a_ponta(tmp_path):
    from fastapi.testclient import TestClient

    from cerebro import falar, ouvir, servidor

    class ComEmoji(pensar.MotorTeste):
        def gerar(self, mensagens, esquema):
            self.usou_esquema = True
            self.estatisticas = {}
            conteudo = r'{"expressao":"feliz","fala":"Primeira frase. Segunda com 😀 aqui.","acoes":[]}'
            for i in range(0, len(conteudo), 5):
                yield conteudo[i:i + 5]

    cerebro = pensar.Cerebro("teste")
    cerebro.motor = ComEmoji()
    app = servidor.criar_app(ouvir.Ouvido("teste"), cerebro, falar.Voz("teste", cache=tmp_path))
    with TestClient(app) as cliente:
        linhas = [json.loads(l) for l in cliente.post("/v1/turno", json={"texto": "olá"}).text.splitlines()]

    tipos = [e["tipo"] for e in linhas]
    assert "erro" not in tipos, "o turno morria aqui"
    assert tipos[-1] == "fim"
    assert len([e for e in linhas if e["tipo"] == "frase"]) == 2


# ---------------------------------------------------------------------------
# 2 · A mesma resposta dita duas vezes, sobreposta
# ---------------------------------------------------------------------------


def test_falar_a_serio_espera_pela_vez_em_vez_de_passar_a_frente(monkeypatch):
    """`falar(esperar=True)` sintetizava na thread de quem pedia, POR CIMA do
    que a fila ainda estava a dizer. Duas vozes ao mesmo tempo, e nenhuma
    delas percebível."""
    from robot.voice import speak

    ordem: list[str] = []

    def reproduzir(caminho):
        import time

        nome = str(caminho)
        ordem.append(f"início:{nome}")
        time.sleep(0.05)
        ordem.append(f"fim:{nome}")

    monkeypatch.setattr(speak.config, "a_simular", lambda: False)
    monkeypatch.setattr(speak, "_reproduzir_wav", reproduzir)

    speak.tocar(b"RIFF_da_fila", esperar=False)
    speak.falar("urgente", esperar=True)     # não pode saltar à frente
    speak.esperar_acabar()

    # nenhum "início" pode aparecer entre um "início" e o seu "fim"
    profundidade = 0
    for passo in ordem:
        profundidade += 1 if passo.startswith("início") else -1
        assert profundidade <= 1, f"duas coisas a tocar ao mesmo tempo: {ordem}"


def test_um_audio_estragado_nao_faz_o_robo_repetir_se(monkeypatch):
    """Um `audio_b64` corrompido dá binascii.Error — que é um ValueError. O
    ramo que o apanhava devolvia False e mandava o caminho antigo perguntar
    tudo outra vez, por cima do que já estava a tocar."""
    import robot.main as main
    from robot.brain import cerebro
    from robot import config

    monkeypatch.setattr(config, "a_simular", lambda: False)
    monkeypatch.setattr(main.config, "a_simular", lambda: False)
    monkeypatch.setattr(main.contexto, "montar", lambda *a, **k: {})
    monkeypatch.setattr(main.eyes, "expressao", lambda *a, **k: None)
    monkeypatch.setattr(main.eyes, "animar", lambda *a, **k: None)
    monkeypatch.setattr(main.glow, "pulsar", lambda *a, **k: None)
    monkeypatch.setattr(main.speak, "falar", lambda *a, **k: None)
    monkeypatch.setattr(main.speak, "tocar", lambda *a, **k: None)
    monkeypatch.setattr(main.speak, "esperar_acabar", lambda: None)

    def turno_estragado(**_kwargs):
        yield {"tipo": "ouvido", "texto": "olá"}
        yield {"tipo": "frase", "texto": "Olá, Lara!", "audio": b"x"}
        raise ValueError("Invalid base64-encoded string")

    from robot.brain.state import Maquina

    assert main._consumir_turno(Maquina(), turno_estragado()) is True, \
        "já falou — desistir aqui dava-lhe uma segunda resposta por cima"


# ---------------------------------------------------------------------------
# 3 · Uma resposta sem fala deixava o robô calado
# ---------------------------------------------------------------------------


def test_uma_fala_vazia_ainda_da_uma_frase(tmp_path):
    """O esquema permite `"fala": ""`, e os modelos fazem-no. Sem isto, o robô
    executava a ação em silêncio — a armadilha nº 3 a entrar por outra porta."""
    class Mudo(pensar.MotorTeste):
        def gerar(self, mensagens, esquema):
            self.usou_esquema = True
            self.estatisticas = {}
            yield '{"expressao":"feliz","fala":"","acoes":[{"nome":"gesto","argumentos":{"nome":"acenar"}}]}'

    cerebro = pensar.Cerebro("teste")
    cerebro.motor = Mudo()
    eventos = list(cerebro.pensar("acena!"))
    assert [e for e in eventos if e["tipo"] == "frase"], "o robô tem de dizer alguma coisa"
    assert eventos[-1]["acoes"] == [{"nome": "gesto", "argumentos": {"nome": "acenar"}}]


def test_se_mesmo_assim_nao_falar_o_robo_admite_que_nao_percebeu(monkeypatch):
    import robot.main as main
    from robot import config
    from robot.brain.state import Maquina

    dito: list[str] = []
    monkeypatch.setattr(config, "a_simular", lambda: False)
    monkeypatch.setattr(main.config, "a_simular", lambda: False)
    monkeypatch.setattr(main.contexto, "montar", lambda *a, **k: {})
    monkeypatch.setattr(main.eyes, "expressao", lambda *a, **k: None)
    monkeypatch.setattr(main.eyes, "animar", lambda *a, **k: None)
    monkeypatch.setattr(main.glow, "pulsar", lambda *a, **k: None)
    monkeypatch.setattr(main.speak, "falar", lambda t, esperar=True: dito.append(str(t)))
    monkeypatch.setattr(main.speak, "esperar_acabar", lambda: None)
    monkeypatch.setattr(main.tools, "executar", lambda n, a: "feito")

    def sem_fala(**_kwargs):
        yield {"tipo": "ouvido", "texto": "acena"}
        yield {"tipo": "resposta", "fala": "", "acoes": [], "recusadas": []}
        yield {"tipo": "fim", "tempo_ms": {}}

    main._consumir_turno(Maquina(), sem_fala())
    assert dito == ["Não percebi. Podes repetir?"]


# ---------------------------------------------------------------------------
# 4 · O NaN passava por todos os limites
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), float("-inf")])
def test_nan_e_infinito_sao_recusados(valor):
    """`nan < 5` e `nan > 50` são AMBOS falsos: o NaN escorregava pelos
    limites e só rebentava lá à frente, no int(). E o json.loads aceita o
    literal NaN, portanto um modelo pode mesmo devolvê-lo."""
    ok, razao = acoes.validar({"nome": "mover", "argumentos": {"direcao": "frente", "cm": valor}})
    assert not ok, razao


def test_normalizar_nao_levanta_com_nan():
    """A docstring promete «nunca levanta exceções» — e não cumpria."""
    validas, recusadas = acoes.normalizar([
        {"nome": "virar", "argumentos": {"graus": float("nan")}},
        {"nome": "gesto", "argumentos": {"nome": "acenar"}},
    ])
    assert validas == [{"nome": "gesto", "argumentos": {"nome": "acenar"}}]
    assert recusadas


def test_um_numero_que_nao_se_percebe_nao_vira_20_cm():
    """`_mover` apanhava o erro e usava o valor por omissão: o robô andava
    20 cm por causa de um argumento que devia ter sido recusado. A única
    maneira de darmos por isso era vê-lo andar."""
    for mau in (float("nan"), "vinte", None, [5]):
        resposta = tools.executar("mover", {"direcao": "frente", "cm": mau})
        assert isinstance(resposta, tools.Recusa), f"{mau!r} → {resposta}"
        assert "Andei" not in resposta


# ---------------------------------------------------------------------------
# 5 a 8 · O resto
# ---------------------------------------------------------------------------


def test_a_ligacao_ao_modelo_fecha_se_quem_consome_desistir(monkeypatch):
    """Um comando direto acaba o turno a meio. Sem fechar, o Ollama ficava a
    gerar para um socket que ninguém lê, com o modelo ocupado."""
    fechadas = []

    class RespostaFalsa:
        status_code = 200
        text = ""

        def iter_lines(self):
            for _ in range(1000):
                yield json.dumps({"message": {"content": "a"}}).encode()

        def close(self):
            fechadas.append(True)

    motor = pensar.MotorOllama()
    monkeypatch.setattr(pensar.requests, "post", lambda *a, **k: RespostaFalsa())

    gerador = motor.gerar([{"role": "user", "content": "olá"}], None)
    next(gerador)
    gerador.close()                 # quem consome desiste
    assert fechadas, "a ligação ficou aberta"


def test_saude_e_turno_ao_mesmo_tempo_nao_dao_erro():
    """`sessoes()` iterava o dicionário sem lock enquanto outra thread lhe
    mexia. O 500 resultante lê-se, no arranque do robô, como «o cérebro não
    responde» — com o cérebro perfeitamente de pé."""
    import threading

    cerebro = pensar.Cerebro("teste")
    erros: list[Exception] = []
    parar = threading.Event()

    def a_pensar():
        i = 0
        while not parar.is_set():
            cerebro.responder("olá", sessao=f"s{i}")
            i += 1

    def a_perguntar():
        while not parar.is_set():
            try:
                cerebro.sessoes()
            except Exception as erro:  # noqa: BLE001
                erros.append(erro)

    threads = [threading.Thread(target=a_pensar), threading.Thread(target=a_perguntar)]
    for t in threads:
        t.start()
    threading.Event().wait(1.0)
    parar.set()
    for t in threads:
        t.join(timeout=5)
    assert not erros, erros[:3]


def test_uma_fala_que_nao_e_texto_nao_e_lida_em_voz_alta():
    """O robô dizia literalmente «chavetas texto dois pontos olá Lara»."""
    r = pensar.interpretar('{"expressao":"feliz","fala":{"texto":"olá"},"acoes":[]}',
                           None, acoes.expressoes_disponiveis())
    assert "{" not in r["fala"]
    assert r["recusadas"]


def test_uma_resposta_que_nao_e_json_e_offline_nao_400(monkeypatch):
    """Uma página de erro de um proxy é «o modelo está em baixo», não «o
    pedido estava mal feito» — e o Pi precisa de saber a diferença para usar
    o caminho antigo."""
    class RespostaFalsa:
        status_code = 200
        text = ""

        def iter_lines(self):
            yield b"<html>502 Bad Gateway</html>"

        def close(self):
            pass

    motor = pensar.MotorOllama()
    monkeypatch.setattr(pensar.requests, "post", lambda *a, **k: RespostaFalsa())
    with pytest.raises(pensar.CerebroIndisponivel):
        list(motor.gerar([{"role": "user", "content": "olá"}], None))


def test_a_mesma_frase_pedida_por_duas_threads_nao_parte_a_cache(tmp_path):
    """Duas sínteses do mesmo texto escreviam as duas no mesmo «.parcial», e
    a segunda não encontrava nada para mudar de nome."""
    import threading

    from cerebro import falar

    voz = falar.Voz("teste", cache=tmp_path)
    erros: list[Exception] = []

    def sintetizar():
        try:
            for _ in range(20):
                voz.sintetizar("A mesma frase para toda a gente.")
        except Exception as erro:  # noqa: BLE001
            erros.append(erro)

    threads = [threading.Thread(target=sintetizar) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert not erros, erros[:3]
    assert list(tmp_path.glob("*.parcial")) == []
