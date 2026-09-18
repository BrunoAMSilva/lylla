"""OS TESTES DA NAVEGAÇÃO.

O mais importante está no primeiro: `test_a_conta_e_a_mesma_do_browser`.

O treino acontece no browser (docs/escola-de-conducao.html) e a condução
acontece aqui, em Python. São duas implementações da mesma matemática, e duas
implementações da mesma matemática divergem — é o que elas fazem. Por isso o
piloto.json traz consigo seis casos de teste calculados do lado do browser, e
este ficheiro obriga o Python a dar o mesmo resultado até à nona casa decimal.

No dia em que alguém mudar uma ativação, a ordem dos pesos ou uma constante
da mistura só de um dos lados, é aqui que se sabe — e não no corredor, com a
Lara a ver o robô bater na ombreira.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from robot.navigation import casa as mod_casa
from robot.navigation import piloto as mod_piloto
from robot.navigation.pose import Pose

RAIZ = Path(__file__).resolve().parents[1]
FICHEIRO_CASA = RAIZ / "data" / "casa.json"
FICHEIRO_PILOTO = RAIZ / "data" / "piloto.json"

precisa_de_casa = pytest.mark.skipif(not FICHEIRO_CASA.exists(), reason="falta data/casa.json")
precisa_de_piloto = pytest.mark.skipif(not FICHEIRO_PILOTO.exists(), reason="falta data/piloto.json")


@pytest.fixture(scope="module")
def casa() -> mod_casa.Casa:
    return mod_casa.Casa.de_ficheiro(FICHEIRO_CASA)


@pytest.fixture(scope="module")
def piloto() -> mod_piloto.Piloto:
    return mod_piloto.Piloto.de_ficheiro(FICHEIRO_PILOTO)


# ---------------------------------------------------------------------------
# 1. As duas metades têm de dar o mesmo
# ---------------------------------------------------------------------------

@precisa_de_piloto
def test_a_conta_e_a_mesma_do_browser(piloto):
    problemas = piloto.verificar_contra_o_browser()
    assert not problemas, "o Python e o browser deixaram de concordar:\n" + "\n".join(problemas)


@precisa_de_piloto
def test_o_piloto_traz_casos_de_teste(piloto):
    """Um piloto.json sem casos de teste é um piloto que ninguém pode verificar."""
    assert piloto.dados.get("testes"), "este piloto.json foi gravado sem casos de teste"


@precisa_de_piloto
def test_uma_rede_recusa_entradas_do_tamanho_errado(piloto):
    with pytest.raises(ValueError):
        piloto.rumo.correr([0.0, 0.0])


@precisa_de_casa
def test_uma_planta_sem_paredes_mais_o_que_ela_desenhou_da_rota(casa):
    """O modo descoberta, do lado do robô: a Lylla recebe as divisões com nome
    mas NENHUMA parede, e as paredes que usa são as que desenhou sozinha com o
    ultrassom. Isto prova que não é preciso código novo para isso — a camada
    aprendida já é tratada como parede em tudo o que decide caminho — e que o
    destino não cai dentro de uma parede que ela já conhece.
    """
    import copy

    # a planta sem paredes: mesma grelha, mesmas divisões, zero paredes
    nua = copy.deepcopy(casa)
    nua.parede = bytearray(nua.cols * nua.rows)
    nua.invalidar()

    # e a camada aprendida com as paredes verdadeiras, como se as tivesse medido
    nua.definir_aprendido(bytearray(casa.parede))
    assert nua.celulas_aprendidas() > 0, "a casa de teste não tem paredes nenhumas"

    origem = nua.ponto_da_divisao(0)
    assert origem is not None
    assert not nua.eh_parede(*origem), (
        "o destino caiu dentro de uma parede que ela já tinha desenhado"
    )
    campo = nua.campo_de_celula(*origem)
    alcancaveis = sum(1 for v in campo if v != math.inf)
    assert alcancaveis > nua.cols, (
        "com as paredes desenhadas por ela, a rota deixou de chegar a lado nenhum"
    )


@precisa_de_piloto
def test_a_memoria_comeca_vazia_e_esvazia_se(piloto):
    """Uma viagem nova não herda a manobra da anterior a meio."""
    piloto.reiniciar()
    assert piloto.memoria == [0.0] * piloto.n_memoria
    piloto.decidir([120.0] * piloto.n_feixes, 0.3, 200.0, 10.0, 0.0)
    piloto.reiniciar()
    assert piloto.memoria == [0.0] * piloto.n_memoria


@precisa_de_piloto
def test_com_memoria_a_mesma_leitura_pode_dar_respostas_diferentes(piloto):
    """É ISTO que a memória serve para fazer, e é o que um cérebro sem ela
    não consegue: duas posições que dão a mesma leitura de sensor têm de
    poder ter respostas diferentes, senão contornar uma parede sem mapa é
    impossível por construção — a rede é uma função das entradas.

    Num piloto sem memória isto é impossível e o teste diz isso em voz alta.
    """
    if piloto.n_memoria == 0:
        pytest.skip("este piloto foi treinado sem memória")
    piloto.reiniciar()
    entrada = ([90.0] * piloto.n_feixes, 0.9, 250.0, 12.0, 0.4)
    primeira = piloto.decidir(*entrada).viragem
    for _ in range(6):
        piloto.decidir([30.0] * piloto.n_feixes, -2.4, 250.0, 4.0, 1.1)
    depois = piloto.decidir(*entrada).viragem
    assert primeira != pytest.approx(depois, abs=1e-9), (
        "a memória não está a mudar nada — a ligação de retorno partiu-se"
    )


# ---------------------------------------------------------------------------
# 2. A planta
# ---------------------------------------------------------------------------

@precisa_de_casa
def test_a_casa_de_exemplo_esta_toda_ligada(casa):
    """Todas as divisões se alcançam a partir da partida — senão faltou uma porta."""
    campo = casa.campo_ate(0)
    for k in range(len(casa.divisoes)):
        celulas = [i for i, z in enumerate(casa.zona) if z == k and not casa.parede[i]]
        assert celulas, f"a divisão {casa.divisoes[k].nome} não tem chão"
        assert any(math.isfinite(campo[i]) for i in celulas), \
            f"não há caminho da sala até {casa.divisoes[k].nome}"


@precisa_de_casa
def test_o_campo_e_zero_no_destino_e_infinito_dentro_da_parede(casa):
    campo = casa.campo_ate(1)
    dentro = [i for i, z in enumerate(casa.zona) if z == 1 and not casa.parede[i]]
    assert campo[dentro[0]] == 0
    paredes = [i for i, p in enumerate(casa.parede) if p]
    assert all(math.isinf(campo[i]) for i in paredes[:50])


@precisa_de_casa
def test_descer_o_campo_chega_sempre_ao_destino(casa):
    """A propriedade que faz isto funcionar: de qualquer sítio, andar sempre
    para o vizinho com menor distância acaba no destino. Se falhar, é porque
    o campo tem um mínimo local — e aí não há navegação nenhuma."""
    campo = casa.campo_ate(2)
    for divisao in range(len(casa.divisoes)):
        celulas = [i for i, z in enumerate(casa.zona) if z == divisao and not casa.parede[i]]
        i = celulas[len(celulas) // 2]
        x, y = casa.centro(i % casa.cols, i // casa.cols)
        caminho = casa.descer(campo, x, y)
        fim = caminho[-1]
        assert casa.distancia_em(campo, fim[0], fim[1]) == 0, \
            f"a partir de {casa.divisoes[divisao].nome} o caminho encalhou"


@precisa_de_casa
def test_o_alvo_local_esta_sempre_a_caminho(casa):
    campo = casa.campo_ate(0)
    x, y = casa.centro(*casa.partida)
    alvo = casa.alvo_local(campo, x, y, 55, 12)
    assert casa.distancia_em(campo, *alvo) < casa.distancia_em(campo, x, y)


@precisa_de_casa
def test_nao_cabe_um_robo_dentro_de_uma_parede(casa):
    parede = next(i for i, p in enumerate(casa.parede) if p)
    x, y = casa.centro(parede % casa.cols, parede // casa.cols)
    assert not casa.livre(x, y, 12)


@precisa_de_casa
@pytest.mark.parametrize("dito", ["sala", "Sala", "à sala", "para a sala", "A SALA"])
def test_o_llm_pode_dizer_o_nome_de_varias_maneiras(casa, dito):
    assert casa.indice_divisao(dito) == casa.indice_divisao("sala")


@precisa_de_casa
def test_um_sitio_que_nao_existe_da_menos_um(casa):
    assert casa.indice_divisao("garagem subterrânea") == -1


# ---------------------------------------------------------------------------
# 3. A odometria
# ---------------------------------------------------------------------------

def test_andar_em_frente_anda_em_frente():
    p = Pose()
    p.definir(100, 100, 0.0)
    for _ in range(10):
        p.avancar(1.0, 1.0, 0.1, 22.0, 15.0)
    assert p.x == pytest.approx(100 + 22.0, abs=0.01)
    assert p.y == pytest.approx(100, abs=0.01)
    assert p.rumo == pytest.approx(0.0, abs=1e-9)


def test_rodar_no_sitio_nao_sai_do_sitio():
    p = Pose()
    p.definir(100, 100, 0.0)
    for _ in range(10):
        p.avancar(-1.0, 1.0, 0.1, 22.0, 15.0)
    assert (p.x, p.y) == pytest.approx((100, 100), abs=0.01)
    assert p.rumo != 0.0


def test_a_deriva_so_cresce():
    p = Pose()
    p.definir(0, 0, 0.0)
    anterior = 0.0
    for _ in range(20):
        p.avancar(1.0, 1.0, 0.1, 22.0, 15.0)
        assert p.deriva_cm > anterior
        anterior = p.deriva_cm
    assert p.confianca(55) < 1.0


# ---------------------------------------------------------------------------
# 4. O comportamento — e sobretudo a segurança
# ---------------------------------------------------------------------------

@pytest.fixture
def navegacao(monkeypatch, tmp_path):
    """O ir_para com a casa e o piloto carregados, e um ultrassom a fingir.

    ⚠️ O ultrassom TEM de ver alguma coisa. Antes este teste corria com o
    sensor a dizer sempre «não vejo nada», e passava — até o robô passar a
    parar de vez em quando para se orientar pelo que vê. Num mundo onde não
    se vê nada, orientar-se é impossível, e ele passou a desistir: o teste
    apanhou uma simulação irrealista, não uma regressão.
    """
    monkeypatch.setenv("ROBO_SIMULAR", "1")
    from robot.hardware import sensors
    from robot.navigation import ir_para
    from robot.navigation import varrimento

    def sonar():
        return varrimento.alcance_previsto(
            ir_para._casa, ir_para._pose.x, ir_para._pose.y, ir_para._pose.rumo, 200.0
        )

    monkeypatch.setattr(sensors, "distancia_cm", sonar)
    monkeypatch.setattr(sensors, "ha_precipicio", lambda: False)
    monkeypatch.setattr(ir_para, "_cfg",
                        lambda c, o: str(tmp_path / "mapa.json") if c == "mapa" else o)
    assert ir_para.carregar(forcar=True) is None
    yield ir_para
    ir_para.parar()


@precisa_de_casa
@precisa_de_piloto
def test_atravessa_a_casa_ate_a_cozinha(navegacao):
    estado, _ = navegacao.comecar("cozinha")
    assert estado == "a_ir"
    for _ in range(4000):
        passo = navegacao.um_passo(dt=0.1)
        if passo.terminou:
            break
    assert passo.chegou, f"não chegou: {passo.razao}"


# ---------------------------------------------------------------------------
# 7. A memória do espaço — o mapa que ela desenha sozinha
# ---------------------------------------------------------------------------

def _memoria_vazia(cols=20, rows=20, cm=20.0):
    from robot.navigation.memoria_espaco import MemoriaDoEspaco
    return MemoriaDoEspaco(cols, rows, cm)


def test_uma_leitura_marca_o_que_esta_la_e_o_que_nao_esta():
    """As duas metades de uma leitura: «há algo a 100 cm» e «não há nada antes»."""
    m = _memoria_vazia()
    # de (50, 50) para leste, eco a 100 cm → o obstáculo cai no quadrado 7
    # (x = 150 cm) e o caminho até lá, nos quadrados 2 a 6.
    m.atualizar(50.0, 50.0, 0.0, 100.0, 200.0)
    assert m.valor(7, 2) > 0, "não marcou o obstáculo"
    assert m.valor(4, 2) < 0, "não marcou o caminho até lá como vazio"


def test_o_saco_que_saiu_apaga_se_sozinho():
    """A propriedade que faz um mapa de ocupação funcionar: o que deixou de lá
    estar é apagado pelos raios que passam por onde ele estava."""
    m = _memoria_vazia()
    for _ in range(30):                       # o saco esteve ali muito tempo
        m.atualizar(50.0, 50.0, 0.0, 100.0, 200.0)
    assert m.valor(7, 2) >= 2.0
    for _ in range(30):                       # e agora já não está: os raios
        m.atualizar(50.0, 50.0, 0.0, 180.0, 200.0)   # passam por onde ele estava
    assert m.valor(7, 2) < 0, "o saco ficou no mapa para sempre"


def test_a_evidencia_tem_teto_para_o_mapa_poder_mudar_de_ideias():
    m = _memoria_vazia()
    for _ in range(500):
        m.atualizar(50.0, 50.0, 0.0, 100.0, 200.0)
    from robot.navigation import memoria_espaco
    assert m.valor(7, 2) <= memoria_espaco.TETO
    # e com o teto, chega meia dúzia de leituras contrárias para o desfazer
    for _ in range(40):
        m.atualizar(50.0, 50.0, 0.0, 180.0, 200.0)
    assert m.valor(7, 2) < memoria_espaco.LIMIAR_OCUPADO


def test_visto_duas_vezes_nao_conta_para_a_rota_visto_muitas_conta():
    """É isto, em código, o que se quer: a média entre o saco e o sofá."""
    from robot.navigation import memoria_espaco
    m = _memoria_vazia()
    m.atualizar(50.0, 50.0, 0.0, 100.0, 200.0)
    m.atualizar(50.0, 50.0, 0.0, 100.0, 200.0)
    assert sum(m.ocupadas()) == 0, "duas leituras não podem desviar uma rota"
    for _ in range(30):
        m.atualizar(50.0, 50.0, 0.0, 100.0, 200.0)
    assert sum(m.ocupadas()) > 0, "trinta leituras têm de contar"


def test_sem_eco_e_uma_pista_fraca_e_nao_atravessa_paredes():
    """Uma parede oblíqua não devolve eco. Se «não vejo nada» valesse tanto
    como um eco, ela apagava paredes a olhar para elas de lado."""
    from robot.navigation import memoria_espaco
    com = _memoria_vazia()
    sem = _memoria_vazia()
    com.atualizar(50.0, 50.0, 0.0, 150.0, 200.0)   # 199 já contava como «sem eco»
    sem.atualizar(50.0, 50.0, 0.0, 999.0, 200.0)
    assert abs(sem.valor(4, 2)) < abs(com.valor(4, 2))
    # e para lá de 70% do alcance (140 cm → x = 190 cm), nada
    assert sem.valor(11, 2) == 0.0, "sem eco não pode marcar nada ao longe"


def test_o_mapa_grava_se_e_le_se_igual(tmp_path):
    m = _memoria_vazia()
    for k in range(12):
        m.atualizar(50.0, 50.0, k * 0.5, 60.0 + k * 8, 200.0)
    m.guardar(tmp_path / "mapa.json", "teste")
    from robot.navigation.memoria_espaco import MemoriaDoEspaco
    lido = MemoriaDoEspaco.de_ficheiro(tmp_path / "mapa.json")
    assert lido.ocupadas() == m.ocupadas()


# ---------------------------------------------------------------------------
# 8. A mobília aprendida entra (e sai) do planeamento
# ---------------------------------------------------------------------------

@precisa_de_casa
def test_a_mobilia_aprendida_bloqueia_como_uma_parede(casa):
    livre = next(i for i, p in enumerate(casa.parede) if not p and casa.zona[i] >= 0)
    x, y = livre % casa.cols, livre // casa.cols
    assert not casa.eh_parede(x, y)
    aprendido = bytearray(len(casa.parede))
    aprendido[livre] = 1
    casa.definir_aprendido(aprendido)
    try:
        assert casa.eh_parede(x, y)
        assert casa.celulas_aprendidas() == 1
    finally:
        casa.definir_aprendido(None)


@precisa_de_casa
def test_mudar_a_mobilia_deita_fora_o_campo_antigo(casa):
    antes = casa.campo_ate(0)
    casa.definir_aprendido(bytearray(len(casa.parede)))
    try:
        assert casa.campo_ate(0) is not antes, "ficou com o campo velho em cache"
    finally:
        casa.definir_aprendido(None)


@precisa_de_casa
@precisa_de_piloto
def test_a_mobilia_aprendida_nunca_tranca_uma_porta(navegacao):
    """Uns ecos falsos não podem deixar a Lylla fechada num quarto a dizer
    que não sabe lá ir. Entre acreditar no mapa e sair, sai-se."""
    casa = navegacao._casa
    navegacao.assumir("quarto da Lara")
    casa.definir_aprendido(bytearray([1] * len(casa.parede)))   # tudo bloqueado
    estado, mensagem = navegacao.comecar("cozinha")
    assert estado == "a_ir", mensagem
    # a propriedade que interessa não é a camada estar vazia — é HAVER caminho
    campo = casa.campo_ate(casa.indice_divisao("cozinha"))
    assert math.isfinite(casa.distancia_em(campo, navegacao._pose.x, navegacao._pose.y))


# ---------------------------------------------------------------------------
# 9. O varrimento — descobrir onde se está
# ---------------------------------------------------------------------------

@precisa_de_casa
def test_o_varrimento_encontra_a_posicao_certa(casa):
    """Meio metro ao lado e dez graus torta: uma volta a medir chega para
    voltar ao sítio."""
    import random

    from robot.navigation import varrimento as V

    rnd = random.Random(3)
    vx, vy = casa.centro(8, 6)                       # onde ela ESTÁ
    erro_rumo = math.radians(10)
    amostras = []
    for k in range(36):
        a = k * 2 * math.pi / 36
        d = V.alcance_previsto(casa, vx, vy, a, 200.0)
        d = 999.0 if d >= 200 else max(4.0, d + rnd.gauss(0, 5))
        amostras.append(V.Amostra(a + erro_rumo, d))

    c = V.emparelhar(casa, vx + 40, vy - 35, amostras)   # onde ela JULGA estar
    assert c.aceite, f"não decidiu: erro {c.erro_cm:.1f}, rival {c.erro_rival_cm:.1f}"
    assert math.hypot(c.dx + 40, c.dy - 35) < 20, "corrigiu para o sítio errado"
    assert abs(math.degrees(c.drumo) + 10) < 6


@precisa_de_casa
def test_sem_ecos_nao_decide_nada(casa):
    """Um quarto grande e vazio não devolve ecos nenhuns. A resposta certa
    não é inventar uma posição, é dizer que não sabe."""
    from robot.navigation import varrimento as V

    amostras = [V.Amostra(k * 0.2, 999.0) for k in range(36)]
    c = V.emparelhar(casa, 100.0, 100.0, amostras)
    assert not c.aceite
    assert c.amostras_usadas == 0


@precisa_de_casa
def test_um_empate_nao_e_uma_resposta(casa):
    """Duas explicações igualmente boas para o que vê = não decide."""
    from robot.navigation import varrimento as V

    c = V.Correcao(erro_cm=3.0, erro_rival_cm=3.2, amostras_usadas=20, ambigua=True)
    assert not c.aceite


@precisa_de_casa
@precisa_de_piloto
def test_o_precipicio_manda_mais_que_a_rede(navegacao, monkeypatch):
    from robot.hardware import sensors

    navegacao.comecar("cozinha")
    monkeypatch.setattr(sensors, "ha_precipicio", lambda: True)
    passo = navegacao.um_passo(dt=0.1)
    assert passo.terminou and passo.razao == "precipício"
    assert passo.esquerdo == 0.0 and passo.direito == 0.0
    assert not navegacao.a_navegar()


@precisa_de_casa
@precisa_de_piloto
def test_com_a_parede_colada_roda_mas_nao_avanca(navegacao, monkeypatch):
    from robot.hardware import sensors

    navegacao.comecar("cozinha")
    monkeypatch.setattr(sensors, "distancia_cm", lambda: 10.0)
    passo = navegacao.um_passo(dt=0.1)
    assert passo.razao == "parede colada"
    # rodar no sítio: as rodas em sentidos opostos, e a soma dá zero
    assert passo.esquerdo == pytest.approx(-passo.direito)
    assert passo.esquerdo + passo.direito == pytest.approx(0.0)


@precisa_de_casa
@precisa_de_piloto
def test_desiste_de_estar_encravada(navegacao, monkeypatch):
    from robot.hardware import sensors

    navegacao.comecar("cozinha")
    monkeypatch.setattr(sensors, "distancia_cm", lambda: 5.0)
    for _ in range(200):
        passo = navegacao.um_passo(dt=0.1)
        if passo.terminou:
            break
    assert passo.razao == "encravada"


@precisa_de_casa
@precisa_de_piloto
def test_recusa_um_sitio_que_nao_existe(navegacao):
    estado, mensagem = navegacao.comecar("garagem")
    assert estado == "recusa"
    assert "cozinha" in mensagem          # diz os sítios que conhece


@precisa_de_casa
@precisa_de_piloto
def test_ja_estou_ai_nao_e_uma_recusa(navegacao):
    navegacao.assumir("cozinha")
    estado, mensagem = navegacao.comecar("cozinha")
    assert estado == "ja_estou"
    assert not navegacao.a_navegar()


@precisa_de_casa
@precisa_de_piloto
def test_perdida_recusa_partir(navegacao):
    navegacao._pose.deriva_cm = 999.0
    estado, mensagem = navegacao.comecar("sala")
    assert estado == "recusa"
    assert mensagem == navegacao.PERDIDA


@precisa_de_casa
@precisa_de_piloto
def test_dizer_lhe_onde_esta_limpa_a_deriva(navegacao):
    navegacao._pose.deriva_cm = 999.0
    assert navegacao.assumir("sala") is None
    assert navegacao._pose.deriva_cm < 100
    estado, _ = navegacao.comecar("cozinha")
    assert estado == "a_ir"


# ---------------------------------------------------------------------------
# 5. O contrato com o cérebro
# ---------------------------------------------------------------------------

def test_a_acao_ir_para_esta_no_catalogo():
    from robot.brain import acoes

    assert "ir_para" in acoes.ACOES
    ok, _ = acoes.validar({"nome": "ir_para", "argumentos": {"sitio": "cozinha"}})
    assert ok


@precisa_de_casa
def test_o_catalogo_so_deixa_passar_sitios_que_existem():
    from robot.brain import acoes

    ok, razao = acoes.validar({"nome": "ir_para", "argumentos": {"sitio": "Marte"}})
    assert not ok and "sitio" in razao


def test_a_planta_e_o_piloto_falam_da_mesma_lylla():
    """Um piloto treinado com um robô de outro tamanho conduz outro robô."""
    if not (FICHEIRO_PILOTO.exists() and FICHEIRO_CASA.exists()):
        pytest.skip("faltam os ficheiros")
    p = json.loads(FICHEIRO_PILOTO.read_text(encoding="utf-8"))
    assert p["fisica"]["raio_cm"] == pytest.approx(mod_casa.RAIO_CM)


# ---------------------------------------------------------------------------
# 6. Às escondidas
# ---------------------------------------------------------------------------

class CaraFalsa:
    """Uma observação da câmara, fabricada: «vejo a Lara / não vejo ninguém»."""

    def __init__(self, nome=None):
        self.presente = nome is not None
        self.nome = nome


@pytest.fixture
def jogo(navegacao, tmp_path, monkeypatch):
    from robot.navigation import procurar

    monkeypatch.setattr(procurar, "FICHEIRO_MEMORIA", tmp_path / "esconderijos.json")
    yield procurar
    procurar.parar()


@precisa_de_casa
@precisa_de_piloto
def test_encontrar_alguem_acaba_o_jogo(jogo):
    estado, _ = jogo.comecar("Lara")
    assert estado == "a_procurar"
    passo = jogo.um_passo(CaraFalsa("Lara"))
    assert passo.encontrou and passo.terminou
    assert not jogo.a_procurar()


@precisa_de_casa
@precisa_de_piloto
def test_ver_outra_pessoa_nao_acaba_o_jogo(jogo):
    jogo.comecar("Lara")
    passo = jogo.um_passo(CaraFalsa("Bruno"))
    assert not passo.encontrou and not passo.terminou


@precisa_de_casa
@precisa_de_piloto
def test_aprende_onde_a_encontrou_e_vai_la_primeiro(jogo):
    jogo.comecar("Lara")
    jogo.um_passo(CaraFalsa("Lara"))                  # encontrada onde está
    memoria = jogo.memoria().get("lara", {})
    assert memoria, "não guardou nada"
    favorito = max(memoria, key=memoria.get)
    for _ in range(3):                                # mais três vezes no mesmo sítio
        jogo.comecar("Lara")
        jogo.um_passo(CaraFalsa("Lara"))
    ordem = jogo.ordem_de_procura("Lara")
    from robot.navigation import ir_para
    assert ir_para._casa.divisoes[ordem[0]].nome == favorito


@precisa_de_casa
@precisa_de_piloto
def test_esquecer_limpa_a_memoria(jogo):
    jogo.comecar("Lara")
    jogo.um_passo(CaraFalsa("Lara"))
    assert jogo.memoria()
    jogo.esquecer()
    assert jogo.memoria() == {}


@precisa_de_casa
@precisa_de_piloto
def test_perder_se_e_uma_pergunta_e_nao_o_fim(jogo, monkeypatch):
    """A odometria acaba-se sempre. O que não pode acontecer é o robô parar
    sem dizer porquê — e o jogo tem de poder continuar depois da resposta."""
    from robot.navigation import ir_para

    # sem pausa a espreitar: o teste corre milhares de passos num instante,
    # e a espreitadela conta-se pelo relógio de parede
    monkeypatch.setattr(jogo, "_cfg",
                        lambda chave, omissao: 0.0 if chave == "segundos_a_espreitar" else omissao)
    # ⚠️ E o ultrassom deixa de ver seja o que for: sem ecos, o varrimento não
    #    consegue emparelhar e ela não se safa sozinha. É essa a situação que
    #    este teste descreve — perdida E sem forma de se encontrar. (Com o
    #    varrimento a funcionar, pôr a deriva a 999 já não a deixa perdida:
    #    ela pára, olha à volta e resolve o problema, que é o que se quer.)
    from robot.hardware import sensors
    monkeypatch.setattr(sensors, "distancia_cm", lambda: 999.0)
    jogo.comecar("Lara")
    ir_para._pose.deriva_cm = 999.0
    for _ in range(20000):      # chegar a uma divisão é agora ir ao MEIO dela
        passo = jogo.um_passo(CaraFalsa(None))
        if passo.terminou:
            break
    assert passo.razao == "onde estou"
    assert jogo.a_perguntar(), "devia ficar à espera de resposta, não desistir"
    estado, _ = jogo.responder("cozinha")
    assert estado == "a_procurar"
    assert ir_para._pose.deriva_cm < 100


@precisa_de_casa
@precisa_de_piloto
def test_o_para_desliga_mesmo_o_jogo(jogo, monkeypatch):
    """«PÁRA» tem de desligar o MODO, não só os motores: senão a volta
    seguinte do ciclo principal punha-o a andar outra vez."""
    from robot.brain import comandos_diretos

    jogo.comecar("Lara")
    assert jogo.a_procurar()
    comandos_diretos.tentar("olá robô pára")
    assert not jogo.a_procurar()
    from robot.navigation import ir_para
    assert not ir_para.a_navegar()


@precisa_de_casa
@precisa_de_piloto
def test_dizer_lhe_onde_esta_pela_acao_do_llm(navegacao):
    """«estás na cozinha» chega como ir_para(sitio=cozinha, estou_aqui=true)."""
    from robot.brain import tools

    navegacao._pose.deriva_cm = 999.0
    resposta = tools.IMPLEMENTACOES["ir_para"](sitio="cozinha", estou_aqui=True)
    assert not isinstance(resposta, tools.Recusa)
    assert navegacao._pose.deriva_cm < 100
