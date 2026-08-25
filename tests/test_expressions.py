"""Testes das caras do robô.

    pytest

Existem por uma razão prática: quando a Lara mexer nos números do
config/expressoes.yaml e escrever um valor impossível, isto avisa-a com uma
mensagem clara — em vez de o robô mostrar uma coisa estranha e ninguém
perceber porquê.
"""

from __future__ import annotations

import pytest

from robot.expressions import (
    ANIMACOES, ESSENCIAIS, EXPRESSOES, OMISSAO,
    cor_base, morph_ms, parametros, validar_todas,
)


def test_o_yaml_e_valido():
    validar_todas()


def test_caras_essenciais_existem():
    """O resto do código conta com estas. Não as apaguem."""
    for nome in ESSENCIAIS:
        assert nome in EXPRESSOES, f"Falta a cara '{nome}'"


def test_animacoes_so_usam_caras_que_existem():
    for anim, passos in ANIMACOES.items():
        for cara, _pausa in passos:
            assert cara in EXPRESSOES, (
                f"A animação '{anim}' usa a cara '{cara}', que não existe."
            )


@pytest.mark.parametrize("nome", sorted(EXPRESSOES))
def test_cada_cara_fica_completa(nome):
    """Os valores por omissão preenchem tudo o que o YAML não disser."""
    p = parametros(nome)
    for chave in OMISSAO:
        assert chave in p, f"A cara '{nome}' ficou sem '{chave}'"
    assert "cor" in p
    assert "abertura_esq" in p and "abertura_dir" in p


@pytest.mark.parametrize("nome", sorted(EXPRESSOES))
def test_cores_sao_hex_de_6_digitos(nome):
    cor = parametros(nome)["cor"]
    assert len(cor) == 6
    assert all(c in "0123456789ABCDEF" for c in cor)


def test_cara_inexistente_da_erro_claro():
    with pytest.raises(ValueError, match="Não existe a cara"):
        parametros("cara_de_batata")


def test_coracao_e_vermelho():
    """O Astro mostra corações vermelhos — é o caso que justificou o RGB."""
    p = parametros("coracao")
    assert p["forma"] == "coracao"
    r = int(p["cor"][0:2], 16)
    g = int(p["cor"][2:4], 16)
    assert r > 200 and g < 120, "O coração devia ser bem vermelho"


def test_cor_base_e_o_ciano_do_astro():
    assert cor_base() == "36E0FF"


def test_morph_e_percetivel_mas_nao_lento():
    assert 60 <= morph_ms() <= 600


def test_piscadela_fecha_so_um_olho():
    p = parametros("piscadela")
    assert p["abertura_esq"] != p["abertura_dir"]


def test_valores_estao_dentro_dos_limites():
    """Um número absurdo no YAML tem de ser apanhado antes de chegar ao ESP32."""
    for nome in EXPRESSOES:
        p = parametros(nome)
        assert 0.0 <= float(p["abertura_esq"]) <= 1.0
        assert 0.0 <= float(p["abertura_dir"]) <= 1.0
        assert 0.5 <= float(p["rx"]) <= 12.0
        assert -1.0 <= float(p["arco"]) <= 1.0
