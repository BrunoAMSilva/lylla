"""SEGUIR A LARA PELA CASA.

╔══════════════════════════════════════════════════════════════════════════╗
║  O QUE ESTE FICHEIRO É E O QUE NÃO É                                     ║
║                                                                          ║
║  É o CONTROLADOR: dada a posição de um alvo, decide a que velocidade     ║
║  andam as duas rodas. Essa parte está feita e testada, porque é          ║
║  aritmética e dá para testar sem robô nenhum.                            ║
║                                                                          ║
║  NÃO é a perceção. Seguir alguém pela casa não é seguir uma CARA — é     ║
║  seguir umas COSTAS, e o YuNet só encontra caras. Assim que a Lara se    ║
║  vira para andar, o detetor deixa de a ver. A solução (fase 16) é:       ║
║  apanhar a cara uma vez, passar a caixa ao tracker do OpenCV, e voltar   ║
║  a detetar de vez em quando para reconfirmar. Isso precisa do robô real  ║
║  para se afinar; está marcado com TODO.                                  ║
╚══════════════════════════════════════════════════════════════════════════╝

⚠️ LER A SECÇÃO D17 DO PLANO ANTES DE LIGAR ISTO. Há um número que decide
   tudo: a que velocidade os sensores de precipício ainda travam a tempo.
"""

from __future__ import annotations

from dataclasses import dataclass

from robot import config
from robot.hardware import motors, sensors


@dataclass
class Comando:
    """O que fazer neste instante."""

    esquerdo: float = 0.0
    direito: float = 0.0
    razao: str = "parado"

    @property
    def parado(self) -> bool:
        return self.esquerdo == 0.0 and self.direito == 0.0


def _cfg(chave: str, omissao):
    return config.obter(f"seguir.{chave}", omissao)


# ---------------------------------------------------------------------------
# O INTERRUPTOR — ligado pela ação `seguir` do cérebro, ou por um comando
# direto. É só um estado: quem faz alguma coisa com ele é o ciclo principal,
# que chama um_passo() a cada volta enquanto a_seguir() for verdadeiro.
# ---------------------------------------------------------------------------

_a_seguir = False


def permitido() -> bool:
    """O robot.yaml deixa? (`seguir.ativo`, que vem DESLIGADO — ver D17)."""
    return bool(_cfg("ativo", False))


def comecar() -> bool:
    """Liga o modo seguir. Devolve False se a configuração não deixar."""
    global _a_seguir
    if not permitido():
        _a_seguir = False
        return False
    _a_seguir = True
    return True


def parar() -> None:
    """Desliga o modo seguir e para as rodas — sempre, mesmo que já estivesse
    parado. Chamado também pelo "pára" dos comandos diretos."""
    global _a_seguir
    if _a_seguir:
        motors.parar()
    _a_seguir = False


def a_seguir() -> bool:
    return _a_seguir


