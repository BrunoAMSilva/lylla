"""O BRILHO AZUL — os LEDs de acento da sonda.

O Astro tem partes que brilham a azul. Na nossa versão sonda espacial, o
brilho está onde ele teria pernas: um anel de LEDs na base, que se lê como
os propulsores de uma nave. Mais um anel no peito.

╔══════════════════════════════════════════════════════════════════════════╗
║  PORQUE NÃO USAMOS NEOPIXEL (WS2812)                                     ║
║                                                                          ║
║  Seria a escolha óbvia — LEDs RGB endereçáveis, uma cor qualquer. Mas    ║
║  os WS2812 precisam de temporização a nanossegundos, e no Raspberry Pi 5 ║
║  a biblioteca clássica (rpi_ws281x, que usava DMA e PWM) deixou de       ║
║  funcionar por causa do chip RP1 novo. É o mesmo problema do RPi.GPIO.   ║
║                                                                          ║
║  Como só queremos UMA cor — o azul do Astro — não precisamos de RGB.     ║
║  Usamos LEDs azuis comuns nos canais que sobram do PCA9685 dos motores,  ║
║  que já corre a 1 kHz. Zero chips novos, zero risco de temporização.     ║
║                                                                          ║
║  ⚠️ Tinham de ser os canais do PCA9685 dos MOTORES (1 kHz) e não os dos  ║
║     servos: a 50 Hz os LEDs tremeriam de forma visível.                  ║
╚══════════════════════════════════════════════════════════════════════════╝

⚠️ Cada grupo de LEDs precisa da SUA resistência em série. Sem ela, o LED
   dura uns segundos. Para LEDs azuis (~3,2 V) a 5 V com ~15 mA: 120 Ω.
"""

from __future__ import annotations

import atexit
import math
import threading
import time

from robot import config
from robot.hardware import pca9685

FREQ_HZ = 1000.0
_animacao: threading.Thread | None = None
_parar = threading.Event()
_nivel: dict[str, float] = {}

# O azul do Astro. É o mesmo "ciano" do catálogo do mBot2.
COR = (54, 224, 255)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  AS CORES DA CONVERSA — para uma criança perceber quando pode falar      ║
# ║                                                                          ║
# ║  Só a velocidade do piscar não chega: a Lara não sabe se o robô ainda a  ║
# ║  está a ouvir ou se já foi pensar. Por isso cada momento tem uma cor:    ║
# ║                                                                          ║
# ║    verde    → estou a ouvir, fala à vontade                              ║
# ║    amarelo → laranja  → estás calada há um bocado… vou deixar de ouvir   ║
# ║    roxo     → já não estou a ouvir, estou a pensar                       ║
# ║    ciano    → estou a falar (a cor do Astro)                             ║
# ║    vermelho → alguma coisa correu mal                                    ║
# ║                                                                          ║
# ║  Nos LEDs antigos do PCA9685 (só azuis) a cor não existe: fica o ritmo.  ║
# ╚══════════════════════════════════════════════════════════════════════════╝
VERDE = (0, 255, 70)
AMARELO = (255, 200, 0)
LARANJA = (255, 90, 0)
ROXO = (150, 40, 255)
VERMELHO = (255, 0, 0)
BRANCO = (255, 255, 255)

_NOMES = {VERDE: "verde (a ouvir)", AMARELO: "amarelo", LARANJA: "laranja (quase a parar)",
          ROXO: "roxo (a pensar)", VERMELHO: "vermelho", BRANCO: "branco", COR: "ciano"}

_cor = COR
_escuta = {"fracao": 0.0}     # quanto do silêncio já passou (0 = a falar, 1 = acabou)

# ⚠️ O mBot2 fala por SÉRIE, e as animações escrevem 25 vezes por segundo.
#    Mandar tudo satura a ligação que também leva os comandos das rodas. Só
#    se escreve quando o brilho muda de verdade, e no máximo 10 vezes por
#    segundo — a olho não se distingue.
_PASSO = 0.04
_INTERVALO_S = 0.1
_ultimo_envio = 0.0
_ultimo_nivel = -1.0
_ultima_cor: tuple[int, int, int] | None = None


def _motor() -> str:
    """Quem acende os LEDs: "mbot2" (o shield) ou "pca9685" (o desenho antigo).

    O PCA9685 em 0x40 era o dos motores TB6612, que saiu da construção quando
    o mBot2 ficou inteiro. Os LEDs viviam nos canais que sobravam dele; sem
    essa placa, pedir-lhe brilho dá erro de I2C a cada volta do ciclo.
    """
    return str(config.obter("brilho.motor", "mbot2"))


def _endereco() -> int:
    return int(config.obter("i2c.motores", 0x40))


