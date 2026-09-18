"""UMA CONVERSA — os quatro passos de cada vez que alguém fala com o robô.

    ┌────────────┐   ┌──────────────┐   ┌─────────────┐   ┌──────────────┐
    │ 1. OUVIR   │ → │ 2. INTERPRE- │ → │ 3. CONFIRMAR│ → │ 4. EXECUTAR  │
    │            │   │    TAR       │   │             │   │              │
    │ grava até  │   │ o mini trans-│   │ bip + luz   │   │ falar, andar,│
    │ ela se ca- │   │ creve; o Pi  │   │ roxa + «hmm»│   │ seguir, tirar│
    │ lar (luzes │   │ vê se é um   │   │ — antes de  │   │ fotos, apren-│
    │ verde →    │   │ comando dire-│   │ a rede res- │   │ der uma cara │
    │ laranja)   │   │ to; senão o  │   │ ponder      │   │              │
    │            │   │ LLM responde │   │             │   │              │
    └────────────┘   └──────────────┘   └─────────────┘   └──────────────┘
      ouvir()          interpretar()      rotinas "ouvi",   executar()
                                          "a_pensar"

`interpretar()` NÃO mexe no robô: traduz os eventos do mini numa sequência de
PASSOS (dizer isto, fazer esta cara, correr esta rotina, fazer estas ações).
`executar()` é o único que mexe em hardware. Assim cada metade testa-se sem a
outra, e acrescentar uma capacidade nova é acrescentar um tipo de passo.

⚠️ Os passos 2 a 4 sobrepõem-se no tempo, de propósito: a primeira frase toca
   enquanto o mini ainda escreve a segunda. É por isso que o `interpretar()` é
   um gerador e não uma lista — juntar tudo antes de executar era esperar pelo
   LLM inteiro (a armadilha nº 1 do cérebro).

Tudo o que é enfeite (luzes, sons, caras, «hmm») vem das ROTINAS — ver
robot/rotinas.py. Este ficheiro só diz QUANDO; as rotinas dizem O QUÊ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator

from robot import config, rotinas
from robot.brain import cerebro, comandos_diretos, contexto, tools
from robot.brain.state import Estado, Maquina
from robot.hardware import eyes, glow
from robot.voice import frases, listen, speak


@dataclass
class Passo:
    """Uma coisa que o robô tem de fazer. O `tipo` diz qual:

    rotina · cara · frase · direto · acoes · falha · fim
    """

    tipo: str
    texto: str = ""
    audio: bytes | None = None
    nome: str = ""
    acoes: list[dict] = field(default_factory=list)


# ============================================================ 1. OUVIR


@dataclass
class Pedido:
    """O que ela disse, ainda por perceber: áudio a caminho do mini, ou texto
    (em simulação, escrito no teclado)."""

    eventos: Iterable[dict] | None = None     # o turno já em curso no mini
    texto: str | None = None                  # simulação: a frase escrita
    vazio: bool = False                       # ninguém disse nada
    confirma_sozinho: bool = False            # em contínuo o «ouvi» sai do microfone


def ouvir(ctx: dict, cancelar: Callable[[], bool] = lambda: False) -> Pedido:
    """Acende o verde e grava até ela se calar. Em direto, o áudio já vai a
    caminho do mini enquanto ela fala — o turno começa aqui."""
    rotinas.correr("acordar")

    if config.a_simular():
        return Pedido(texto=listen.ouvir())

    if config.obter("cerebro.escutar_em_directo", True):
        # O áudio vai para o mini ENQUANTO ela fala. O `cancelar` é o botão
        # vermelho: bateria crítica, Ctrl+C — o turno acaba sem esperar.
        escuta = listen.escutar_em_directo(ao_progresso=glow.progresso_escuta,
                                           ao_acabar=lambda: rotinas.correr("ouvi"))
        return Pedido(eventos=cerebro.escutar(escuta, contexto=ctx, cancelar=cancelar),
                      confirma_sozinho=True)

    # O caminho em lote: gravar tudo e só depois enviar (ver robot.yaml).
    wav = listen.gravar_wav(ao_progresso=glow.progresso_escuta)
    if wav is None:
        return Pedido(vazio=True)
    return Pedido(eventos=cerebro.turno(wav=wav, contexto=ctx))


# ======================================================= 2. INTERPRETAR


def interpretar(eventos: Iterable[dict]) -> Iterator[Passo]:
    """Os eventos do mini → os passos do robô. Não toca em hardware nenhum.

    ⚠️ Nunca levanta. Seja qual for a forma como o turno corra mal — o mini a
       morrer, um evento estragado, um erro que ninguém previu — sai um passo
       `falha`, e o `executar()` garante que a criança ouve uma explicação.
    """
    try:
        for evento in eventos:
            tipo = evento.get("tipo")

            if tipo == "parcial":
                # Só para o terminal: vê-se o mini a perceber enquanto ela fala.
                print(f"   … «{evento['texto']}»", end="\r", flush=True)

            elif tipo == "ouvido":
                ouvido = evento.get("texto", "")
                print(f"   👤 «{ouvido}»" + " " * 20)
                # Um comando direto não depende do LLM (ver comandos_diretos).
                directa = comandos_diretos.tentar(ouvido)
                if directa is not None:
                    print(f"   ⚡ comando direto → {directa!r}")
                    # ⚠️ Fechar o turno JÁ. Sem isto o mini continuava a pensar
                    #    e escrevia no histórico uma resposta que ninguém ouviu.
                    _fechar(eventos)
                    yield Passo("direto", texto=directa)
                    return

            elif tipo == "a_pensar":
                # Vai ao LLM: é aqui que entra o «hmm». Maior se for pensar a sério.
                yield Passo("rotina", nome="a_pensar_muito" if evento.get("explicar") else "a_pensar")

            elif tipo == "expressao":
                yield Passo("cara", nome=evento["nome"])

            elif tipo == "frase":
                print(f"   🤖 «{evento['texto']}»")
                yield Passo("frase", texto=evento["texto"], audio=evento.get("audio"))

            elif tipo == "resposta":
                for razao in evento.get("recusadas", []):
                    print(f"   ↯ recusei: {razao}")
                for facto in evento.get("lembrar", []) or []:
                    print(f"   🧠 lembrei-me: {facto}")
                if evento.get("acoes"):
                    yield Passo("acoes", acoes=list(evento["acoes"]))

            elif tipo == "fim":
                ms = evento.get("tempo_ms", {})
                if ms.get("primeira_frase"):
                    falou_s = ms.get("fala_s")
                    quanto = f" · ela falou {falou_s} s" if falou_s else ""
                    print(f"   ⏱️  primeira frase {ms['primeira_frase']} ms"
                          f" · turno {ms.get('total')} ms{quanto}")
                yield Passo("fim", nome=evento.get("motivo") or "")
                return
    except cerebro.SemCerebro as erro:
        # ⚠️ A exceção nasce AQUI dentro (o `escutar()` só levanta quando é
        #    consumido), não em quem nos chamou. Quem nos chamou não sabia que
        #    o robô ficou calado — já esteve assim, e emudecia na rede a tossir.
        print(f"⚠️  {erro}")
        yield Passo("falha", nome="sem_cerebro")
    except Exception as erro:  # noqa: BLE001
        # Um áudio estragado (binascii.Error), um evento sem a chave esperada…
        print(f"⚠️  {type(erro).__name__}: {erro}")
        yield Passo("falha", nome="baralhei")


def _fechar(eventos) -> None:
    """Acaba um turno a meio, do lado do robô (fecha o WebSocket)."""
    try:
        eventos.close()
    except Exception:  # noqa: BLE001
        pass


# ========================================================= 4. EXECUTAR


def executar(passos: Iterable[Passo], maquina: Maquina) -> bool:
    """Faz o que os passos pedem. Devolve True (o robô disse sempre alguma coisa).

    ⚠️ SAI SEMPRE COM O ROBÔ A TER DITO ALGUMA COISA. Um robô que se cala sem
       razão parece avariado, e é aí que o projeto morre.
    """
    falou = False
    cara_escolhida = False
    acoes: list[dict] = []

    for passo in passos:
        if passo.tipo == "rotina":
            if not falou:                  # um «hmm» depois da resposta é ruído
                rotinas.correr(passo.nome)

        elif passo.tipo == "cara":
            eyes.expressao(passo.nome)
            cara_escolhida = True

        elif passo.tipo == "frase":
            if not falou:
                falou = True
                # A cara que o cérebro escolheu ganha à do estado.
                maquina.mudar(Estado.A_FALAR, olhos=not cara_escolhida)
                rotinas.correr("a_falar")
            if passo.audio:
                speak.tocar(passo.audio, esperar=False)
            else:
                speak.falar(passo.texto, esperar=False)   # sem TTS no mini: a voz que houver

        elif passo.tipo == "direto":
            if passo.texto:
                speak.falar(passo.texto)
            return True

        elif passo.tipo == "acoes":
            acoes = passo.acoes

        elif passo.tipo == "falha":
            if not falou:
                rotinas.correr("sem_cerebro" if passo.nome == "sem_cerebro" else "nao_ouvi")
                speak.falar(frases.dizer(passo.nome))
            return True

        elif passo.tipo == "fim" and passo.nome == "cancelado":
            return True

    # Sem `and ouvido`: o que interessa é ele NÃO TER DITO NADA. Uma resposta
    # com a fala vazia deixava o robô a executar a ação em silêncio.
    if not falou:
        rotinas.correr("nao_ouvi")
        speak.falar(frases.dizer("nao_percebi"))
        return True

    speak.esperar_acabar()      # as ações vêm DEPOIS da fala, não por cima
    executar_acoes(acoes, maquina)
    return True


def executar_acoes(acoes: list[dict], maquina: Maquina) -> None:
    """Andar, seguir, dançar, aprender uma cara… — o que o cérebro pediu.

    ⚠️ O resultado só se fala quando é uma RECUSA. A fala já veio no JSON;
       dizer outra vez «Andei 20 cm» é o robô a repetir-se. Mas um «não posso,
       está aí uma parede» TEM de sair.
    """
    if not acoes:
        return
    maquina.mudar(Estado.A_AGIR)
    rotinas.correr("a_agir")
    for acao in acoes:
        print(f"   ⚙️  {acao['nome']}({acao['argumentos']})")
        resultado = tools.executar(acao["nome"], acao["argumentos"])
        print(f"      → {resultado}")
        if isinstance(resultado, tools.Recusa):
            speak.falar(resultado)


# ======================================================== tudo junto


def consumir(maquina: Maquina, eventos: Iterable[dict]) -> bool:
    """Passos 2 a 4 de um turno que já está em curso no mini."""
    return executar(interpretar(eventos), maquina)


def uma_interacao(maquina: Maquina, obs=None, cancelar: Callable[[], bool] = lambda: False) -> None:
    """Uma conversa completa: ouvir → interpretar → confirmar → executar."""
    maquina.mudar(Estado.A_OUVIR)
    ctx = contexto.montar(maquina, obs)
    if ctx.get("pessoa"):
        maquina.pessoa = ctx["pessoa"]
        print(f"   👁️  vejo: {ctx['pessoa']}")

    try:
        # 1. OUVIR
        pedido = ouvir(ctx, cancelar)
        if pedido.vazio or (pedido.eventos is None and not pedido.texto):
            if not config.a_simular():
                rotinas.correr("nao_ouvi")
                speak.falar(frases.dizer("nao_ouvi"))
            return

        # 3. CONFIRMAR — já, antes de a rede dizer seja o que for.
        # (Em contínuo ela AINDA está a falar aqui: o «ouvi» sai do microfone
        #  quando ela se calar — ver ouvir().)
        if not pedido.confirma_sozinho:
            maquina.mudar(Estado.A_PENSAR, olhos=False)
            rotinas.correr("ouvi")

        # 2 + 4. INTERPRETAR e EXECUTAR, sobrepostos.
        if pedido.texto is not None:
            eventos = _turno_de_texto(pedido.texto, ctx)
        else:
            eventos = pedido.eventos
        consumir(maquina, eventos)
    except cerebro.SemCerebro as erro:
        print(f"⚠️  {erro}")
        rotinas.correr("sem_cerebro")
        speak.falar(frases.dizer("sem_cerebro"))
    finally:
        rotinas.correr("acabei")
        maquina.mudar(Estado.ATENTO)


def _turno_de_texto(texto: str, ctx: dict) -> Iterator[dict]:
    """Em simulação: a frase escrita faz de «ouvido», e o comando direto é
    verificado ANTES de ir ao mini (não há transcrição à espera)."""
    yield {"tipo": "ouvido", "texto": texto}
    yield from cerebro.turno(texto=texto, contexto=ctx)
