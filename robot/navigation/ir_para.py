"""IR ATÉ UMA DIVISÃO DA CASA.

╔══════════════════════════════════════════════════════════════════════════╗
║  A REGRA MAIS IMPORTANTE DESTE FICHEIRO                                  ║
║                                                                          ║
║  A REDE NEURONAL NÃO É O SISTEMA DE SEGURANÇA.                           ║
║                                                                          ║
║  O piloto treinado decide para onde virar e a que velocidade ir. O que   ║
║  ele NÃO decide é se pode andar: isso é dos sensores, e a resposta       ║
║  deles não se discute. O precipício trava, o obstáculo colado trava, e   ║
║  travam ANTES de a rede ser consultada — não «com muito peso na          ║
║  mistura», não «quase sempre». Travam.                                   ║
║                                                                          ║
║  Isto não é desconfiança da rede: é que uma rede treinada em simulação   ║
║  aprendeu o mundo que nós lhe demos, e o degrau da cozinha não estava    ║
║  lá. Um sistema aprendido decide o COMO; um sistema escrito à mão        ║
║  decide o SE. Trocar os dois é a forma clássica de partir um robô.       ║
╚══════════════════════════════════════════════════════════════════════════╝

O CICLO, dez vezes por segundo:

    1. os sensores têm a última palavra (precipício? parede colada?)
    2. onde é que ela julga estar          → pose.py
    3. para onde é o próximo ponto da rota → casa.py (campo de distância)
    4. o que fazem as rodas                → piloto.py (as três redes)
    5. e a segurança corta o que for preciso ao resultado

Ligar isto ao ciclo principal é uma linha, ao lado do `follow` (main.py):

    if ir_para.a_navegar():
        ir_para.um_passo()
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path

from robot import config
from robot.hardware import motors, sensors
from robot.navigation import casa as mod_casa
from robot.navigation import memoria_espaco
from robot.navigation import piloto as mod_piloto
from robot.navigation import varrimento as mod_varrimento
from robot.navigation.pose import Pose

RAIZ = Path(__file__).resolve().parents[2]


@dataclass
class Comando:
    """O que aconteceu neste passo — igual em espírito ao follow.Comando."""

    esquerdo: float = 0.0
    direito: float = 0.0
    razao: str = "parado"
    terminou: bool = False
    chegou: bool = False

    @property
    def parado(self) -> bool:
        return self.esquerdo == 0.0 and self.direito == 0.0


# ---------------------------------------------------------------------------
# O estado — um só, como no follow. Quem faz alguma coisa com ele é o ciclo
# principal, que chama um_passo() a cada volta enquanto a_navegar() for True.
# ---------------------------------------------------------------------------

_casa: mod_casa.Casa | None = None
_piloto: mod_piloto.Piloto | None = None
_pose = Pose()
_destino = -1
_ponto_destino: tuple[float, float] | None = None
_campo: list[float] | None = None
_activo = False
_inicio = 0.0
_ultimo_passo = 0.0
_limite_s = 0.0
_melhor_dist = math.inf
_sem_progresso = 0
_passos_encravado = 0
_ultima_razao = "parado"

# --- a memória do espaço, e o varrimento que a usa para se encontrar ------
_memoria: memoria_espaco.MemoriaDoEspaco | None = None
_fase = "conduzir"                    # "conduzir" · "varrer"
_varrimento: mod_varrimento.Varrimento | None = None
_proxima_atualizacao_mapa = 0.0
_ultima_correcao = None


def _cfg(chave: str, omissao):
    return config.obter(f"navegacao.{chave}", omissao)


def _caminho(chave: str, omissao: str) -> Path:
    valor = str(_cfg(chave, omissao))
    p = Path(valor)
    return p if p.is_absolute() else RAIZ / p


# ---------------------------------------------------------------------------
# Carregar a planta e o cérebro (uma vez, e nunca durante uma viagem)
# ---------------------------------------------------------------------------

def carregar(forcar: bool = False) -> str | None:
    """Devolve None se correu bem, ou a explicação do que falta."""
    global _casa, _piloto, _pose
    if _casa is not None and _piloto is not None and not forcar:
        return None
    fc = _caminho("casa", "data/casa.json")
    fp = _caminho("piloto", "data/piloto.json")
    if not fc.exists():
        return f"I don't have the house plan ({fc.name}). Draw it in the driving school page."
    if not fp.exists():
        return f"I don't have a trained pilot ({fp.name}). Train it in the driving school page."
    try:
        _casa = mod_casa.Casa.de_ficheiro(fc)
        _piloto = mod_piloto.Piloto.de_ficheiro(fp)
    except Exception as erro:  # noqa: BLE001
        _casa = _piloto = None
        return f"The house plan or the pilot is broken: {erro}"
    if _piloto.n_feixes > 1 and _cfg("feixes_reais", 1) < _piloto.n_feixes:
        print(f"⚠️  O piloto foi treinado com {_piloto.n_feixes} feixes e o robô só tem "
              f"{_cfg('feixes_reais', 1)}. Vai conduzir às cegas para os lados — "
              f"treina um piloto de 1 feixe, ou monta os sensores que faltam.")
    _carregar_memoria()
    x, y = _casa.centro(*_casa.partida)
    _pose.definir(x, y, 0.0)
    return None


def _carregar_memoria() -> None:
    """A mobília que ela já aprendeu, de execuções anteriores.

    Um mapa velho é melhor do que mapa nenhum: as paredes não mudaram, e o
    sofá provavelmente também não. O que mudou (o saco que já lá não está)
    apaga-se sozinho à primeira vez que um raio passar por lá.
    """
    global _memoria
    assert _casa is not None
    if not _cfg("mapear", True):
        _memoria = None
        return
    fm = _caminho("mapa", "data/mapa.json")
    try:
        if fm.exists():
            _memoria = memoria_espaco.MemoriaDoEspaco.de_ficheiro(fm)
            if (_memoria.cols, _memoria.rows) != (_casa.cols, _casa.rows):
                print("⚠️  O mapa aprendido é de outra planta. Começo um novo.")
                _memoria = None
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Não consegui ler o mapa aprendido ({erro}). Começo um novo.")
        _memoria = None
    if _memoria is None:
        _memoria = memoria_espaco.MemoriaDoEspaco.de_casa(_casa)
    _aplicar_mapa(forcar=True)


def guardar_memoria() -> None:
    if _memoria is None or _casa is None:
        return
    try:
        _memoria.guardar(_caminho("mapa", "data/mapa.json"), _casa.nome)
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Não consegui guardar o mapa aprendido: {erro}")


def _aplicar_mapa(forcar: bool = False) -> None:
    """Passar a mobília aprendida ao planeamento.

    ⚠️ COM UMA REDE DE SEGURANÇA. Um eco falso teimoso podia marcar uma porta
    como fechada e trancar a Lylla num quarto — a planta diria que há caminho
    e ela não encontraria nenhum. Por isso, depois de aplicar a camada, se o
    destino deixou de ser alcançável, a camada é deitada fora: entre acreditar
    no mapa e conseguir sair do quarto, sai-se do quarto.
    """
    global _campo, _proxima_atualizacao_mapa
    if _memoria is None or _casa is None:
        return
    _proxima_atualizacao_mapa = time.monotonic() + float(_cfg("segundos_entre_mapas", 2.0))
    antes = _casa.aprendido
    _casa.definir_aprendido(_memoria.ocupadas())
    if _destino < 0:
        return
    campo = _casa.campo_de_celula(*_casa.ponto_da_divisao(_destino))
    if math.isfinite(_casa.distancia_em(campo, _pose.x, _pose.y)):
        _campo = campo
        return
    print("⚠️  A mobília aprendida fechava o caminho todo — ignoro-a nesta viagem.")
    _casa.definir_aprendido(antes)
    _campo = _casa.campo_de_celula(*_casa.ponto_da_divisao(_destino))


def divisoes() -> list[str]:
    """Os nomes que se podem dizer em voz alta. Vazio = ainda não há planta."""
    if carregar() is not None or _casa is None:
        return []
    return _casa.nomes()


def permitido() -> bool:
    """Em simulação anda sempre — não há nada para partir. No robô a sério,
    é preciso ligar `navegacao.ativo` de propósito, depois de os sensores de
    precipício estarem montados e testados. Mesma lógica do `seguir`."""
    if config.a_simular():
        return True
    return bool(_cfg("ativo", False))


# ---------------------------------------------------------------------------
# Começar, parar, saber
# ---------------------------------------------------------------------------

def comecar(nome_divisao: str) -> tuple[str, str]:
    """Aponta o robô a uma divisão.

    Devolve (estado, mensagem), com estado em:
        "a_ir"      aceitou e começou a andar
        "ja_estou"  já lá está — não é recusa nem erro
        "recusa"    não vai, e a mensagem diz porquê (é para ser dita em voz alta)
    """
    global _destino, _campo, _activo, _inicio, _ultimo_passo, _limite_s
    global _melhor_dist, _sem_progresso, _passos_encravado

    erro = carregar()
    if erro:
        return ("recusa", erro)
    assert _casa is not None and _piloto is not None
    if not permitido():
        return ("recusa", "I'm not allowed to walk around the house on my own yet.")

    idx = _casa.indice_divisao(nome_divisao)
    if idx < 0:
        return ("recusa", f"I don't know any place called {nome_divisao}. "
                          f"Conheço: {', '.join(_casa.nomes())}.")

    perdida_de_todo = _pose.deriva_cm > mod_varrimento.BUSCA_CM * 1.5
    if perdida_de_todo:
        # Para lá do que o varrimento consegue procurar, emparelhar é adivinhar
        # com confiança — e isso é pior do que perguntar.
        return ("recusa", PERDIDA)

    global _ponto_destino
    celula = _casa.ponto_da_divisao(idx)
    if celula is None:
        return ("recusa", f"The room {_casa.divisoes[idx].nome} has no floor on the plan.")
    _ponto_destino = _casa.centro(*celula)
    campo = _casa.campo_de_celula(*celula)
    distancia = _casa.distancia_em(campo, _pose.x, _pose.y)
    if not math.isfinite(distancia) and _casa.aprendido is not None:
        # ⚠️ A MOBÍLIA APRENDIDA NUNCA PODE TRANCAR UMA PORTA. Um punhado de
        #    ecos falsos num sítio errado chegava para o mapa dizer que não há
        #    caminho — e a Lylla ficava num quarto a dizer que não sabe lá ir,
        #    com a porta aberta à frente. Entre acreditar no que aprendeu e
        #    conseguir sair, sai-se.
        print("⚠️  A mobília aprendida fechava o caminho todo — ignoro-a nesta viagem.")
        _casa.definir_aprendido(None)
        campo = _casa.campo_de_celula(*celula)
        distancia = _casa.distancia_em(campo, _pose.x, _pose.y)
    if not math.isfinite(distancia):
        return ("recusa", f"I don't know how to get to the {_casa.divisoes[idx].nome} from here. A door is missing on the plan.")
    if _chegou(_pose.x, _pose.y):
        parar()
        return ("ja_estou", f"I'm already {em_ingles(_casa.divisoes[idx].nome, 'em')}!")

    _destino, _campo, _activo = idx, campo, True
    _inicio = _ultimo_passo = time.monotonic()
    # Tempo de sobra, mas não infinito: três vezes o que demoraria em linha
    # reta à velocidade máxima. Passado isto, alguma coisa correu mal e é
    # melhor parar do que continuar a esbarrar.
    _limite_s = max(20.0, (distancia / _piloto.v_max_cm_s) * 3.0 + 10.0)
    _melhor_dist = distancia
    _sem_progresso = 0
    _passos_encravado = 0
    _piloto.reiniciar()
    _aplicar_mapa(forcar=True)
    if _pose.deriva_cm > float(_cfg("deriva_para_varrer", 30)):
        _comecar_varrimento()
        return ("a_ir", f"I'm going {em_ingles(_casa.divisoes[idx].nome)}. Let me just check where I am.")
    return ("a_ir", f"I'm going {em_ingles(_casa.divisoes[idx].nome)}.")


def parar() -> None:
    global _activo, _fase
    _activo = False
    _fase = "conduzir"
    motors.parar()
    guardar_memoria()


def a_navegar() -> bool:
    return _activo


def assumir(nome_divisao: str) -> str | None:
    """«Estás na cozinha.» — repõe a posição e limpa a deriva acumulada.

    É a correção mais barata que existe e resolve 90% dos problemas de
    odometria numa casa: de vez em quando, uma pessoa diz onde ele está.
    """
    global _pose
    erro = carregar()
    if erro:
        return erro
    assert _casa is not None
    idx = _casa.indice_divisao(nome_divisao)
    if idx < 0:
        return f"I don't know any place called {nome_divisao}."
    celulas = [i for i, z in enumerate(_casa.zona) if z == idx and not _casa.parede[i]]
    if not celulas:
        return f"The room {_casa.divisoes[idx].nome} has no floor on the plan."
    sx = sum((i % _casa.cols) + 0.5 for i in celulas) / len(celulas)
    sy = sum((i // _casa.cols) + 0.5 for i in celulas) / len(celulas)
    # A deriva não fica a zero: sabe-se a DIVISÃO, não o ponto exato dela.
    _pose.definir(sx * _casa.cm, sy * _casa.cm, _pose.rumo, deriva_cm=_casa.cm)
    return None


def estado() -> dict:
    return {
        "a_navegar": _activo,
        "destino": _casa.divisoes[_destino].nome if (_casa and 0 <= _destino) else None,
        "x_cm": round(_pose.x, 1),
        "y_cm": round(_pose.y, 1),
        "rumo_graus": round(math.degrees(_pose.rumo), 1),
        "deriva_cm": round(_pose.deriva_cm, 1),
        "razao": _ultima_razao,
        "fase": _fase,
        "mapa": _memoria.resumo().__dict__ if _memoria else None,
        "mobilia_aprendida": _casa.celulas_aprendidas() if _casa else 0,
    }


# ---------------------------------------------------------------------------
# UM PASSO
# ---------------------------------------------------------------------------

def um_passo(dt: float | None = None) -> Comando:
    """Um décimo de segundo de viagem.

    `dt` em segundos. Deixar a None mede o tempo real entre chamadas, que é o
    que se quer no robô; passar um valor é para os testes e para quem tem um
    ciclo de ritmo garantido. O piloto foi treinado a 10 Hz — quanto mais
    longe disso o ciclo andar, mais diferente do simulador ele conduz.
    """
    global _ultimo_passo, _melhor_dist, _sem_progresso, _passos_encravado, _ultima_razao

    if not _activo or _casa is None or _piloto is None or _campo is None:
        return Comando(razao="parado")

    agora = time.monotonic()
    if dt is None:
        dt = min(0.5, max(0.02, agora - _ultimo_passo))
    _ultimo_passo = agora

    # --- 1. OS SENSORES TÊM A ÚLTIMA PALAVRA -------------------------------
    if sensors.ha_precipicio():
        parar()
        _ultima_razao = "precipício"
        return Comando(razao="precipício", terminou=True)

    distancia = sensors.distancia_cm()

    # --- 1b. a dar uma volta a ver onde está? -----------------------------
    if _fase == "varrer":
        return _passo_do_varrimento(distancia, dt)
    minimo = float(config.obter("seguranca.distancia_min_cm", 25))
    aviso = float(config.obter("seguranca.distancia_aviso_cm", 40))

    # --- 2. onde está, e para onde vai ------------------------------------
    alvo = _casa.alvo_local(_campo, _pose.x, _pose.y, _piloto.lookahead_cm, _piloto.raio_cm)
    erro_rumo = _angulo(math.atan2(alvo[1] - _pose.y, alvo[0] - _pose.x) - _pose.rumo)
    dist_alvo = math.hypot(alvo[0] - _pose.x, alvo[1] - _pose.y)

    # --- 3. o piloto ------------------------------------------------------
    decisao = _piloto.decidir(
        _feixes(distancia), erro_rumo, dist_alvo,
        _v_estimada, _w_estimada, _sem_progresso,
    )
    esq, dir_ = decisao.esquerdo, decisao.direito
    razao = "a caminho"

    # --- 4. o que a segurança corta ao que o piloto pediu ------------------
    if distancia < minimo:
        # Não anda mais para a frente. Continua a poder RODAR, e roda para o
        # lado que o piloto queria — a segurança tira a velocidade, não o
        # sentido; se lhe tirássemos o sentido também, ficava encravada a
        # olhar para a parede.
        #
        # ⚠️ E SE AO FIM DE DOIS SEGUNDOS AINDA LÁ ESTIVER, TENTA O OUTRO LADO.
        #    Com um só sensor à frente ela não sabe de que lado há saída, e a
        #    escolha do piloto pode estar simplesmente errada — insistir nela
        #    durante seis segundos é como empurrar uma porta que se puxa.
        giro = 0.3 if decisao.viragem >= 0 else -0.3
        if (_passos_encravado // 20) % 2 == 1:
            giro = -giro
        esq, dir_ = -giro, giro
        razao = "parede colada"
        _passos_encravado += 1
        if _passos_encravado > int(_cfg("passos_encravado", 60)):
            parar()
            _ultima_razao = "encravada"
            return Comando(razao="encravada", terminou=True)
    else:
        _passos_encravado = 0
        if distancia < aviso:
            esq *= 0.5
            dir_ *= 0.5
            razao = "devagar, há algo à frente"

    # --- 5. mexer, e acreditar que se mexeu -------------------------------
    escala = min(float(_cfg("velocidade_max", 0.45)),
                 float(config.obter("motores.velocidade_max", 0.6)))
    motors.mover(esq * escala, dir_ * escala)
    _atualizar_pose(esq, dir_, dt)
    _aprender_o_espaco(distancia)

    # --- 6. já chegou? ficou perdida? demorou de mais? ---------------------
    d = _casa.distancia_em(_campo, _pose.x, _pose.y)
    if math.isfinite(d) and d < _melhor_dist - 1:
        _melhor_dist = d
        _sem_progresso = 0
    else:
        _sem_progresso += 1

    if _chegou(_pose.x, _pose.y):
        parar()
        _ultima_razao = "cheguei"
        return Comando(esq, dir_, "cheguei", terminou=True, chegou=True)

    # ⚠️ VERIFICAR CEDO E COM REGULARIDADE, NÃO SÓ EM PÂNICO.
    #
    # A tentação é só ir ver onde se está quando já se está perdida. Não
    # funciona, por duas razões: a conta da deriva é OTIMISTA (não sabe da
    # roda que patina hoje), e o emparelhamento só procura meio metro à volta
    # — quando a conta finalmente dispara, o erro verdadeiro já pode estar
    # fora do alcance da procura, e aí ela «corrige-se» com toda a confiança
    # para o sítio errado.
    #
    # Por isso: de três em três metros, ou aos 30 cm de deriva calculada, o
    # que vier primeiro. Custa oito segundos e mantém o erro sempre dentro do
    # que a procura consegue apanhar.
    if (_pose.deriva_cm > float(_cfg("deriva_para_varrer", 30))
            or _pose.percorrido_cm > float(_cfg("metros_entre_varrimentos", 3.0)) * 100):
        _comecar_varrimento()
        _ultima_razao = "vou ver onde estou"
        return Comando(razao="vou ver onde estou")

    if agora - _inicio > _limite_s:
        parar()
        _ultima_razao = "demorou de mais"
        return Comando(razao="demorou de mais", terminou=True)

    _ultima_razao = razao
    return Comando(esq, dir_, razao)


# ---------------------------------------------------------------------------
# Os pormenores
# ---------------------------------------------------------------------------

_v_estimada = 0.0
_w_estimada = 0.0


def _aprender_o_espaco(distancia_cm: float) -> None:
    """Somar esta leitura ao mapa — mas só quando vale a pena somá-la.

    ⚠️ MAPEAR COM A POSIÇÃO ERRADA ESTRAGA O MAPA. Se ela se julga meio metro
    ao lado, desenha a mesma parede duas vezes, meio metro ao lado. Por isso
    só se aprende enquanto a deriva estiver pequena; passado esse ponto ela
    continua a andar, mas deixa de tomar notas — e volta a tomá-las assim que
    um varrimento a puser outra vez no sítio.
    """
    global _proxima_atualizacao_mapa
    if _memoria is None or _piloto is None or not _cfg("mapear", True):
        return
    if _pose.deriva_cm > float(_cfg("deriva_para_mapear", 25)):
        return
    # ⚠️ E — MAIS IMPORTANTE — só se escreve no mapa enquanto a posição ainda
    #    está perto da última CONFIRMADA por um varrimento. A conta da deriva
    #    é otimista por natureza (não sabe da roda que patinou agora); a única
    #    coisa em que se pode confiar é em ter emparelhado com o mapa há pouco
    #    caminho. Sem esta regra, um mapa aprendido com a posição errada fica
    #    guardado no disco e estraga todas as viagens seguintes — aconteceu.
    if _pose.percorrido_cm > float(_cfg("mapear_ate_cm", 150)):
        return
    _memoria.atualizar(_pose.x, _pose.y, _pose.rumo, distancia_cm, _piloto.alcance_cm)
    if time.monotonic() >= _proxima_atualizacao_mapa:
        _aplicar_mapa()


def _comecar_varrimento() -> None:
    global _fase, _varrimento
    _fase = "varrer"
    _varrimento = mod_varrimento.Varrimento(rumo_inicial=_pose.rumo)
    motors.parar()


def _passo_do_varrimento(distancia_cm: float, dt: float) -> Comando:
    """Uma volta lenta sobre si própria, a medir — e no fim, uma decisão."""
    global _fase, _ultima_razao, _ultima_correcao
    assert _varrimento is not None and _piloto is not None and _casa is not None

    if not _varrimento.completo:
        v = float(_cfg("velocidade_varrer", 0.22))
        escala = min(float(_cfg("velocidade_max", 0.45)),
                     float(config.obter("motores.velocidade_max", 0.6)))
        motors.mover(-v * escala, v * escala)
        _atualizar_pose(-v, v, dt)
        _varrimento.juntar(_pose.rumo, distancia_cm)
        _ultima_razao = "a ver onde estou"
        return Comando(-v, v, "a ver onde estou")

    motors.parar()
    correcao = mod_varrimento.emparelhar(
        _casa, _pose.x, _pose.y, _varrimento.amostras, _piloto.alcance_cm
    )
    _ultima_correcao = correcao
    _fase = "conduzir"

    if not correcao.aceite:
        # Ou vê pouco (um quarto vazio devolve poucos ecos), ou o que vê tem
        # mais do que uma explicação (um corredor é igual a si próprio um
        # metro à frente). Nos dois casos, a resposta honesta é perguntar.
        parar()
        _ultima_razao = "perdi-me"
        return Comando(razao="perdi-me", terminou=True)

    # Uma correção que ganhou por pouco vale — mas fica com a incerteza alta,
    # o que faz com que ela volte a verificar dentro de pouco tempo em vez de
    # andar três metros a acreditar nela.
    # ⚠️ COM TETO. Sem ele, uma correção «por pouco» com 6 cm de erro ficava
    #    com 18 cm de incerteza, o gatilho está nos 20, e ela parava para dar
    #    outra volta um segundo e meio depois — a passar a viagem a rodar.
    #    Metade do gatilho garante sempre algum caminho andado entre voltas.
    teto = float(_cfg("deriva_para_varrer", 20)) * 0.5
    resto = min(max(5.0, correcao.erro_cm) * (3.0 if correcao.duvidosa else 1.0), teto)
    _pose.definir(_pose.x + correcao.dx, _pose.y + correcao.dy,
                  _pose.rumo + correcao.drumo, deriva_cm=resto)
    _piloto.reiniciar()
    _aplicar_mapa(forcar=True)
    _ultima_razao = "já sei onde estou"
    return Comando(razao="já sei onde estou")


def _atualizar_pose(esq: float, dir_: float, dt: float) -> None:
    global _v_estimada, _w_estimada
    assert _piloto is not None
    _v_estimada, _w_estimada = _pose.avancar(
        esq, dir_, dt, _piloto.v_max_cm_s, _piloto.entre_eixos_cm
    )


def _feixes(distancia_frente_cm: float) -> list[float]:
    """Traduzir os sensores que existem para os feixes que o piloto espera.

    ⚠️ A Lylla tem HOJE um sensor apontado à frente. Um piloto treinado com
    cinco feixes espera cinco leituras — e o que se faz aos quatro que não
    existem é dizer «não vejo nada ali», que é a mentira menos má: faz o robô
    andar, em vez de o fazer parar para sempre. Mas é uma mentira, e nota-se:
    ele passa ao lado de coisas que não vê. As duas saídas honestas são
    treinar um piloto de UM feixe (na página, o slider dos feixes a 1), ou
    montar mais dois VL53L1X nos cantos. A página deixa comparar os dois.
    """
    assert _piloto is not None
    n = _piloto.n_feixes
    centro = n // 2
    leituras = [_piloto.alcance_cm] * n
    leituras[centro] = min(distancia_frente_cm, _piloto.alcance_cm)
    return leituras


RAIO_CHEGADA_CM = 35.0


def _chegou(x: float, y: float) -> bool:
    """Chegou mesmo — a menos de 35 cm do ponto, dentro da divisão."""
    if _ponto_destino is None:
        return False
    return math.hypot(x - _ponto_destino[0], y - _ponto_destino[1]) <= RAIO_CHEGADA_CM


ARTIGOS = {
    "a":   ("à ",    "ao "),      # vou À sala · vou AO corredor
    "por": ("pela ", "pelo "),    # começo PELA sala · PELO corredor
    "em":  ("na ",   "no "),      # estou NA sala · NO corredor
}


# O que ela diz quando já não sabe onde está. É uma constante porque o
# procurar.py a reconhece: é uma PERGUNTA («em que divisão estou?»), não o fim.
PERDIDA = "I'm not sure where I am. Take me somewhere I know and tell me which room it is."


def em_ingles(nome: str, preposicao: str = "a") -> str:
    """«sala» + «a» → «to the sala» · + «em» → «in the sala».

    A voz é inglesa (o fonemizador da GLaDOS é en-us): tudo o que o robô DIZ
    vai em inglês. O nome da divisão fica como está na planta.
    """
    return {"a": "to the ", "por": "in the ", "em": "in the "}.get(preposicao, "to the ") + nome


def com_artigo(nome: str, preposicao: str = "a") -> str:
    """«sala» + «a» → «à sala» · «corredor» + «por» → «pelo corredor».

    Não é enfeite: um robô que diz «vou a sala» soa a tradução automática, e
    a Lara repara. A regra é a do português de todos os dias — acaba em «a»,
    é feminino — com uma lista curta para o que ela não apanha.
    """
    femininas = ("sala", "cozinha", "casa", "garagem", "varanda", "despensa",
                 "entrada", "suite", "arrecadacao")
    primeira = nome.split()[0].lower()
    fem, masc = ARTIGOS.get(preposicao, ARTIGOS["a"])
    return (fem if primeira.endswith("a") or primeira in femininas else masc) + nome


def _angulo(a: float) -> float:
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a
