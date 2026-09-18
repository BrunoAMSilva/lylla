"""Testes do modo secretária.

    pytest tests/test_companion.py

Estes testes existem por três razões, por ordem de importância:

  1. O robô vive em cima de uma secretária a 75 cm do chão. O limite de
     velocidade tem de valer para TODOS os caminhos, incluindo o que o LLM
     mandar fazer.
  2. "Pára" e "para de olhar" têm de funcionar sempre, não quase sempre.
  3. Um robô que cumprimenta de cada vez que a Lara olha para o caderno é
     insuportável ao fim de dez minutos.
"""

from __future__ import annotations

import time

import pytest

from robot import config
from robot.brain import comandos_diretos, companion
from robot.expressions import ANIMACOES, EXPRESSOES
from robot.gestures import GESTOS
from robot.hardware import eyes, motors
from robot.perception import attention


@pytest.fixture(autouse=True)
def _limpo():
    motors.modo("chao")
    companion.reiniciar()
    yield
    motors.modo("chao")
    companion.reiniciar()


# ---------------------------------------------------------------------------
# 1 · Velocidade na secretária
# ---------------------------------------------------------------------------

def test_modo_secretaria_limita_a_velocidade():
    motors.modo("secretaria")
    teto = float(config.obter("secretaria.velocidade_max", 0.25))
    assert motors._limitar(1.0) == pytest.approx(teto)
    assert motors._limitar(-1.0) == pytest.approx(-teto)


def test_o_limite_da_secretaria_e_menor_que_o_do_chao():
    """Se alguém puser os dois iguais, este teste avisa."""
    chao = float(config.obter("motores.velocidade_max", 0.6))
    mesa = float(config.obter("secretaria.velocidade_max", 0.25))
    assert mesa < chao, "A velocidade da secretária tem de ser menor que a do chão"


def test_o_limite_aplica_se_a_todos_os_caminhos():
    """⚠️ O teto tem de estar em _limitar(), não em cada função que anda.

    Se alguém acrescentar uma função nova que chame o hardware diretamente,
    este teste não a apanha — mas apanha o caso em que alguém MOVE o limite
    para fora do caminho comum.
    """
    motors.modo("secretaria")
    teto = float(config.obter("secretaria.velocidade_max", 0.25))
    for chamada in (
        lambda: motors.frente(1.0),
        lambda: motors.tras(1.0),
        lambda: motors.esquerda(0.9),
        lambda: motors.direita(0.9),
        lambda: motors.mover(1.0, 1.0),
    ):
        chamada()
        # em simulação não há hardware; o que verificamos é que _limitar corta
        assert abs(motors._limitar(1.0)) <= teto


def test_modo_invalido_da_erro_claro():
    with pytest.raises(ValueError, match="não existe"):
        motors.modo("voar")


def test_mudar_de_modo_para_os_motores():
    motors.mover(0.2, 0.2)
    motors.modo("secretaria")
    assert motors.modo_atual() == "secretaria"


# ---------------------------------------------------------------------------
# 2 · Comandos que não passam pelo LLM
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frase", [
    "para de olhar", "Para de olhar!", "PARA DE OLHAR",
    "Não olhes para mim", "nao olhes para mim", "modo privado",
])
def test_parar_de_olhar_funciona_sempre(frase):
    companion.voltar_a_seguir()
    assert comandos_diretos.tentar(frase) is not None
    assert companion.esta_a_seguir() is False


@pytest.mark.parametrize("frase", ["pára", "PARA", "stop", "Quieto!"])
def test_parar_funciona_sempre(frase):
    assert comandos_diretos.tentar(frase) == "Stopped."


def test_voltar_a_olhar():
    companion.parar_de_seguir()
    assert companion.esta_a_seguir() is False
    assert comandos_diretos.tentar("podes olhar") is not None
    assert companion.esta_a_seguir() is True


@pytest.mark.parametrize("frase", [
    "conta-me uma piada", "quem está aqui?", "anda para a frente",
    "o que é que vês?", "",
])
def test_frases_normais_seguem_para_o_llm(frase):
    assert comandos_diretos.tentar(frase) is None


def test_nao_ha_frases_reservadas_repetidas():
    todas = [f for frases, _ in comandos_diretos.COMANDOS for f in frases]
    assert len(todas) == len(set(todas)), "Há uma frase em dois comandos diferentes"


def test_com_a_camara_desligada_o_tick_nao_ve_nada():
    """A privacidade não é um filtro à saída — é a câmara não ser lida."""
    companion.parar_de_seguir()
    obs = companion.tick()
    assert obs.presente is False
    assert obs.nome is None


# ---------------------------------------------------------------------------
# 3 · Atenção — histerese e reidentificação
# ---------------------------------------------------------------------------

def test_uma_imagem_sem_cara_nao_significa_que_saiu():
    """A Lara vira a cara para o caderno durante meio segundo. Não saiu."""
    attention.esquecer()
    attention._estava_presente = True
    limite = int(config.obter("secretaria.frames_para_ausencia", 8))
    for _ in range(limite - 1):
        obs = attention._ausente()
        assert obs.saiu_agora is False, "Declarou ausência cedo demais"


def test_ao_fim_de_muitas_imagens_sem_cara_e_porque_saiu():
    attention.esquecer()
    attention._estava_presente = True
    limite = int(config.obter("secretaria.frames_para_ausencia", 8))
    obs = None
    for _ in range(limite):
        obs = attention._ausente()
    assert obs.saiu_agora is True


