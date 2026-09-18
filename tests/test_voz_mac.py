"""Testes da voz — o Pi a pedir a Joana ao Mac.

    pytest tests/test_voz_mac.py

Estes testes existem por uma razão só, e é a mais importante de todas: **o robô
tem de continuar a falar com o Mac desligado**. A voz da Lara escolhida (Joana)
só existe no macOS, e o que a torna utilizável num robô que anda pela casa é a
cache em disco do Pi. Se a cache se partir, o robô emudece — e ninguém dá por
isso até estar a brincar com ele.

Correm em qualquer máquina: o servidor tem um motor `teste` que faz um apito,
para não ser preciso um Mac para testar o caminho todo.
"""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from robot.voice import speak

RAIZ = Path(__file__).resolve().parent.parent


def _carregar_servidor():
    caminho = RAIZ / "scripts" / "servidor_voz.py"
    spec = importlib.util.spec_from_file_location("servidor_voz", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


servidor_voz = _carregar_servidor()


@pytest.fixture
def mac(tmp_path):
    """Um Mac de mentira: mesmo serviço, motor de apito, porta ao calhas."""
    servidor_voz._opcoes.motor = "teste"
    servidor_voz._opcoes.voz = "Joana"
    servidor_voz._opcoes.velocidade = 1.0
    servidor_voz.CACHE = tmp_path / "cache-do-mac"

    http = ThreadingHTTPServer(("127.0.0.1", 0), servidor_voz.Manipulador)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{http.server_address[1]}"
    http.shutdown()
    http.server_close()


@pytest.fixture
def pi(tmp_path, monkeypatch):
    """O lado do Pi: cache limpa e configuração controlada."""
    cache = tmp_path / "cache-do-pi"
    monkeypatch.setattr(speak, "CACHE", cache)
    monkeypatch.setattr(speak, "_avisado_do_mac", False)

    definicoes: dict[str, object] = {}

    def obter(caminho, omissao=None):
        return definicoes.get(caminho, omissao)

    monkeypatch.setattr(speak.config, "obter", obter)
    return definicoes, cache


# ---------------------------------------------------------------------------
# 1 · O caminho normal
# ---------------------------------------------------------------------------


def test_pede_ao_mac_e_guarda_em_disco(mac, pi):
    definicoes, cache = pi
    definicoes["voz.servidor"] = f"{mac}/falar"

    caminho = speak._pedir_ao_mac("Olá Lara!")

    assert caminho is not None
    assert caminho.is_file()
    assert caminho.parent == cache
    assert caminho.read_bytes().startswith(b"RIFF")


def test_sem_servidor_configurado_nao_tenta_a_rede(pi):
    definicoes, _ = pi
    assert speak._pedir_ao_mac("Olá Lara!") is None


# ---------------------------------------------------------------------------
# 2 · O que interessa mesmo: falar com o Mac desligado
# ---------------------------------------------------------------------------


def test_com_o_mac_desligado_a_frase_em_cache_continua_a_sair(mac, pi):
    definicoes, _ = pi
    definicoes["voz.servidor"] = f"{mac}/falar"

    primeira = speak._pedir_ao_mac("Tenho a bateria fraca.")
    assert primeira is not None

    # O Mac vai abaixo (porta morta, nada a responder).
    definicoes["voz.servidor"] = "http://127.0.0.1:9/falar"
    definicoes["voz.tempo_limite_s"] = 1

    segunda = speak._pedir_ao_mac("Tenho a bateria fraca.")
    assert segunda == primeira, "a cache tem de ser consultada ANTES da rede"


def test_com_o_mac_desligado_uma_frase_nova_devolve_none_sem_rebentar(pi):
    definicoes, _ = pi
    definicoes["voz.servidor"] = "http://127.0.0.1:9/falar"
    definicoes["voz.tempo_limite_s"] = 1

    assert speak._pedir_ao_mac("Uma frase que ele nunca disse.") is None


def test_falar_nao_rebenta_sem_voz_nenhuma(pi, monkeypatch):
    """Sem Mac, sem Piper e sem espeak-ng, o robô cala-se — mas não estoira."""
    definicoes, _ = pi
    definicoes["voz.servidor"] = "http://127.0.0.1:9/falar"
    definicoes["voz.tempo_limite_s"] = 1
    monkeypatch.setattr(speak.config, "a_simular", lambda: False)
    monkeypatch.setattr(speak, "_iniciar", lambda: None)

    speak._falar_agora("Isto não se ouve em lado nenhum.")


# ---------------------------------------------------------------------------
# 3 · A cache não pode enganar-se de voz nem ficar meia escrita
# ---------------------------------------------------------------------------


def test_vozes_diferentes_dao_ficheiros_diferentes(mac, pi):
    definicoes, _ = pi
    definicoes["voz.servidor"] = f"{mac}/falar"

    definicoes["voz.voz_mac"] = "Joana"
    joana = speak._pedir_ao_mac("Bom dia.")
    definicoes["voz.voz_mac"] = "Catarina"
    catarina = speak._pedir_ao_mac("Bom dia.")

    assert joana != catarina


def test_velocidade_diferente_da_ficheiro_diferente(mac, pi):
    definicoes, _ = pi
    definicoes["voz.servidor"] = f"{mac}/falar"

    definicoes["voz.velocidade_fala"] = 1.0
    normal = speak._pedir_ao_mac("Vamos embora.")
    definicoes["voz.velocidade_fala"] = 0.8
    devagar = speak._pedir_ao_mac("Vamos embora.")

    assert normal != devagar


def test_nao_fica_lixo_parcial_na_cache(mac, pi):
    definicoes, cache = pi
    definicoes["voz.servidor"] = f"{mac}/falar"

    speak._pedir_ao_mac("Uma frase qualquer.")

    assert list(cache.glob("*.parcial")) == []
    assert speak.frases_em_cache() == 1


# ---------------------------------------------------------------------------
# 4 · O serviço do Mac
# ---------------------------------------------------------------------------


def test_saude_responde(mac):
    with urllib.request.urlopen(f"{mac}/saude", timeout=5) as r:
        dados = json.load(r)
    assert dados["ok"] is True
    assert dados["motor"] == "teste"


def test_texto_vazio_da_erro_e_nao_500(mac):
    pedido = urllib.request.Request(
        f"{mac}/falar", data=json.dumps({"texto": "   "}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as erro:
        urllib.request.urlopen(pedido, timeout=5)
    assert erro.value.code == 400


def test_o_mac_tambem_guarda_em_cache(mac):
    for _ in range(2):
        pedido = urllib.request.Request(
            f"{mac}/falar", data=json.dumps({"texto": "Repetida."}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(pedido, timeout=5) as r:
            assert r.read().startswith(b"RIFF")

    assert len(list(servidor_voz.CACHE.glob("*.wav"))) == 1


# ---------------------------------------------------------------------------
# 5 · O interruptor de motor e o modo inglês
# ---------------------------------------------------------------------------


class _VozFalsa:
    """Um Piper de mentira que escreve um WAV válido."""

    def synthesize_wav(self, texto, ficheiro, cfg=None):
        ficheiro.setnchannels(1)
        ficheiro.setsampwidth(2)
        ficheiro.setframerate(22050)
        ficheiro.writeframes(b"\x00\x00" * 2205)


def test_motor_piper_nao_chega_a_pedir_ao_mac(pi, monkeypatch):
    """Com a voz da GLaDOS no Pi, o robô não precisa da rede — nem lhe toca."""
    definicoes, _ = pi
    definicoes["voz.motor"] = "piper"
    definicoes["voz.servidor"] = "http://127.0.0.1:9/falar"

    pedidos = []
    monkeypatch.setattr(speak.config, "a_simular", lambda: False)
    monkeypatch.setattr(speak, "_pedir_ao_mac", lambda t: pedidos.append(t))
    monkeypatch.setattr(speak, "_iniciar", lambda: _VozFalsa())
    monkeypatch.setattr(speak, "_reproduzir_wav", lambda c: None)

    speak._falar_agora("Hello Lara.")

    assert pedidos == [], "com motor=piper o Mac nem devia ser contactado"


def test_por_omissao_o_mac_vem_primeiro(mac, pi, monkeypatch):
    definicoes, _ = pi
    definicoes["voz.servidor"] = f"{mac}/falar"
    usou_piper = []
    monkeypatch.setattr(speak.config, "a_simular", lambda: False)
    monkeypatch.setattr(speak, "_iniciar", lambda: usou_piper.append(1))
    monkeypatch.setattr(speak, "_reproduzir_wav", lambda c: None)

    speak._falar_agora("Bom dia.")

    assert usou_piper == [], "com motor=mac o Piper só entra se o Mac falhar"


def test_modo_ingles_muda_o_system_prompt(monkeypatch):
    """A voz inglesa obriga o LLM a pensar em inglês, não só a soar a inglês."""
    from robot.brain import personalidade

    definicoes = {"lingua": "pt"}
    monkeypatch.setattr(personalidade.config, "obter",
                        lambda caminho, omissao=None: definicoes.get(caminho, omissao))

    em_portugues = personalidade.carregar()
    assert "ENGLISH MODE" not in em_portugues

    definicoes["lingua"] = "en"
    em_ingles = personalidade.carregar()
    assert "ENGLISH MODE" in em_ingles

    # ⚠️ A instrução vai À FRENTE, e a regra de língua sai. Acrescentá-la no
    #    fim não chegava: o gemma4:e4b lia a parede de português primeiro e
    #    respondia em português com `lingua: "en"` bem posto.
    assert em_ingles.startswith("ENGLISH MODE")
    assert "Falas português de Portugal" not in em_ingles

    # O resto da personalidade que a Lara escreveu mantém-se toda.
    # (As regras de tutor têm uma versão por língua; o que conta aqui é o
    # texto DELA.)
    for linha in personalidade.texto_base().splitlines():
        if linha.strip() and "portugu" not in linha.lower():
            assert linha in em_ingles, f"perdeu-se: {linha!r}"
