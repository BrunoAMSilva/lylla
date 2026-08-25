"""Testes dos gestos dos braços.

    pytest

Existem pela mesma razão que os testes das expressões: quando a Lara inventar
um gesto novo e se enganar num nome, isto avisa-a com uma mensagem clara em
vez de o robô fazer um movimento estranho — ou de forçar um servo contra um
batente, o que o queima em segundos.
"""

from __future__ import annotations

import pytest

from robot import config
from robot.gestures import GESTOS, POSES, validar_todos
from robot.hardware import arms


def test_todas_as_poses_e_gestos_sao_validos():
    validar_todos()


def test_gestos_so_usam_poses_que_existem():
    for nome, passos in GESTOS.items():
        for passo, _pausa in passos:
            if isinstance(passo, str):
                assert passo in POSES, f"O gesto '{nome}' usa a pose '{passo}', que não existe."


@pytest.mark.parametrize("nome", sorted(POSES))
def test_poses_so_usam_juntas_configuradas(nome):
    juntas = set(config.obter("bracos.juntas", {}) or {})
    for junta in POSES[nome]:
        assert junta in juntas, f"A pose '{nome}' usa a junta '{junta}', que não existe."


@pytest.mark.parametrize("nome", sorted(POSES))
def test_poses_estao_dentro_dos_limites(nome):
    """Uma pose fora dos limites não parte nada — mas revela um erro de escrita."""
    juntas = config.obter("bracos.juntas", {}) or {}
    for junta, graus in POSES[nome].items():
        cfg = juntas[junta]
        assert cfg["min"] <= graus <= cfg["max"], (
            f"A pose '{nome}' põe '{junta}' a {graus}°, fora dos limites "
            f"[{cfg['min']}, {cfg['max']}] do robot.yaml."
        )


def test_gestos_essenciais_existem():
    """O resto do código conta com estes. Não os apaguem."""
    for essencial in ("acenar", "festejar", "nao_sei"):
        assert essencial in GESTOS


def test_pose_descanso_existe():
    """É a posição para onde o robô volta sempre."""
    assert "descanso" in POSES


def test_angulo_fora_dos_limites_e_corrigido_e_nao_rebenta():
    """A validação é a última defesa da mecânica contra o LLM."""
    juntas = config.obter("bracos.juntas", {}) or {}
    cfg = juntas["garra"]
    arms.angulo("garra", 9999)
    assert arms.posicao_atual()["garra"] == float(cfg["max"])
    arms.angulo("garra", -9999)
    assert arms.posicao_atual()["garra"] == float(cfg["min"])


def test_junta_inexistente_da_erro_claro():
    with pytest.raises(ValueError, match="Não existe a junta"):
        arms.angulo("cauda", 90)


def test_garra_so_aceita_abrir_ou_fechar():
    with pytest.raises(ValueError, match="abrir"):
        arms.garra("esmagar")


def test_gesto_inexistente_da_erro_claro():
    with pytest.raises(ValueError, match="Não existe o gesto"):
        arms.gesto("moonwalk")
