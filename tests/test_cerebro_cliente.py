"""Testes do lado do PI: o cliente que fala com o mini.

    pytest tests/test_cerebro_cliente.py

Levantam um mini de mentira numa porta ao calhas (o mesmo serviço, com os
motores de teste) e apontam-lhe o cliente do robô — a rede é a sério, os
modelos é que não. O que interessa provar aqui é o contrário do outro
ficheiro: **o que acontece quando o mini NÃO está lá.**
"""

from __future__ import annotations

import threading
import wave
import io

import pytest

from robot.brain import cerebro

pytest.importorskip("uvicorn")


@pytest.fixture
def mini(tmp_path, monkeypatch):
    """Um mini a sério, numa porta livre. Devolve o URL base."""
    import uvicorn

    from cerebro import falar, ouvir, pensar, servidor

    app = servidor.criar_app(
        ouvir.Ouvido("teste"), pensar.Cerebro("teste"),
        falar.Voz("teste", cache=tmp_path / "mini"),
    )
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    servidor_http = uvicorn.Server(config)
    thread = threading.Thread(target=servidor_http.run, daemon=True)
    thread.start()
    for _ in range(200):                     # esperar que a porta esteja aberta
        if servidor_http.started:
            break
        threading.Event().wait(0.05)
    porta = servidor_http.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{porta}"
    servidor_http.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def robo(monkeypatch):
    """A configuração do robô, controlada pelo teste."""
    definicoes: dict[str, object] = {}
    monkeypatch.setattr(cerebro.config, "obter",
                        lambda caminho, omissao=None: definicoes.get(caminho, omissao))
    monkeypatch.setattr(cerebro.config, "a_simular", lambda: False)
    monkeypatch.setattr(cerebro, "_avisado", False)
    return definicoes