def _acender_no_mbot2() -> None:
    """Os 5 LEDs do CyberPi seguem o grupo mais aceso.

    São uma tira só — não há "base" e "peito" separados no shield. Enquanto
    não houver LEDs próprios, o mais aceso manda: uma pulsação de atenção no
    peito sobrepõe-se à respiração lenta da base, que é a leitura certa.
    """
    global _ultimo_envio, _ultimo_nivel, _ultima_cor
    from robot import config
    from robot.hardware import mbot2

    # ⚠️ Só ESCREVE numa ligação que já exista; nunca a abre. Isto corre na
    #    thread da animação, e abrir a ligação ao mBot2 fora da principal fica
    #    pendurado sem prazo — ver mbot2.ligar().
    if not (config.a_simular() or mbot2.ja_ligado()):
        return

    nivel = max(_nivel.values(), default=0.0)
    agora = time.monotonic()
    mudou_cor = _cor != _ultima_cor
    if not mudou_cor and abs(nivel - _ultimo_nivel) < _PASSO and nivel not in (0.0, 1.0):
        return
    # ⚠️ Uma mudança de COR passa à frente do limite de 10/s: é ela que diz à
    #    Lara que o robô deixou de ouvir, e não pode chegar 100 ms atrasada.
    if not mudou_cor and agora - _ultimo_envio < _INTERVALO_S:
        return
    _ultimo_envio, _ultimo_nivel, _ultima_cor = agora, nivel, _cor
    mbot2.luz_rgb(*(int(c * nivel) for c in _cor))


def _canais() -> dict:
    """Os grupos de LEDs, definidos no config/robot.yaml."""
    return config.obter("brilho.canais", {}) or {}


def brilho(grupo: str, valor: float) -> None:
    """Acende um grupo de LEDs, de 0.0 (apagado) a 1.0 (máximo).

    >>> brilho("base", 0.6)
    """
    canais = _canais()
    if grupo not in canais:
        disponiveis = ", ".join(sorted(canais)) or "(nenhum definido)"
        raise ValueError(
            f"Não existe o grupo de luz '{grupo}'.\n"
            f"Os que existem são: {disponiveis}\n"
            f"(Estão em config/robot.yaml, secção brilho.canais)"
        )
    valor = max(0.0, min(1.0, float(valor)))
    _nivel[grupo] = valor

    if config.a_simular():
        config.sim(f"brilho {grupo} → {valor * 100:.0f}%")
        return
    if _motor() == "mbot2":
        _acender_no_mbot2()
        return
    if pca9685.iniciar(_endereco(), FREQ_HZ):
        pca9685.duty(_endereco(), int(canais[grupo]), valor)


def cor(rgb: tuple[int, int, int]) -> None:
    """Muda a cor das luzes (só nas que têm cor: os LEDs do CyberPi)."""
    global _cor
    nova = tuple(max(0, min(255, int(c))) for c in rgb)
    if nova != _cor and config.a_simular() and _NOMES.get(nova):
        config.sim(f"luzes → {_NOMES[nova]}")      # só as cores com nome: sem spam
    _cor = nova


def cor_atual() -> tuple[int, int, int]:
    return _cor


def tudo(valor: float) -> None:
    for grupo in _canais():
        brilho(grupo, valor)


def apagar() -> None:
    parar_animacao()
    tudo(0.0)


# ---------------------------------------------------------------------------
# Animações — é isto que faz o robô parecer vivo mesmo parado
# ---------------------------------------------------------------------------

def _ciclo(funcao, periodo: float) -> None:
    inicio = time.monotonic()
    while not _parar.wait(0.04):
        t = (time.monotonic() - inicio) / max(periodo, 0.05)
        try:
            funcao(t)
        except Exception:  # noqa: BLE001
            break


def respirar(grupo: str = "base", periodo: float = 3.5,
             minimo: float = 0.12, maximo: float = 0.55) -> None:
    """Sobe e desce devagar, como uma respiração.

    É o comportamento por omissão quando o robô está parado. Uma luz que
    pulsa devagar lê-se como "vivo mas em repouso"; uma luz fixa lê-se como
    "aparelho ligado".
    """
    parar_animacao()

    def passo(t: float) -> None:
        # Seno deslocado para 0..1
        f = (math.sin(t * 2 * math.pi) + 1) / 2
        brilho(grupo, minimo + f * (maximo - minimo))

    _arrancar(passo, periodo)


def pulsar(grupo: str = "base", periodo: float = 0.6) -> None:
    """Pisca depressa — para quando o robô está a pensar ou a trabalhar."""
    parar_animacao()

    def passo(t: float) -> None:
        f = (math.sin(t * 2 * math.pi) + 1) / 2
        brilho(grupo, 0.15 + f * 0.85)

    _arrancar(passo, periodo)


def _misturar(a, b, f: float) -> tuple[int, int, int]:
    f = max(0.0, min(1.0, f))
    return tuple(int(x + (y - x) * f) for x, y in zip(a, b))


def progresso_escuta(fracao: float) -> None:
    """Chamado pelo microfone a cada 80 ms: 0 = ela está a falar; a subir até
    1 = o silêncio já chegou para acabar a frase. Só muda um número — quem
    pinta é a animação `a_ouvir`, na thread dela."""
    _escuta["fracao"] = max(0.0, min(1.0, float(fracao)))


