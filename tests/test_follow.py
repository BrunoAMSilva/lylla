"""Testes do modo seguir.

    pytest tests/test_follow.py

O controlador dá-se para testar todo sem robô — é aritmética. A perceção
(seguir umas costas, não uma cara) é que precisa do robô real, e por isso
não está aqui.

O teste mais importante deste ficheiro é o primeiro: **o precipício ganha
sempre**. Um robô que persegue uma criança persegue-a até às escadas.
"""

from __future__ import annotations

import pytest

from robot import config
from robot.brain import follow


# ---------------------------------------------------------------------------
# 1 · Os vetos ganham a tudo
# ---------------------------------------------------------------------------

def test_o_precipicio_ganha_sempre():
    """Mesmo com o alvo mesmo à frente e longe, um degrau para o robô."""
    c = follow.calcular(x=0.0, area=0.02, distancia_cm=300, ha_precipicio=True)
    assert c.parado
    assert "precipício" in c.razao


def test_o_precipicio_ganha_ao_obstaculo_e_ao_alvo():
    for x in (-1.0, 0.0, 1.0):
        for area in (0.0, 0.05, 0.5):
            assert follow.calcular(x, area, 300, ha_precipicio=True).parado


def test_um_obstaculo_perto_para_o_robo():
    minima = float(config.obter("seguranca.distancia_min_cm", 25))
    c = follow.calcular(x=0.0, area=0.02, distancia_cm=minima - 1)
    assert c.parado and "obstáculo" in c.razao


def test_sem_alvo_o_robo_para():
    """⚠️ Nunca continuar às cegas na última direção conhecida."""
    c = follow.calcular(x=None, area=0.0, distancia_cm=300)
    assert c.parado and "perdi" in c.razao


# ---------------------------------------------------------------------------
# 2 · Velocidade
# ---------------------------------------------------------------------------

def test_nunca_passa_do_limite():
    v_max = float(config.obter("seguir.velocidade_max", 0.35))
    for x in (-1.0, -0.5, 0.0, 0.5, 1.0):
        for area in (0.0, 0.02, 0.08, 0.15):
            c = follow.calcular(x, area, 300)
            assert abs(c.esquerdo) <= v_max + 1e-9
            assert abs(c.direito) <= v_max + 1e-9


def test_o_limite_do_seguir_e_menor_que_o_do_chao():
    """A conta do D17: os sensores de precipício não travam a toda a velocidade."""
    chao = float(config.obter("motores.velocidade_max", 0.6))
    seguir = float(config.obter("seguir.velocidade_max", 0.35))
    assert seguir < chao


def test_abranda_ao_aproximar_se():
    longe = follow.calcular(x=0.0, area=0.02, distancia_cm=300)
    meio = follow.calcular(x=0.0, area=0.11, distancia_cm=300)
    assert 0 < meio.esquerdo < longe.esquerdo


def test_para_quando_chega_perto():
    perto = float(config.obter("seguir.area_parar", 0.16))
    c = follow.calcular(x=0.0, area=perto + 0.01, distancia_cm=300)
    assert c.parado and "perto" in c.razao


def test_a_velocidade_e_continua_e_nao_salta():
    """Sem saltos: um degrau de velocidade sente-se como um empurrão."""
    anterior = None
    for i in range(40):
        area = 0.20 * i / 39
        v = follow.calcular(x=0.0, area=area, distancia_cm=300).esquerdo
        if anterior is not None:
            assert abs(v - anterior) < 0.12, f"salto em área={area:.3f}"
        anterior = v


# ---------------------------------------------------------------------------
# 3 · Direção
# ---------------------------------------------------------------------------

def test_alvo_a_direita_vira_a_direita():
    c = follow.calcular(x=0.8, area=0.02, distancia_cm=300)
    assert c.esquerdo > c.direito


def test_alvo_a_esquerda_vira_a_esquerda():
    c = follow.calcular(x=-0.8, area=0.02, distancia_cm=300)
    assert c.direito > c.esquerdo


def test_alvo_ao_centro_anda_a_direito():
    c = follow.calcular(x=0.0, area=0.02, distancia_cm=300)
    assert c.esquerdo == pytest.approx(c.direito)


def test_a_zona_morta_evita_o_tremer():
    """Sem zona morta, o robô corrige à volta do centro e treme."""
    morta = float(config.obter("seguir.zona_morta", 0.12))
    c = follow.calcular(x=morta * 0.5, area=0.02, distancia_cm=300)
    assert c.esquerdo == pytest.approx(c.direito)


def test_normalizar_mantem_a_curva():
    """⚠️ Cortar a roda que passa do limite mudaria a DIREÇÃO da curva.

    Com x=1 e avanço no máximo, as duas rodas normalizadas têm de manter a
    diferença entre elas proporcional — senão o robô curva menos do que devia
    exatamente quando mais precisa.
    """
    c = follow.calcular(x=1.0, area=0.0, distancia_cm=300)
    v_max = float(config.obter("seguir.velocidade_max", 0.35))
    assert max(abs(c.esquerdo), abs(c.direito)) == pytest.approx(v_max)
    assert c.esquerdo > c.direito


# ---------------------------------------------------------------------------
# 4 · A conta que decide se isto é seguro
# ---------------------------------------------------------------------------

def test_o_tcrt5000_no_para_choques_so_da_para_velocidade_de_secretaria():
    """O número que decidiu o desenho todo do modo seguir (D17).

    Um sensor que vê o degrau ~5 cm à frente das rodas só é seguro até
    ~27 cm/s — que é a velocidade da secretária, não a de seguir alguém.
    """
    v = follow.velocidade_segura_cm_s(margem_cm=5.0)
    assert 20 < v < 35, f"esperava ~27 cm/s, deu {v:.0f}"


def test_um_tof_apontado_ao_chao_muda_tudo():
    """Ver 30 cm à frente em vez de 5 triplica a velocidade segura."""
    v = follow.velocidade_segura_cm_s(margem_cm=30.0)
    assert v > 70, f"esperava ~81 cm/s, deu {v:.0f}"
    assert v > 2.5 * follow.velocidade_segura_cm_s(margem_cm=5.0)


def test_sem_margem_nenhuma_nao_ha_velocidade_segura():
    assert follow.velocidade_segura_cm_s(margem_cm=0.0) == 0.0


def test_a_velocidade_configurada_esta_dentro_do_que_e_seguro():
    """⚠️ O teste que liga a configuração à física.

    Se alguém subir o `seguir.velocidade_max` no YAML acima do que os
    sensores conseguem travar, isto avisa — em vez de o robô descobrir
    sozinho ao fundo das escadas.
    """
    cm_por_s_no_maximo = float(config.obter("motores.cm_por_segundo", 18.0)) / \
        float(config.obter("motores.velocidade", 0.5))
    configurada = float(config.obter("seguir.velocidade_max", 0.35)) * cm_por_s_no_maximo
    segura = follow.velocidade_segura_cm_s(margem_cm=5.0)
    assert configurada <= segura, (
        f"O modo seguir está configurado para {configurada:.0f} cm/s mas os "
        f"sensores de precipício só travam a tempo até {segura:.0f} cm/s. "
        f"Baixar seguir.velocidade_max ou montar um ToF apontado ao chão (D17)."
    )


def test_o_modo_seguir_vem_desligado_de_origem():
    """⚠️ É comportamento da fase 16. Não pode ligar-se sozinho antes disso."""
    assert bool(config.obter("seguir.ativo", False)) is False