def wav(segundos: float = 1.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(b"\x11\x22" * int(16_000 * segundos))
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# 1 · O caminho normal
# ---------------------------------------------------------------------------


def test_ve_que_o_mini_esta_de_pe(robo, mini):
    robo["cerebro.url"] = mini
    assert cerebro.ligado()
    assert cerebro.saude()["ok"]


def test_um_turno_traz_a_fala_o_audio_e_as_acoes(robo, mini):
    robo["cerebro.url"] = mini
    tipos, frases, acoes = [], [], []
    for evento in cerebro.turno(wav=wav(), contexto={"pessoa": "Lara"}):
        tipos.append(evento["tipo"])
        if evento["tipo"] == "frase":
            frases.append(evento)
        elif evento["tipo"] == "resposta":
            acoes = evento["acoes"]
    assert tipos[0] == "ouvido" and tipos[-1] == "fim"
    assert frases and all(f["audio"].startswith(b"RIFF") for f in frases), \
        "o áudio tem de chegar ao Pi já em bytes, pronto a tocar"
    assert isinstance(acoes, list)


def test_um_turno_por_texto_funciona_sem_microfone(robo, mini):
    robo["cerebro.url"] = mini
    frases = [e["texto"] for e in cerebro.turno(texto="segue-me!") if e["tipo"] == "frase"]
    assert frases


def test_transcrever_e_sintetizar_sozinhos(robo, mini):
    robo["cerebro.url"] = mini
    assert cerebro.transcrever(wav())
    assert cerebro.sintetizar("Olá").startswith(b"RIFF")


def test_o_wav_que_o_pi_manda_e_16k_mono(robo):
    import numpy as np

    dados = cerebro.para_wav(np.zeros(16_000, dtype=np.float32))
    with wave.open(io.BytesIO(dados), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16_000)
        assert w.getnframes() == 16_000


# ---------------------------------------------------------------------------
# 2 · O QUE INTERESSA MESMO: o mini desligado
# ---------------------------------------------------------------------------


def test_com_o_mini_desligado_o_turno_levanta_semcerebro(robo):
    robo["cerebro.url"] = "http://127.0.0.1:9"
    robo["cerebro.timeout_ligar_s"] = 1
    with pytest.raises(cerebro.SemCerebro):
        list(cerebro.turno(texto="olá"))


def test_com_o_mini_desligado_transcrever_e_sintetizar_devolvem_vazio(robo):
    """Não levantam: quem chama já tem um recurso local para isto."""
    robo["cerebro.url"] = "http://127.0.0.1:9"
    robo["cerebro.timeout_ouvir_s"] = 1
    robo["cerebro.timeout_falar_s"] = 1
    assert cerebro.transcrever(wav()) == ""
    assert cerebro.sintetizar("Olá") is None


def test_com_o_mini_desligado_ligado_da_false_e_nao_rebenta(robo):
    robo["cerebro.url"] = "http://127.0.0.1:9"
    robo["cerebro.timeout_saude_s"] = 1
    assert cerebro.ligado() is False
    assert cerebro.saude() is None


def test_queixa_se_uma_vez_e_nao_a_cada_frase(robo, capsys):
    """Um aviso por frase encheria o terminal e escondia o resto."""
    robo["cerebro.url"] = "http://127.0.0.1:9"
    robo["cerebro.timeout_falar_s"] = 1
    for _ in range(3):
        cerebro.sintetizar("Olá")
    assert capsys.readouterr().out.count("não respondeu") == 1


def test_um_url_sem_barra_a_mais(robo):
    robo["cerebro.url"] = "http://mac.local:8420/"
    assert cerebro.base_url() == "http://mac.local:8420"


# ---------------------------------------------------------------------------
# 3 · A voz do robô continua a sair do sítio certo
# ---------------------------------------------------------------------------


def test_a_voz_usa_o_cerebro_quando_nao_ha_voz_servidor(monkeypatch):
    """Um endereço só. Sem `voz.servidor`, a voz vem do mesmo mini."""
    from robot.voice import speak

    definicoes = {"cerebro.url": "http://mini.local:8420"}
    monkeypatch.setattr(speak.config, "obter",
                        lambda caminho, omissao=None: definicoes.get(caminho, omissao))
    assert speak._url_do_servidor() == "http://mini.local:8420/v1/falar"

    definicoes["voz.servidor"] = "http://outro:9000/falar"
    assert speak._url_do_servidor() == "http://outro:9000/falar"


def test_a_voz_pede_ao_mini_e_guarda_em_disco(monkeypatch, tmp_path, robo, mini):
    """O ciclo todo: o Pi pede ao mini, guarda, e da segunda vez não vai à
    rede — que é o que o faz falar com o mini desligado."""
    from robot.voice import speak

    definicoes = {"cerebro.url": mini}
    monkeypatch.setattr(speak.config, "obter",
                        lambda caminho, omissao=None: definicoes.get(caminho, omissao))
    monkeypatch.setattr(speak, "CACHE", tmp_path / "voz")

    primeira = speak._pedir_ao_mac("Olá, Lara!")
    assert primeira is not None and primeira.read_bytes().startswith(b"RIFF")

    definicoes["cerebro.url"] = "http://127.0.0.1:9"      # o mini vai abaixo
    definicoes["voz.tempo_limite_s"] = 1
    assert speak._pedir_ao_mac("Olá, Lara!") == primeira, "a cache vem ANTES da rede"
    assert speak._pedir_ao_mac("Uma frase nova.") is None


def test_tocar_audio_nao_rebenta_com_lixo(monkeypatch):
    from robot.voice import speak

    monkeypatch.setattr(speak.config, "a_simular", lambda: False)
    monkeypatch.setattr(speak, "_reproduzir_wav", lambda caminho: None)
    speak._tocar_agora("isto não é um wav".encode("utf-8"))     # não levanta


def test_as_frases_tocam_por_ordem(monkeypatch):
    """A segunda frase chega enquanto a primeira ainda toca. A fila é o que
    garante que não tocam por cima uma da outra."""
    from robot.voice import speak

    tocadas: list[str] = []
    monkeypatch.setattr(speak.config, "a_simular", lambda: False)
    monkeypatch.setattr(speak, "_reproduzir_wav", lambda caminho: tocadas.append(str(caminho)))

    speak.tocar(b"RIFF____primeira", esperar=False)
    speak.tocar(b"RIFF____segunda", esperar=False)
    speak.esperar_acabar()
    assert len(tocadas) == 2