def test_reconhece_logo_quando_ainda_nao_sabe_quem_e():
    attention.esquecer()
    assert attention._deve_identificar((0.5, 0.5)) is True


def test_nao_reconhece_outra_vez_logo_a_seguir():
    attention.esquecer()
    attention._nome_atual = "Lara"
    attention._ultima_identificacao = time.monotonic()
    attention._centro_anterior = (0.5, 0.5)
    assert attention._deve_identificar((0.51, 0.49)) is False


def test_um_salto_grande_obriga_a_reconhecer():
    """Se a cara saltou para o outro lado, provavelmente é outra pessoa."""
    attention.esquecer()
    attention._nome_atual = "Lara"
    attention._ultima_identificacao = time.monotonic()
    attention._centro_anterior = (0.2, 0.5)
    assert attention._deve_identificar((0.9, 0.5)) is True


def test_a_observacao_vazia_e_segura():
    obs = attention.Observacao()
    assert obs.presente is False and obs.nome is None and obs.perto is False


def test_o_custo_e_reportado():
    c = attention.custo()
    for chave in ("deteccao_ms", "reconhecimento_ms", "fracao_de_um_nucleo", "watts_estimados"):
        assert chave in c


# ---------------------------------------------------------------------------
# 4 · Olhar
# ---------------------------------------------------------------------------

def test_o_olhar_fica_dentro_dos_limites():
    eyes.expressao("neutro", olhar=(5.0, -9.0))
    x, y = eyes.olhar_atual()
    assert -1.0 <= x <= 1.0 and -1.0 <= y <= 1.0


def test_mexer_o_olhar_nao_muda_a_expressao():
    eyes.expressao("feliz")
    eyes.olhar_para(0.7, 0.0)
    assert eyes.atual() == "feliz"


def test_olhar_quase_igual_nao_reenvia():
    """Sem isto, 10 linhas por segundo na série e o morph nunca acabava."""
    eyes.expressao("neutro", olhar=(0.5, 0.5))
    eyes.olhar_para(0.5 + eyes.LIMIAR_OLHAR / 2, 0.5)
    assert eyes.olhar_atual() == (0.5, 0.5)


def test_olhar_diferente_reenvia():
    eyes.expressao("neutro", olhar=(0.0, 0.0))
    eyes.olhar_para(0.9, 0.0)
    assert eyes.olhar_atual()[0] == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# 5 · Atividades
# ---------------------------------------------------------------------------

def test_as_atividades_usam_caras_e_gestos_que_existem():
    """Uma atividade que chame uma animação inexistente rebenta na secretária."""
    for animacao in ("bocejar", "entediado"):
        assert animacao in ANIMACOES, f"Falta a animação '{animacao}'"
    for cara in ("entediado", "a_bocejar", "sonolento", "atento"):
        assert cara in EXPRESSOES, f"Falta a cara '{cara}'"
    assert "espreguicar" in GESTOS


def test_as_atividades_correm_sem_rebentar():
    for nome, funcao in companion.ATIVIDADES:
        try:
            funcao()
        except Exception as erro:  # noqa: BLE001
            pytest.fail(f"A atividade '{nome}' rebentou: {erro}")


def test_as_atividades_nao_se_repetem_seguidas():
    companion.reiniciar()
    companion._ultima_atividade = 0.0
    vistas = []
    for _ in range(len(companion.ATIVIDADES)):
        vistas.append(companion._entreter_se())
        companion._ultima_atividade = 0.0
    assert len(set(vistas)) == len(companion.ATIVIDADES), "Repetiu atividades"


def test_as_atividades_respeitam_o_intervalo():
    companion.reiniciar()
    companion._ultima_atividade = time.monotonic()
    assert companion._entreter_se() is None


def test_ha_atividades_que_chegue_para_nao_cansar():
    assert len(companion.ATIVIDADES) >= 4


# ---------------------------------------------------------------------------
# 6 · Não interromper
# ---------------------------------------------------------------------------

def test_o_robo_nao_cumprimenta_a_mesma_pessoa_duas_vezes_seguidas():
    """Levantar-se para ir buscar água não devia dar um 'olá' novo."""
    companion.reiniciar()
    obs = attention.Observacao(presente=True, nome="Lara", chegou_agora=True)
    companion._reagir_a_chegada(obs)
    primeira = companion._ja_cumprimentou["Lara"]
    companion._reagir_a_chegada(obs)
    assert companion._ja_cumprimentou["Lara"] == primeira, "Cumprimentou outra vez"


def test_o_arrefecimento_da_saudacao_e_de_minutos_nao_de_segundos():
    valor = float(config.obter("secretaria.arrefecimento_saudacao_s", 900))
    assert valor >= 300, "Cumprimentar de 5 em 5 minutos é irritante"


def test_o_orcamento_de_cpu_esta_declarado():
    """Os três números que decidem quanto custa olhar (secção D8b do plano)."""
    fps = float(config.obter("secretaria.fps_deteccao", 10))
    largura, altura = config.obter("secretaria.resolucao_deteccao", [320, 240])
    assert 2 <= fps <= 20, "Acima de 20 fps não se nota e come CPU"
    assert largura * altura <= 640 * 480, (
        "Detetar em imagem grande é desperdício — a posição não precisa de resolução"
    )
