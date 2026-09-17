"""O mBot2 INTEIRO, comandado pelo Pi por um cabo USB.

O mBot2 não foi canibalizado: o shield e o CyberPi ficam onde estão, ligados
por um cabo USB ao Pi, e este módulo fala com eles. Ganhamos os encoders
contados em hardware, a malha fechada de velocidade e o giroscópio — sem
cortar um único cabo.

    from robot.hardware import mbot2
    mbot2.velocidade(43, 43)      # RPM em cada roda
    mbot2.andados_cm()            # (esquerda, direita) desde o último zero
    mbot2.parar()

⚠️ ISTO NÃO É A CAMADA DA LARA. Ela usa o `lylla.py`, na raiz do projeto.

╔══════════════════════════════════════════════════════════════════════════╗
║  AS DUAS VELOCIDADES DESTA LIGAÇÃO — é o que decide o desenho todo       ║
║                                                                          ║
║  PEDIR custa caro: cada ida-e-volta é 51 ms (só ao CyberPi) ou 102 ms    ║
║  (se atravessar o shield). Medido, não estimado.                        ║
║                                                                          ║
║  SUBSCREVER é de borla: pede-se UMA vez ao CyberPi que empurre um valor  ║
║  sozinho, e a partir daí ler custa ~0 ms e 0% de CPU.                   ║
║                                                                          ║
║  Por isso tudo o que se lê muitas vezes — os dois encoders, a distância, ║
║  o giroscópio — é subscrito no arranque. Só os COMANDOS custam, e o      ║
║  `drive_speed` manda nos dois motores de uma vez (61 ms, não 122).      ║
║                                                                          ║
║  E como o `EM_set_speed` é malha fechada DENTRO do shield, a velocidade  ║
║  mantém-se sem ser reenviada: o ciclo não precisa de um comando por      ║
║  passo, só quando há correção a fazer.                                  ║
╚══════════════════════════════════════════════════════════════════════════╝

⚠️ SEGURANÇA: a paragem atual usa este cabo USB. O corte físico de movimento
   com o mBot2 intacto ainda precisa de ser desenhado e testado. Até lá, os
   ensaios de movimento exigem um adulto junto ao robô e acesso à alimentação.

⚠️ Armadilhas da biblioteca `makeblock`, todas verificadas no hardware:
   1. `import makeblock` abre sozinho a primeira porta CH340 que encontrar e
      faz o aperto de mão. Abrir uma SEGUNDA ligação à mesma porta põe duas
      threads a repartir os bytes e ninguém recebe resposta inteira — é por
      isso que `_ja_ligado()` reaproveita a ligação do import.
   2. Sem nenhuma porta CH340 o import rebenta a meio (AttributeError).
      Os submódulos sobrevivem em `sys.modules`; o nome `makeblock` não.
   3. `CyberPi.connect()` fica pendurado para sempre se não houver resposta.
   4. O Ctrl+C da biblioteca fecha as portas e sai com os motores a rodar.
   5. A primeira leitura de uma subscrição devolve 0 — o marcador, não o valor.
"""

from __future__ import annotations

import atexit
import os
import signal
import sys
import threading
import time

from robot import config

# ---------------------------------------------------------------------------
# Estado do módulo
# ---------------------------------------------------------------------------
_api = None                      # o módulo de API da biblioteca, já ligado
_dev = None                      # a porta série (para a fechar à saída)
_ligado = False
_tentou_ligar = False
_subs: dict[str, object] = {}    # subscrições vivas, por nome
_lock = threading.Lock()         # os comandos não se atropelam entre threads
_ultimo_comando: tuple[float, float] | None = None

RPM_MAXIMO_ABSOLUTO = 200.0      # limite do próprio shield


class Prazo(Exception):
    """O despertador tocou antes de a chamada voltar."""


def _com_prazo(segundos: float, funcao, *args):
    """Corre `funcao` com despertador — só na thread principal.

    O `connect()` da biblioteca espera pelo `protocol.ready` num ciclo sem
    saída. Um robô que fica pendurado a arrancar é pior do que um robô que diz
    que não conseguiu.
    """
    if threading.current_thread() is not threading.main_thread():
        return funcao(*args)

    def _toca(_s, _f):
        raise Prazo()

    anterior = signal.signal(signal.SIGALRM, _toca)
    signal.setitimer(signal.ITIMER_REAL, segundos)
    try:
        return funcao(*args)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, anterior)


