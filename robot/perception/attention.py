"""ATENÇÃO — quem está à frente do robô, dez vezes por segundo.

╔══════════════════════════════════════════════════════════════════════════╗
║  DETETAR MUITO, RECONHECER POUCO                                         ║
║                                                                          ║
║  São duas perguntas diferentes, com preços muito diferentes:             ║
║                                                                          ║
║    "está aqui alguém, e onde?"   → YuNet   ~2-3 ms   (75 856 parâmetros) ║
║    "quem é?"                     → SFace  ~25-35 ms  (~1 M parâmetros)   ║
║                                                                          ║
║  Um robô de secretária precisa da primeira DEZ VEZES POR SEGUNDO — é o   ║
║  que faz os olhos seguirem a pessoa e o que o faz parecer vivo. Da       ║
║  segunda precisa quando alguém CHEGA, e depois só de vez em quando para  ║
║  confirmar.                                                              ║
║                                                                          ║
║  Fazer as duas a 10 fps custaria ~35% de um núcleo. Fazendo só a         ║
║  primeira, e a segunda quando muda alguma coisa, fica em ~12%.           ║
║  É a mesma ideia do ESP32 a desenhar a cara: pôr cada trabalho no        ║
║  sítio certo vale mais do que comprar hardware para o fazer à bruta.     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from robot import config

_ultima_identificacao = 0.0
_nome_atual: str | None = None
_centro_anterior: tuple[float, float] | None = None
_frames_sem_cara = 0
_estava_presente = False

# Contadores para a experiência da fase 9
_ms_detecao: list[float] = []
_ms_reconhecimento: list[float] = []


@dataclass
class Observacao:
    """O que o robô vê neste instante."""

    presente: bool = False
    x: float = 0.0          # -1 = todo à esquerda · +1 = todo à direita
    y: float = 0.0          # -1 = em cima · +1 = em baixo
    area: float = 0.0       # 0 a 1 — que fatia da imagem a cara ocupa
    nome: str | None = None
    chegou_agora: bool = False
    saiu_agora: bool = False
    ms: float = 0.0
    identificou: bool = False
    caras: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def perto(self) -> bool:
        """Encostado ao robô — uma cara grande na imagem."""
        return self.area >= float(config.obter("secretaria.area_perto", 0.10))


def _cfg(chave: str, omissao):
    return config.obter(f"secretaria.{chave}", omissao)


def _resolucao() -> tuple[int, int]:
    valor = _cfg("resolucao_deteccao", [320, 240])
    return int(valor[0]), int(valor[1])


def _deve_identificar(centro: tuple[float, float]) -> bool:
    """Vale a pena gastar os 30 ms do SFace agora?

    Sim em três casos: ainda não sabemos quem é; a cara saltou para outro
    sítio (provavelmente é outra pessoa); ou já passou tempo demais desde a
    última confirmação.
    """
    global _centro_anterior
    agora = time.monotonic()

    if _nome_atual is None:
        return True
    if agora - _ultima_identificacao > float(_cfg("reidentificar_s", 4.0)):
        return True
    if _centro_anterior is not None:
        salto = abs(centro[0] - _centro_anterior[0]) + abs(centro[1] - _centro_anterior[1])
        if salto > float(_cfg("salto_outra_pessoa", 0.35)):
            return True
    return False


def observar() -> Observacao:
    """Um instante de atenção. Barato de propósito — é chamado ~10x/s."""
    global _nome_atual, _ultima_identificacao, _centro_anterior
    global _frames_sem_cara, _estava_presente

    if config.a_simular():
        return Observacao()

    from robot.perception import camera, faces

    t0 = time.perf_counter()
    imagem = camera.tirar_foto()
    if imagem is None:
        return _ausente()

    # Detetar numa imagem pequena. O YuNet cresce com o número de píxeis, e
    # para saber ONDE está uma cara não é preciso resolução nenhuma.
    largura, altura = _resolucao()
    try:
        import cv2

        pequena = cv2.resize(imagem, (largura, altura))
    except Exception:  # noqa: BLE001
        pequena = imagem
        altura, largura = imagem.shape[:2]

    encontradas = faces.detetar(pequena)
    ms_det = (time.perf_counter() - t0) * 1000
    _ms_detecao.append(ms_det)
    del _ms_detecao[:-200]

    if not encontradas:
        return _ausente(ms=ms_det)

    # A cara maior é, quase sempre, quem está a falar connosco.
    maior = max(encontradas, key=lambda c: c[2] * c[3])
    cx = (float(maior[0]) + float(maior[2]) / 2) / largura
    cy = (float(maior[1]) + float(maior[3]) / 2) / altura
    area = (float(maior[2]) * float(maior[3])) / (largura * altura)
    centro = (cx, cy)

    identificou = False
    if _deve_identificar(centro):
        t1 = time.perf_counter()
        # ⚠️ A assinatura sai da imagem GRANDE, não da pequena. Reconhecer
        #    numa cara de 40 px dá vetores instáveis e trocas de identidade.
        escala_x = imagem.shape[1] / largura
        escala_y = imagem.shape[0] / altura
        grande = maior.copy()
        grande[0] *= escala_x
        grande[1] *= escala_y
        grande[2] *= escala_x
        grande[3] *= escala_y
        nome, _ = faces.identificar(faces.assinatura(imagem, grande))
        _nome_atual = nome
        _ultima_identificacao = time.monotonic()
        identificou = True
        _ms_reconhecimento.append((time.perf_counter() - t1) * 1000)
        del _ms_reconhecimento[:-200]

    _centro_anterior = centro
    _frames_sem_cara = 0
    chegou = not _estava_presente
    _estava_presente = True

    return Observacao(
        presente=True,
        x=max(-1.0, min(1.0, (cx - 0.5) * 2)),
        y=max(-1.0, min(1.0, (cy - 0.5) * 2)),
        area=area,
        nome=_nome_atual,
        chegou_agora=chegou,
        ms=(time.perf_counter() - t0) * 1000,
        identificou=identificou,
        caras=len(encontradas),
    )


def _ausente(ms: float = 0.0) -> Observacao:
    """Ninguém à vista — mas só depois de termos a certeza.

    ⚠️ Uma pessoa a virar a cara desaparece do detetor durante uma fração de
       segundo. Sem esta histerese, o robô dizia "olá" outra vez de cada vez
       que a Lara olhasse de lado para o caderno.
    """
    global _frames_sem_cara, _estava_presente, _nome_atual, _centro_anterior

    _frames_sem_cara += 1
    limite = int(_cfg("frames_para_ausencia", 8))
    if _frames_sem_cara < limite:
        return Observacao(presente=False, nome=_nome_atual, ms=ms)

    saiu = _estava_presente
    _estava_presente = False
    _nome_atual = None
    _centro_anterior = None
    return Observacao(presente=False, saiu_agora=saiu, ms=ms)


def esquecer() -> None:
    """Reinicia a atenção. Usado nos testes e ao mudar de modo."""
    global _nome_atual, _ultima_identificacao, _centro_anterior
    global _frames_sem_cara, _estava_presente
    _nome_atual = None
    _ultima_identificacao = 0.0
    _centro_anterior = None
    _frames_sem_cara = 0
    _estava_presente = False


def custo() -> dict:
    """Quanto está a custar isto, em milissegundos e em fatia de um núcleo.

    É o número que interessa para decidir se vale a pena um acelerador de IA
    (secção D8b do plano). Mostra-o com `python scripts/test_attention.py`.
    """
    def media(v):
        return sum(v) / len(v) if v else 0.0

    det = media(_ms_detecao)
    rec = media(_ms_reconhecimento)
    fps = float(_cfg("fps_deteccao", 10))
    intervalo = 1.0 / max(fps, 0.1)
    seg = max(float(_cfg("reidentificar_s", 4.0)), 0.1)
    fracao = (det / 1000 / intervalo) + (rec / 1000 / seg)
    return {
        "deteccao_ms": round(det, 2),
        "reconhecimento_ms": round(rec, 2),
        "fps_alvo": fps,
        "fracao_de_um_nucleo": round(fracao, 3),
        "watts_estimados": round(fracao * 1.75, 2),  # ~1,75 W por núcleo A76
        "amostras": len(_ms_detecao),
    }