def calcular(
    x: float | None,
    area: float,
    distancia_cm: float | None = None,
    ha_precipicio: bool = False,
) -> Comando:
    """Do que o robô vê para o que as rodas fazem.

    x       -1 (alvo à esquerda) a +1 (à direita); None = perdi-a
    area    0 a 1, que fatia da imagem o alvo ocupa — serve de distância
    """
    # ── 1 · Vetos. Por esta ordem, e antes de tudo o resto. ────────────────
    #
    # ⚠️ O precipício vem primeiro e não é negociável. Um robô que persegue
    #    uma criança persegue-a até às escadas.
    if ha_precipicio:
        return Comando(0.0, 0.0, "precipício — parei")

    minima = float(config.obter("seguranca.distancia_min_cm", 25))
    if distancia_cm is not None and distancia_cm < minima:
        return Comando(0.0, 0.0, f"obstáculo a {distancia_cm:.0f} cm")

    if x is None:
        return Comando(0.0, 0.0, "perdi-a de vista")

    # ── 2 · Estou perto que chegue? ────────────────────────────────────────
    perto = float(_cfg("area_parar", 0.16))
    longe = float(_cfg("area_seguir", 0.055))
    if area >= perto:
        return Comando(0.0, 0.0, "já estou perto")

    # ── 3 · Velocidade. ───────────────────────────────────────────────────
    #
    # Abranda quando se aproxima, em vez de andar sempre no máximo e travar
    # de repente. Um robô que chega a alguém a abrandar lê-se como cuidadoso;
    # um que chega a toda a velocidade e trava lê-se como descontrolado.
    v_max = float(_cfg("velocidade_max", 0.35))
    if area <= longe:
        avanco = v_max
    else:
        fatia = (perto - area) / max(perto - longe, 1e-6)
        avanco = v_max * max(0.0, min(1.0, fatia))

    # ── 4 · Direção. ──────────────────────────────────────────────────────
    #
    # A zona morta existe para o robô não ficar a corrigir para a esquerda e
    # para a direita à volta do centro. Sem ela, treme.
    morta = float(_cfg("zona_morta", 0.12))
    ganho = float(_cfg("ganho_rotacao", 0.55))
    viragem = 0.0 if abs(x) < morta else ganho * x

    esquerdo = avanco + viragem
    direito = avanco - viragem

    # ⚠️ Normalizar em vez de cortar. Cortar a roda que passa do limite muda
    #    a DIREÇÃO da curva; dividir as duas pelo mesmo fator mantém-na.
    maior = max(abs(esquerdo), abs(direito))
    if maior > v_max:
        esquerdo = esquerdo / maior * v_max
        direito = direito / maior * v_max

    return Comando(esquerdo, direito, f"a seguir (área {area:.0%})")


def um_passo(obs) -> Comando:
    """Uma volta do modo seguir, já com os sensores lidos.

    `obs` é uma attention.Observacao — ou o que vier do tracker, na fase 16.
    """
    if not bool(_cfg("ativo", False)):
        return Comando(0.0, 0.0, "modo seguir desligado")

    x = obs.x if obs.presente else None
    distancia = None if config.a_simular() else sensors.distancia_cm()
    comando = calcular(
        x=x,
        area=obs.area,
        distancia_cm=distancia,
        ha_precipicio=sensors.ha_precipicio(),
    )
    motors.mover(comando.esquerdo, comando.direito)
    return comando


def velocidade_segura_cm_s(
    margem_cm: float = 5.0,
    reacao_s: float = 0.1,
    travagem_m_s2: float = 1.5,
) -> float:
    """A que velocidade os sensores de precipício ainda travam a tempo?

    É a conta que decide se o modo seguir é aceitável numa casa com escadas —
    e a razão de existir a secção D17 do plano.

        margem = velocidade × tempo_de_reação  +  velocidade² / (2 × travagem)
                 └── enquanto não sabe ──┘      └──── enquanto trava ────┘

    Resolvido para a velocidade. Os valores por omissão são o caso real:
    um TCRT5000 no para-choques vê o degrau ~5 cm à frente das rodas, o ciclo
    corre a 10 Hz, e um robô de 2 kg com travagem curta desacelera a ~1,5 m/s².

        margem  5 cm (TCRT5000 no para-choques) →  ~27 cm/s
        margem 30 cm (ToF apontado ao chão)     →  ~81 cm/s

    A conclusão é o desenho todo do modo seguir: **para andar atrás de alguém
    numa casa com escadas é preciso um sensor que olhe PARA A FRENTE, não um
    que olhe para baixo.** Um sensor que vê o degrau onde ele está só serve
    à velocidade da secretária.
    """
    if margem_cm <= 0:
        return 0.0
    margem_m = margem_cm / 100.0
    a = max(travagem_m_s2, 1e-6)
    # v = a · (√(t² + 2·margem/a) − t)
    v = a * ((reacao_s ** 2 + 2 * margem_m / a) ** 0.5 - reacao_s)
    return max(0.0, v * 100.0)