def _porta() -> str:
    """A porta do CyberPi. Por omissão, a primeira `by-id` que apareça.

    O by-id não troca de nome entre arranques. A placa ESP32 antiga pode também
    aparecer como ttyUSB. O conversor USB-série ainda precisa de ser
    identificado antes de a ligar ao lado do CyberPi.
    """
    escolhida = config.obter("mbot2.porta", "")
    if escolhida:
        return str(escolhida)
    import glob

    porta_da_cara = str(config.obter("cara.porta", "") or "")
    candidatas = sorted(glob.glob("/dev/serial/by-id/*")) or sorted(glob.glob("/dev/ttyUSB*"))
    for porta in candidatas:
        if porta_da_cara and os.path.realpath(porta) == os.path.realpath(porta_da_cara):
            continue          # essa é a cara, não é o mBot2
        return porta
    return candidatas[0] if candidatas else ""


def _ja_ligado(porta: str):
    """A ligação que o `import makeblock` já fez sozinho (armadilha 1)."""
    api = sys.modules.get("makeblock.modules.cyberpi.api_cyberpi_api")
    if api is None or getattr(api, "module_auto", None) is None:
        return None, None
    board = getattr(api.module_auto, "_board", None)
    dev = getattr(board, "_dev", None) if board is not None else None
    aberta = getattr(getattr(dev, "_ser", None), "port", None)
    if not aberta:
        return None, None
    if porta and os.path.realpath(aberta) != os.path.realpath(porta):
        try:
            dev.exit()        # agarrou a porta errada (a cara, por exemplo)
        except Exception:  # noqa: BLE001
            pass
        return None, None
    return api, dev


def ja_ligado() -> bool:
    """Já estamos ligados? NÃO tenta ligar — ao contrário do `disponivel()`.

    É para quem corre fora da thread principal (as animações das luzes, por
    exemplo) e só quer usar a ligação se ela já existir.
    """
    return _ligado


def ligar() -> bool:
    """Liga-se ao mBot2 e subscreve o que é preciso ler muitas vezes.

    Chamar isto muitas vezes não faz mal: só liga na primeira.
    """
    global _api, _dev, _ligado, _tentou_ligar
    if _ligado:
        return True
    if _tentou_ligar and not _ligado:
        return False

    # ⚠️ A PRIMEIRA LIGAÇÃO É SÓ NA THREAD PRINCIPAL.
    #    O `connect()` da biblioteca espera pelo `protocol.ready` num ciclo sem
    #    saída, e o despertador do `_com_prazo` é SIGALRM — que só funciona na
    #    thread principal. Fora dela não há prazo nenhum: o programa fica
    #    pendurado para sempre, sem erro e sem linha nenhuma no terminal.
    #    Aconteceu: a animação das luzes tocou aqui no arranque e o robô
    #    congelou logo a seguir aos braços.
    if threading.current_thread() is not threading.main_thread():
        return False

    _tentou_ligar = True

    if config.a_simular():
        config.sim("mBot2 → ligação simulada")
        _ligado = True
        return True

    porta = _porta()
    if not porta:
        print("⚠️  mBot2: nenhuma porta série à vista. O cabo USB está ligado?")
        return False

    try:
        import makeblock  # noqa: F401, PLC0415
    except ImportError:
        print("⚠️  mBot2: falta a biblioteca — pip install makeblock pyserial")
        return False
    except Exception:  # noqa: BLE001
        pass          # armadilha 2: rebenta sem porta CH340, mas deixa rasto útil

    _api, _dev = _ja_ligado(porta)
    if _api is None:
        cyberpi = sys.modules.get("makeblock.boards.cyberpi")
        porta_mod = sys.modules.get("makeblock.comm.SerialPort")
        if cyberpi is None or porta_mod is None:
            print("⚠️  mBot2: a biblioteca não carregou.")
            return False
        try:
            _dev = porta_mod.SerialPort(porta, 115200)
            _api = _com_prazo(float(config.obter("mbot2.espera_s", 20.0)),
                              cyberpi.connect, _dev)
        except Prazo:
            print(f"⚠️  mBot2: {porta} não respondeu. Está aceso e no menu?")
            return False
        except Exception as erro:  # noqa: BLE001
            print(f"⚠️  mBot2: não deu para ligar ({erro})")
            return False

    _ligado = True
    _subscrever_tudo()
    return True


def disponivel() -> bool:
    return _ligado or ligar()


