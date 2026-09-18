"""Testes do CÉREBRO — o serviço do mini e o cliente do Pi.

    pytest tests/test_cerebro.py

Correm em qualquer máquina e sem modelo nenhum: os três motores têm uma
versão `teste` (o STT devolve texto fixo, o LLM devolve JSON fixo, o TTS faz
um apito). É a mesma ideia do motor `teste` do antigo servidor de voz — sem
isto, não se podia testar o caminho todo sem um Mac com 8 GB de modelos.

O que estes testes protegem, por ordem de importância:

  1. o robô NUNCA fica sem resposta — nem com o mini desligado, nem com o
     modelo a devolver disparates;
  2. a primeira frase sai antes de a resposta estar completa (é isso que
     torna a conversa possível);
  3. nada que o LLM invente chega aos motores.
"""

from __future__ import annotations

import io
import json
import wave

import pytest

from cerebro import falar, ouvir, pensar, servidor

fastapi_testclient = pytest.importorskip("fastapi.testclient")


# ---------------------------------------------------------------------------
# Ferramentas
# ---------------------------------------------------------------------------


def wav_de(segundos: float = 1.0, taxa: int = 16_000, canais: int = 1, largura: int = 2) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(canais)
        w.setsampwidth(largura)
        w.setframerate(taxa)
        w.writeframes(b"\x11\x22" * int(taxa * segundos * canais * (largura // 2)))
    return buffer.getvalue()


@pytest.fixture
def mini(tmp_path):
    """O mac mini de mentira: a mesma app, com os três motores de teste."""
    app = servidor.criar_app(
        ouvir.Ouvido("teste"), pensar.Cerebro("teste"),
        falar.Voz("teste", cache=tmp_path / "voz"),
    )
    with fastapi_testclient.TestClient(app) as cliente:
        yield cliente


def eventos(resposta) -> list[dict]:
    return [json.loads(linha) for linha in resposta.text.splitlines() if linha.strip()]


# ---------------------------------------------------------------------------
# 1 · Ouvir
# ---------------------------------------------------------------------------


def test_transcreve_um_wav(mini):
    r = mini.post("/v1/ouvir", content=wav_de(), headers={"Content-Type": "audio/wav"})
    assert r.status_code == 200
    assert r.json()["texto"]
    assert r.json()["duracao_s"] == 1.0


def test_aceita_o_wav_tambem_em_formulario(mini):
    r = mini.post("/v1/ouvir", files={"audio": ("f.wav", wav_de(), "audio/wav")})
    assert r.status_code == 200 and r.json()["texto"]


def test_um_wav_partido_da_400_e_nao_500(mini):
    """Áudio mau é culpa de quem o mandou. E o robô tem de ouvir uma
    explicação, não um stack trace."""
    r = mini.post("/v1/ouvir", content="isto não é um wav".encode("utf-8"), headers={"Content-Type": "audio/wav"})
    assert r.status_code == 400
    assert "erro" in r.json()


def test_sem_audio_nenhum_da_400(mini):
    assert mini.post("/v1/ouvir", content=b"", headers={"Content-Type": "audio/wav"}).status_code == 400


@pytest.mark.parametrize("taxa, canais", [(8_000, 1), (44_100, 1), (16_000, 2), (48_000, 2)])
def test_converte_o_que_nao_vier_a_16k_mono(taxa, canais):
    """O Pi manda 16 kHz mono, mas um WAV gravado à mão pode vir de outra
    maneira. A conversão é aqui, não no robô."""
    audio, duracao = ouvir.descodificar_wav(wav_de(1.0, taxa, canais))
    assert len(audio) == pytest.approx(ouvir.TAXA, rel=0.01)
    assert duracao == pytest.approx(1.0, rel=0.01)


# ---------------------------------------------------------------------------
# 2 · Pensar — a forma da resposta
# ---------------------------------------------------------------------------


def test_a_resposta_tem_sempre_as_tres_partes(mini):
    r = mini.post("/v1/pensar", json={"texto": "olá"}).json()
    assert set(("expressao", "fala", "acoes")) <= set(r)
    assert r["fala"]
    assert isinstance(r["acoes"], list)


def test_a_cara_vem_antes_da_primeira_frase(mini):
    """O robô muda de expressão ANTES de falar. É isto que o faz parecer vivo
    em vez de uma animação atrasada."""
    linhas = eventos(mini.post("/v1/pensar", json={"texto": "olá", "stream": True}))
    tipos = [e["tipo"] for e in linhas]
    # O `a_pensar` vem antes de tudo (é o que deixa o Pi reagir já); logo a
    # seguir, a cara — antes de qualquer frase.
    assert tipos[0] == "a_pensar"
    assert tipos[1] == "expressao"
    assert "frase" in tipos
    assert tipos[-1] == "resposta"


def test_as_frases_saem_uma_a_uma(mini):
    linhas = eventos(mini.post("/v1/pensar", json={"texto": "olá", "stream": True}))
    frases = [e["texto"] for e in linhas if e["tipo"] == "frase"]
    assert len(frases) >= 2
    assert " ".join(frases) == [e for e in linhas if e["tipo"] == "resposta"][0]["fala"]


def test_uma_ordem_vira_uma_acao(mini):
    r = mini.post("/v1/pensar", json={"texto": "segue-me!"}).json()
    assert [a["nome"] for a in r["acoes"]] == ["seguir"]
    assert r["acoes"][0]["argumentos"] == {"acao": "comecar"}


def test_o_historico_e_por_sessao(mini):
    mini.post("/v1/pensar", json={"texto": "olá", "sessao": "a"})
    mini.post("/v1/pensar", json={"texto": "olá", "sessao": "b"})
    assert set(mini.get("/v1/saude").json()["sessoes"]) == {"a:?", "b:?"}
    mini.post("/v1/esquecer", json={"sessao": "a"})
    assert set(mini.get("/v1/saude").json()["sessoes"]) == {"b:?"}
    mini.post("/v1/esquecer")
    assert mini.get("/v1/saude").json()["sessoes"] == {}


# ---------------------------------------------------------------------------
# 3 · Pensar — o que o modelo inventa não chega aos motores
# ---------------------------------------------------------------------------


def _interpretar(conteudo: str) -> dict:
    from robot.brain import acoes

    return pensar.interpretar(conteudo, None, acoes.expressoes_disponiveis())


def test_uma_acao_inventada_e_deitada_fora():
    r = _interpretar('{"expressao":"feliz","fala":"vou voar!","acoes":[{"nome":"voar","argumentos":{}}]}')
    assert r["acoes"] == []
    assert r["fala"] == "vou voar!"          # a fala fica: o robô responde na mesma
    assert r["recusadas"]


def test_um_argumento_fora_dos_limites_e_deitado_fora():
    r = _interpretar('{"expressao":"feliz","fala":"vou","acoes":[{"nome":"mover","argumentos":{"direcao":"frente","cm":5000}}]}')
    assert r["acoes"] == []


def test_uma_cara_que_nao_existe_nao_passa():
    r = _interpretar('{"expressao":"radioativo","fala":"olá","acoes":[]}')
    assert r["expressao"] is None
    assert r["fala"] == "olá"


def test_texto_sem_json_nenhum_vira_fala():
    """Um modelo que ignore o formato ainda assim faz o robô dizer algo."""
    r = _interpretar("Olá, Lara! Estou aqui.")
    assert "Olá" in r["fala"]
    assert r["acoes"] == []


def test_json_dentro_de_uma_cerca_de_codigo():
    r = _interpretar('```json\n{"expressao":"feliz","fala":"olá","acoes":[]}\n```')
    assert r["fala"] == "olá" and r["expressao"] == "feliz"


def test_json_cortado_a_meio_ainda_da_a_fala():
    """Se o max_tokens cortar a resposta, fica-se com o que já se leu — em vez
    de o robô emudecer no meio de uma frase."""
    extrator = pensar.ExtratorDeFala()
    parcial = '{"expressao": "feliz", "fala": "Olá, Lara! Que bom ver-te. E dep'
    for i in range(0, len(parcial), 7):
        extrator.alimentar(parcial[i:i + 7])
    extrator.terminar()
    from robot.brain import acoes

    r = pensar.interpretar(parcial, extrator, acoes.expressoes_disponiveis())
    assert "Olá, Lara!" in r["fala"]
    assert r["expressao"] == "feliz"


# ---------------------------------------------------------------------------
# 4 · O extrator de fala
# ---------------------------------------------------------------------------


def test_o_extrator_solta_as_frases_a_medida_que_chegam():
    extrator = pensar.ExtratorDeFala()
    texto = '{"expressao": "feliz", "fala": "Olá, Lara! Que bom ver-te. Vamos brincar?", "acoes": []}'
    saidas = []
    for i in range(0, len(texto), 3):
        saidas += extrator.alimentar(texto[i:i + 3])
    saidas += extrator.terminar()
    assert [e["texto"] for e in saidas if e["tipo"] == "frase"] == [
        "Olá, Lara! Que bom ver-te.", "Vamos brincar?",
    ]
    assert saidas[0] == {"tipo": "expressao", "nome": "feliz"}


def test_o_extrator_percebe_escapes_e_unicode():
    extrator = pensar.ExtratorDeFala()
    saidas = extrator.alimentar(r'{"fala": "Ele disse \"olá\" e sorriu. Coração!"}') + extrator.terminar()
    assert [e["texto"] for e in saidas] == ['Ele disse "olá" e sorriu.', "Coração!"]


def test_o_extrator_da_o_mesmo_resultado_de_uma_vez_ou_aos_bocados():
    texto = '{"expressao":"triste","fala":"Oh. Anda cá, eu estou contigo. Queres um abraço?","acoes":[]}'
    de_uma_vez = pensar.ExtratorDeFala()
    a = de_uma_vez.alimentar(texto) + de_uma_vez.terminar()
    aos_bocados = pensar.ExtratorDeFala()
    b = []
    for i in range(0, len(texto), 1):
        b += aos_bocados.alimentar(texto[i])
    b += aos_bocados.terminar()
    assert a == b


def test_uma_frase_curta_junta_se_a_seguinte():
    """"Sim!" sozinha soa cortada. Vai com a frase seguinte."""
    assert pensar.dividir_em_frases("Sim! Vamos lá.") == ["Sim! Vamos lá."]


def test_uma_frase_interminavel_corta_se_numa_virgula():
    longa = "Era uma vez um robô que andava pela casa toda, " + "e via coisas, " * 20
    frases = pensar.dividir_em_frases(longa)
    assert len(frases) > 1
    assert all(len(f) < 400 for f in frases)


# ---------------------------------------------------------------------------
# 5 · Falar
# ---------------------------------------------------------------------------


def test_devolve_um_wav_e_guarda_em_cache(mini):
    primeira = mini.post("/v1/falar", json={"texto": "Olá, Lara!"})
    assert primeira.status_code == 200
    assert primeira.content.startswith(b"RIFF")
    assert primeira.headers["X-Cache"] == "miss"
    assert mini.post("/v1/falar", json={"texto": "Olá, Lara!"}).headers["X-Cache"] == "hit"


def test_texto_vazio_da_400(mini):
    assert mini.post("/v1/falar", json={"texto": "   "}).status_code == 400


def test_o_caminho_antigo_do_servidor_de_voz_continua_a_responder(mini):
    """Um Pi com o `voz.servidor` ainda a apontar para /falar não emudece."""
    r = mini.post("/falar", json={"texto": "Olá"})
    assert r.status_code == 200 and r.content.startswith(b"RIFF")


def test_vozes_e_velocidades_diferentes_dao_ficheiros_diferentes(tmp_path):
    voz = falar.Voz("teste", cache=tmp_path)
    normal, _ = voz.sintetizar("Vamos embora.")
    devagar, _ = voz.sintetizar("Vamos embora.", velocidade=0.5)
    assert normal != devagar
    assert voz.chave("x", "a", 1.0) != voz.chave("x", "b", 1.0)


def test_nao_fica_lixo_parcial_na_cache(tmp_path):
    voz = falar.Voz("teste", cache=tmp_path)
    voz.sintetizar("Uma frase.")
    assert list(tmp_path.glob("*.parcial")) == []
    assert voz.em_cache() == 1


def test_a_voz_diz_de_que_motor_e(tmp_path):
    voz = falar.Voz("teste", cache=tmp_path)
    assert voz.resolver("say:Joana") == ("say", "Joana")
    assert voz.resolver("glados") == ("teste", "glados")
    with pytest.raises(falar.VozIndisponivel):
        voz.resolver("inexistente:x")


# ---------------------------------------------------------------------------
# 6 · O turno completo — é isto que o robô usa
# ---------------------------------------------------------------------------


def test_o_turno_por_audio_faz_tudo(mini):
    linhas = eventos(mini.post("/v1/turno", files={"audio": ("f.wav", wav_de(2), "audio/wav")}))
    tipos = [e["tipo"] for e in linhas]
    assert tipos[0] == "ouvido"
    assert "expressao" in tipos and "frase" in tipos and tipos[-1] == "fim"
    frases = [e for e in linhas if e["tipo"] == "frase"]
    assert all(e["audio_b64"] for e in frases), "cada frase tem de trazer o áudio dela"


def test_o_turno_por_texto_nao_transcreve_nada(mini):
    linhas = eventos(mini.post("/v1/turno", json={"texto": "olá"}))
    assert "ouvido" not in [e["tipo"] for e in linhas]


def test_o_turno_leva_o_contexto_ao_modelo(mini):
    r = mini.post("/v1/turno", json={"texto": "olá", "contexto": {"pessoa": "Lara", "bateria_pct": 80}})
    assert r.status_code == 200 and eventos(r)


def test_um_silencio_acaba_o_turno_com_calma(mini, monkeypatch):
    """O microfone apanhou ruído e o Whisper não percebeu nada: o robô tem de
    saber que não percebeu, não de mandar uma pergunta vazia ao modelo."""
    monkeypatch.setattr(mini.app.state.ouvido.motor, "texto_seguinte", "")
    linhas = eventos(mini.post("/v1/turno", files={"audio": ("f.wav", wav_de(1), "audio/wav")}))
    assert linhas[-1]["motivo"] == "nao_percebi"
    assert not [e for e in linhas if e["tipo"] == "frase"]


def test_o_turno_traz_os_tempos(mini):
    fim = eventos(mini.post("/v1/turno", json={"texto": "olá"}))[-1]
    assert fim["tipo"] == "fim"
    assert "total" in fim["tempo_ms"] and "primeira_frase" in fim["tempo_ms"]


def test_se_o_modelo_morrer_a_meio_o_erro_vem_no_fluxo(mini, monkeypatch):
    """Um 500 a meio de um fluxo já começado seria um silêncio inexplicável.
    O erro vai como mais um evento, e o robô diz alguma coisa."""
    def rebentar(*_a, **_k):
        raise pensar.CerebroIndisponivel("o Ollama fugiu")

    monkeypatch.setattr(mini.app.state.cerebro.motor, "gerar", rebentar)
    linhas = eventos(mini.post("/v1/turno", json={"texto": "olá"}))
    assert linhas[-1]["tipo"] == "erro"
    assert linhas[-1]["offline"] is True


# ---------------------------------------------------------------------------
# 7 · Saúde e contrato
# ---------------------------------------------------------------------------


def test_a_saude_diz_o_que_esta_a_correr(mini):
    dados = mini.get("/v1/saude").json()
    assert dados["ok"]
    for parte in ("ouvir", "pensar", "falar"):
        assert dados[parte]["motor"] == "teste"


def test_as_capacidades_sao_o_contrato(mini):
    from robot.brain import acoes

    dados = mini.get("/v1/capacidades").json()
    assert set(dados["acoes"]) == set(acoes.ACOES)
    assert dados["esquema"] == acoes.esquema_json()