def ouvir(grupo: str = "base") -> None:
    """Verde enquanto ela fala; amarelo → laranja, e cada vez mais depressa, à
    medida que o silêncio se aproxima do fim da frase. É o relógio que uma
    criança consegue ler: «se ficar laranja, ele vai deixar de me ouvir»."""
    parar_animacao()
    _escuta["fracao"] = 0.0
    cor(VERDE)
    fase = {"t": 0.0, "antes": time.monotonic()}

    def passo(_t: float) -> None:
        f = _escuta["fracao"]
        agora = time.monotonic()
        periodo = 1.4 - 1.1 * f                    # 1,4 s a falar → 0,3 s no fim
        fase["t"] += (agora - fase["antes"]) / periodo
        fase["antes"] = agora
        if f < 0.05:
            cor(VERDE)
        elif f < 0.5:
            cor(_misturar(VERDE, AMARELO, f / 0.5))
        else:
            cor(_misturar(AMARELO, LARANJA, (f - 0.5) / 0.5))
        onda = (math.sin(fase["t"] * 2 * math.pi) + 1) / 2
        brilho(grupo, 0.45 + onda * 0.55)

    _arrancar(passo, 1.0)


def _arrancar(funcao, periodo: float) -> None:
    global _animacao
    _parar.clear()
    _animacao = threading.Thread(target=_ciclo, args=(funcao, periodo), daemon=True)
    _animacao.start()


def parar_animacao() -> None:
    global _animacao
    if _animacao is not None and _animacao.is_alive():
        _parar.set()
        _animacao.join(timeout=0.5)
    _animacao = None
    _parar.clear()


# ---------------------------------------------------------------------------
# Enriquecimentos — as luzes de cada momento da conversa (ver robot/rotinas.py)
# ---------------------------------------------------------------------------

from robot.rotinas import enriquecimento  # noqa: E402


def _sem_luzes() -> bool:
    return not disponivel()


@enriquecimento("luz.a_ouvir")
def _luz_a_ouvir() -> None:
    if not _sem_luzes():
        ouvir("base")


@enriquecimento("luz.a_pensar")
def _luz_a_pensar() -> None:
    if not _sem_luzes():
        cor(ROXO)
        pulsar("base", periodo=0.5)


@enriquecimento("luz.a_falar")
def _luz_a_falar() -> None:
    if not _sem_luzes():
        cor(COR)
        respirar("base", periodo=1.6, minimo=0.45, maximo=0.9)


@enriquecimento("luz.a_agir")
def _luz_a_agir() -> None:
    if not _sem_luzes():
        cor(COR)
        pulsar("base", periodo=1.0)


@enriquecimento("luz.repouso")
def _luz_repouso() -> None:
    if not _sem_luzes():
        cor(COR)
        respirar("base")


@enriquecimento("luz.a_dormir")
def _luz_a_dormir() -> None:
    if not _sem_luzes():
        cor(COR)
        respirar("base", periodo=7.0, minimo=0.03, maximo=0.15)


@enriquecimento("luz.confusa")
def _luz_confusa() -> None:
    if not _sem_luzes():
        cor(LARANJA)
        respirar("base", periodo=1.2, minimo=0.2, maximo=0.8)


@enriquecimento("luz.erro")
def _luz_erro() -> None:
    if not _sem_luzes():
        cor(VERMELHO)
        respirar("base", periodo=2.0, minimo=0.1, maximo=0.7)


@enriquecimento("luz.preparar")
def _luz_preparar() -> None:
    if not _sem_luzes():
        cor(BRANCO)
        pulsar("base", periodo=0.4)


@enriquecimento("luz.boa")
def _luz_boa() -> None:
    if not _sem_luzes():
        parar_animacao()
        cor(VERDE)
        tudo(1.0)


@enriquecimento("luz.ma")
def _luz_ma() -> None:
    if not _sem_luzes():
        parar_animacao()
        cor(VERMELHO)
        tudo(0.8)


@enriquecimento("luz.festa")
def _luz_festa() -> None:
    """Um arco-íris a correr — é a única vez que o robô usa todas as cores."""
    if _sem_luzes():
        return
    parar_animacao()
    cores = (VERMELHO, LARANJA, AMARELO, VERDE, COR, ROXO)

    def passo(t: float) -> None:
        i = t * len(cores)
        cor(_misturar(cores[int(i) % len(cores)], cores[(int(i) + 1) % len(cores)], i % 1))
        brilho("base", 1.0)

    _arrancar(passo, 1.5)


def nivel_atual() -> dict[str, float]:
    return dict(_nivel)


def disponivel() -> bool:
    return bool(_canais())


@atexit.register
def _apagar_ao_sair() -> None:
    try:
        apagar()
    except Exception:  # noqa: BLE001, S110
        pass