# ---------------------------------------------------------------------------
# Subscrições — o que se lê muitas vezes não se pede, espera-se
# ---------------------------------------------------------------------------
def _subscrever(nome: str, funcao: str, paras: str) -> None:
    """Pede ao CyberPi que empurre um valor sozinho, para sempre."""
    if config.a_simular() or _api is None:
        return
    try:
        from makeblock.protocols.PackData import HalocodePackData  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        modulo = sys.modules.get("makeblock.protocols.PackData")
        if modulo is None:
            return
        HalocodePackData = modulo.HalocodePackData  # noqa: N806

    try:
        modulo = _api.module_auto
        pack = HalocodePackData()
        pack.type = HalocodePackData.TYPE_SCRIPT
        pack.mode = HalocodePackData.TYPE_RUN_WITH_RESPONSE
        pack.script = f"subscribe.add_item({{0}}, {funcao}, {paras})"
        pack.on_response = modulo.common_subscribe_response_cb
        modulo.subscribe(pack)
        modulo.wait_respond(pack, 2)
        _subs[nome] = pack
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  mBot2: não deu para subscrever {nome} ({erro})")


def _subscrever_tudo() -> None:
    _subscrever("EM1", "cyberpi.mbot2.EM_get_angle", "('EM1',)")
    _subscrever("EM2", "cyberpi.mbot2.EM_get_angle", "('EM2',)")
    _subscrever("rotacao", "cyberpi.get_rotation", "('z',)")
    if _api is not None:
        try:
            _api.ultrasonic2.get()     # esta a biblioteca já subscreve sozinha
        except Exception:  # noqa: BLE001
            pass


def _subscrito(nome: str, omissao: float = 0.0) -> float:
    pack = _subs.get(nome)
    if pack is None:
        return omissao
    valor = getattr(pack, "subscribe_value", omissao)
    return float(valor) if isinstance(valor, (int, float)) else omissao


# ---------------------------------------------------------------------------
# As rodas
# ---------------------------------------------------------------------------
def _diametro_cm() -> float:
    return float(config.obter("mbot2.diametro_roda_cm", 8.0))


def _perimetro_cm() -> float:
    return 3.14159265 * _diametro_cm()


def cms_para_rpm(cm_por_s: float) -> float:
    """18 cm/s são 43 RPM em rodas de 8 cm. A conta é esta."""
    return cm_por_s * 60.0 / _perimetro_cm()


def rpm_para_cms(rpm: float) -> float:
    return rpm * _perimetro_cm() / 60.0


def _limitar_rpm(rpm: float) -> float:
    teto = min(float(config.obter("mbot2.rpm_max", 120.0)), RPM_MAXIMO_ABSOLUTO)
    return max(-teto, min(teto, float(rpm)))


def velocidade(esquerda_rpm: float, direita_rpm: float) -> None:
    """Manda as duas rodas de uma vez (61 ms — metade de dois comandos).

    A velocidade FICA. O shield mantém-na em malha fechada até alguém mandar
    outra coisa; não é preciso reenviar isto num ciclo.
    """
    global _ultimo_comando
    if config.a_simular():
        _sim_integrar()          # fecha a conta do comando anterior
    esquerda_rpm = _limitar_rpm(esquerda_rpm)
    direita_rpm = _limitar_rpm(direita_rpm)
    _ultimo_comando = (esquerda_rpm, direita_rpm)

    if config.a_simular():
        config.sim(f"mBot2 → esq={esquerda_rpm:+.0f} RPM dir={direita_rpm:+.0f} RPM")
        return
    if not disponivel():
        return
    with _lock:
        try:
            # ⚠️ a EM2 está montada em espelho: para andar para a frente as
            # duas rodas têm de girar em sentidos opostos.
            sinal = -1.0 if config.obter("mbot2.inverter_direita", False) else 1.0
            _api.mbot2.drive_speed(esquerda_rpm, sinal * direita_rpm)
        except Exception as erro:  # noqa: BLE001
            print(f"⚠️  mBot2: comando falhou ({erro})")


def parar() -> None:
    global _ultimo_comando
    if config.a_simular():
        _sim_integrar()
        _ultimo_comando = (0.0, 0.0)
        config.sim("mBot2 → parar")
        return
    _ultimo_comando = (0.0, 0.0)
    if not _ligado:
        return
    with _lock:
        try:
            _api.mbot2.EM_stop("all")
        except Exception:  # noqa: BLE001
            pass


def travar(sim: bool = True) -> None:
    """Trava os motores na posição (útil numa rampa). Não é travagem de emergência."""
    if config.a_simular():
        config.sim(f"mBot2 → travar={sim}")
        return
    if not disponivel():
        return
    with _lock:
        try:
            _api.mbot2.EM_lock(bool(sim), "all")
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# O que as rodas já andaram — de graça, porque está subscrito
# ---------------------------------------------------------------------------
_zero = [0.0, 0.0]
_zero_rotacao = 0.0

# Em simulação não há encoders — mas a Lara aprende no Mac, e uma lição que só
# funciona com o robô ligado é meia lição. Por isso o modo simulação integra a
# velocidade no tempo e mantém um conta-quilómetros de mentira que se comporta
# como o verdadeiro.
_sim_cm = [0.0, 0.0]
_sim_desde = time.monotonic()
ENTRE_RODAS_CM = 12.5      # aproximado, e só serve para a conta da rotação


def _sim_integrar() -> None:
    """Soma ao conta-quilómetros simulado o que andou desde a última vez."""
    global _sim_desde
    agora = time.monotonic()
    decorrido = agora - _sim_desde
    _sim_desde = agora
    if _ultimo_comando is None:
        return
    esq_rpm, dir_rpm = _ultimo_comando
    _sim_cm[0] += rpm_para_cms(esq_rpm) * decorrido
    _sim_cm[1] += rpm_para_cms(dir_rpm) * decorrido


def angulos() -> tuple[float, float]:
    """Graus de cada encoder desde o último `zerar()`.

    É um CONTADOR acumulado, não uma amostra: ler devagar não perde distância
    nenhuma, porque o que ele andou pelo meio está dentro do número.
    """
    if config.a_simular():
        _sim_integrar()
        por_grau = _perimetro_cm() / 360.0
        return (_sim_cm[0] / por_grau, _sim_cm[1] / por_grau)
    return (_subscrito("EM1") - _zero[0], _subscrito("EM2") - _zero[1])


def andados_cm() -> tuple[float, float]:
    """A mesma coisa em centímetros. ~0,64 mm por grau em rodas de 8 cm."""
    g1, g2 = angulos()
    por_grau = _perimetro_cm() / 360.0
    if config.a_simular():
        return (g1 * por_grau, g2 * por_grau)
    sinal = -1.0 if config.obter("mbot2.inverter_direita", False) else 1.0
    return (g1 * por_grau, g2 * por_grau * sinal)


def andado_cm() -> float:
    """Quanto o robô andou, em média das duas rodas (com sinal)."""
    esq, dir_ = andados_cm()
    return (esq + dir_) / 2.0


def progresso_cm() -> float:
    """Quanto as rodas andaram, sem olhar ao sentido.

    ⚠️ Isto existe por segurança, e a razão é boa: se o `inverter_direita`
    estiver ao contrário, as duas rodas cancelam-se na média com sinal e o
    `andado_cm()` fica sempre perto de zero. Um ciclo que espere por ele nunca
    mais pára — e o robô anda até bater. A magnitude não tem esse problema.
    """
    esq, dir_ = andados_cm()
    return (abs(esq) + abs(dir_)) / 2.0


def rodas_concordam() -> bool:
    """As duas rodas andaram no mesmo sentido?

    Em linha reta têm de concordar. Se não concordam, ou o robô está a rodar
    no sítio, ou o `mbot2.inverter_direita` do robot.yaml está ao contrário.
    """
    esq, dir_ = andados_cm()
    if abs(esq) < 1.0 or abs(dir_) < 1.0:
        return True                      # ainda não andou o suficiente para julgar
    return (esq > 0) == (dir_ > 0)


def zerar() -> None:
    """Põe os contadores a zero — sem pedir nada ao shield.

    Guarda-se a leitura atual e subtrai-se: um `EM_reset_angle` custava 61 ms
    e podia perder passos entre o pedido e a resposta.
    """
    global _zero_rotacao
    if config.a_simular():
        _sim_integrar()
        _sim_cm[0] = _sim_cm[1] = 0.0
        return
    _zero[0] = _subscrito("EM1")
    _zero[1] = _subscrito("EM2")
    _zero_rotacao = _subscrito("rotacao")


def rodou_graus() -> float:
    """Quanto o robô rodou sobre si próprio, pelo GIROSCÓPIO do CyberPi.

    Vale mais do que a conta pelas rodas: não conta o que escorrega.
    """
    if config.a_simular():
        _sim_integrar()
        arco = (_sim_cm[0] - _sim_cm[1]) / 2.0   # direita = positivo
        return arco / (3.14159265 * ENTRE_RODAS_CM) * 360.0
    return _subscrito("rotacao") - _zero_rotacao


def distancia_cm() -> float:
    """Os ultrassons do mBot2 (5 a 300 cm). 300 = não vê nada à frente."""
    if config.a_simular():
        return 100.0
    if not disponivel():
        return 300.0
    try:
        return float(_api.ultrasonic2.get())
    except Exception:  # noqa: BLE001
        return 300.0


# ---------------------------------------------------------------------------
# As luzes que o mBot2 já tem
# ---------------------------------------------------------------------------
EMOCOES = {
    "feliz": "happy",
    "piscar": "wink",
    "a_pensar": "thinking",
    "tonto": "dizzy",
    "a_dormir": "sleepy",
}


def olhos(emocao: str) -> bool:
    """Os 8 LEDs azuis dos ultrassons — os «olhos» que o mBot2 já traz.

    Devolve True se a emoção existe aqui. A animação corre DENTRO do módulo,
    por isso é fluida; animar isto a partir do Pi, a 60 ms por comando, não
    seria. É o mesmo argumento que pôs a cara no ESP32.
    """
    nome = EMOCOES.get(emocao)
    if nome is None:
        return False
    if config.a_simular():
        config.sim(f"mBot2 → olhos '{emocao}'")
        return True
    if not disponivel():
        return False
    with _lock:
        try:
            _api.ultrasonic2.play(nome)
            return True
        except Exception:  # noqa: BLE001
            return False


def brilho_olhos(brilho: int = 100, qual: object = "all") -> None:
    """Brilho de 0 a 100, num LED (1 a 8) ou em todos."""
    if config.a_simular():
        config.sim(f"mBot2 → brilho olhos {brilho} ({qual})")
        return
    if not disponivel():
        return
    with _lock:
        try:
            _api.ultrasonic2.set_bri(max(0, min(100, int(brilho))), qual)
        except Exception:  # noqa: BLE001
            pass


CORES = {
    "vermelho": (255, 0, 0), "verde": (0, 255, 0), "azul": (0, 0, 255),
    "amarelo": (255, 200, 0), "roxo": (160, 0, 255), "branco": (255, 255, 255),
    "ciano": (54, 224, 255), "laranja": (255, 90, 0), "rosa": (255, 60, 140),
}


def luz_rgb(r: int, g: int, b: int) -> bool:
    """Os 5 LEDs RGB do CyberPi, com a cor exata. 0-255 em cada componente.

    É o que o `glow` usa para as animações: o brilho é a mesma cor com os
    componentes escalados, e não há `led.brightness` nesta API.
    """
    r, g, b = (max(0, min(255, int(v))) for v in (r, g, b))
    if config.a_simular():
        config.sim(f"mBot2 → luz rgb({r},{g},{b})")
        return True
    if not disponivel():
        return False
    with _lock:
        try:
            if (r, g, b) == (0, 0, 0):
                _api.led.off("all")
            else:
                _api.led.on(r, g, b, "all")
            return True
        except Exception:  # noqa: BLE001
            return False


def luz(cor: str = "ciano") -> bool:
    """Os 5 LEDs RGB do CyberPi. `luz("apagar")` desliga-os."""
    if cor in ("apagar", "apagado", "nenhuma"):
        if config.a_simular():
            config.sim("mBot2 → luz apagada")
            return True
        if not disponivel():
            return False
        with _lock:
            try:
                _api.led.off("all")
                return True
            except Exception:  # noqa: BLE001
                return False

    rgb = CORES.get(cor)
    if rgb is None:
        return False
    if config.a_simular():
        config.sim(f"mBot2 → luz {cor}")
        return True
    if not disponivel():
        return False
    with _lock:
        try:
            _api.led.on(rgb[0], rgb[1], rgb[2], "all")
            return True
        except Exception:  # noqa: BLE001
            return False


# ---------------------------------------------------------------------------
def estado() -> dict[str, object]:
    """Um retrato para o `check_health.py` e para o cérebro."""
    if config.a_simular():
        return {"ligado": True, "simulado": True}
    if not _ligado:
        return {"ligado": False}
    esq, dir_ = andados_cm()
    return {
        "ligado": True,
        "simulado": False,
        "bateria": _pedir(lambda: _api.get_battery()),
        "andado_esq_cm": round(esq, 1),
        "andado_dir_cm": round(dir_, 1),
        "rodou_graus": round(rodou_graus(), 1),
        "distancia_cm": distancia_cm(),
        "ultimo_comando_rpm": _ultimo_comando,
        "subscricoes": sorted(_subs),
    }


def _pedir(funcao, omissao=None):
    try:
        return funcao()
    except Exception:  # noqa: BLE001
        return omissao


@atexit.register
def _parar_ao_sair() -> None:
    """PARAR SEMPRE — e fechar a porta, que a thread da biblioteca não é daemon."""
    try:
        parar()
    except Exception:  # noqa: BLE001, S110
        pass
    try:
        if _dev is not None:
            _dev.exit()
    except Exception:  # noqa: BLE001, S110
        pass
