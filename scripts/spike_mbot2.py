#!/usr/bin/env python3
"""SPIKE — falar com o mBot2 pelo cabo USB, sem cortar nada.

    python scripts/spike_mbot2.py                  # só mede, nada se mexe
    python scripts/spike_mbot2.py --com-motores    # ⚠️ as rodas rodam
    python scripts/spike_mbot2.py --servo S1       # varre um servo na porta S1
    python scripts/spike_mbot2.py --porta /dev/serial/by-id/usb-...

Isto NÃO é código do robô: é uma experiência para responder a uma pergunta.
Vale a pena manter o mBot2 INTEIRO — shield + CyberPi ligados ao Pi por um cabo
USB — em vez de o canibalizar? A resposta depende de números que não estão na
documentação (a latência de cada tipo de chamada), e é isso que isto mede.

O que se ganha, se as contas derem: os encoders contados EM HARDWARE pelo
shield (o `EM_get_angle` devolve graus), que é o ponto (1) da lista do
docs/navegacao.md, sem esperar pelo ESP32; e o `EM_set_speed` em malha fechada,
que torna o `compensacao_esq`/`compensacao_dir` do robot.yaml desnecessário.

O QUE ESTÁ A ACONTECER POR BAIXO
────────────────────────────────────────────────────────────────────────────
O pacote `makeblock` não fala um protocolo de robô: empurra linhas de
MicroPython pelo canal de script do firmware do CyberPi e lê o que devolvem.
Há DOIS tipos de chamada, e a diferença entre eles é a decisão toda:

  · PEDIDO    (mbot2.*, EM_get_angle, servo_set) — ida-e-volta bloqueante.
  · SUBSCRIÇÃO (ultrasonic2.get) — instala um `subscribe.add_item` no CyberPi,
    que passa a EMPURRAR o valor sozinho. A leitura sai de uma cache local e
    quase não custa nada.

Três detalhes do pacote que explicam o chão da latência (lidos no código dele):
  · quem espera pela resposta acorda de 10 em 10 ms;
  · o envio é feito por uma thread que só esvazia a fila entre leituras da
    série, e essas leituras têm timeout de 10 ms;
  · essa mesma thread lê a série BYTE A BYTE em Python — a 115200 baud isso é
    CPU, e o Pi tem um orçamento apertado (ver `secretaria.fps_deteccao`).
    Por isso este script também mede quanto CPU custa manter uma subscrição.

⚠️  QUATRO ARMADILHAS DO PACOTE, todas verificadas a correr o código dele
  1. `import makeblock` PODE ABRIR UMA PORTA SÉRIE SOZINHO: procura a primeira
     porta com chip CH340 e liga-se-lhe. O ESP32 da cara costuma ser CH340
     também. **Faz este teste com o ESP32 desligado do Pi**, senão arriscas que
     a biblioteca fique agarrada à porta da cara.
  2. E se NÃO houver nenhuma porta CH340, o próprio `import makeblock` REBENTA
     com um `AttributeError: '__CyberPi' object has no attribute '_protocol'`.
     Não é o teu código: é a biblioteca a tentar falar por uma porta que não
     abriu. O truque está no `importar()` aqui em baixo — depois do import
     falhado, os submódulos que interessam ficam vivos em `sys.modules`.
  3. `CyberPi.connect()` FICA PENDURADO PARA SEMPRE se o CyberPi não responder
     (espera pelo `protocol.ready` num ciclo sem saída). Por isso a ligação é
     feita com despertador — um script que não volta é pior do que um erro.
  4. O pacote instala o SEU PRÓPRIO handler de Ctrl+C, que fecha as portas e
     sai — deixando os motores a rodar. Este script volta a instalar o dele
     DEPOIS do import e manda parar antes de sair. Mesmo assim: a paragem de
     emergência nunca é a série, é o botão DPST.
"""

from __future__ import annotations

import argparse
import glob
import os
import signal
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LARGURA = 74


# ─────────────────────────────────────────────────────────────────────────────
# apresentação
# ─────────────────────────────────────────────────────────────────────────────
def titulo(texto: str) -> None:
    print("\n" + "═" * LARGURA)
    print(f"  {texto}")
    print("═" * LARGURA)


def seccao(texto: str) -> None:
    print(f"\n▶ {texto}")


def ok(texto: str) -> None:
    print(f"  ✓ {texto}")


def aviso(texto: str) -> None:
    print(f"  ⚠️  {texto}")


def falhou(texto: str) -> None:
    print(f"  ✗ {texto}")


def percentis(ms: list[float]) -> tuple[float, float, float]:
    """p50, p90 e máximo. Sem numpy — são 30 amostras, não 30 milhões."""
    if not ms:
        return (0.0, 0.0, 0.0)
    ordenado = sorted(ms)
    p50 = statistics.median(ordenado)
    p90 = ordenado[min(len(ordenado) - 1, int(len(ordenado) * 0.9))]
    return (p50, p90, max(ordenado))


def cronometrar(n: int, funcao, nome: str) -> list[float]:
    """Corre `funcao` n vezes e devolve os tempos em ms.

    ⚠️ Cronometrar só o que se quer medir: a primeira chamada de uma subscrição
    inclui a instalação dela no CyberPi e NÃO entra na mesma conta que as
    seguintes — por isso é devolvida à parte por quem chama.
    """
    tempos: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            funcao()
        except Exception as erro:  # noqa: BLE001
            falhou(f"{nome}: {erro}")
            return tempos
        tempos.append((time.perf_counter() - t0) * 1000.0)
    return tempos


def relatar(nome: str, ms: list[float], n_esperado: int) -> float:
    if len(ms) < n_esperado:
        falhou(f"{nome}: só {len(ms)}/{n_esperado} chamadas")
    if not ms:
        return 0.0
    p50, p90, maximo = percentis(ms)
    print(f"  {nome:<34} p50 {p50:7.1f} ms   p90 {p90:7.1f} ms   máx {maximo:7.1f} ms")
    return p50


# ─────────────────────────────────────────────────────────────────────────────
# a porta série
# ─────────────────────────────────────────────────────────────────────────────
def porta_da_cara() -> str | None:
    """A porta do ESP32, para avisar se for a mesma. Falha em silêncio."""
    try:
        from robot import config  # noqa: PLC0415

        return str(config.obter("cara.porta", ""))
    except Exception:  # noqa: BLE001
        return None


def candidatas() -> list[str]:
    """Portas por ordem de preferência: by-id primeiro, porque é estável.

    /dev/ttyUSB0 troca de número conforme a ordem em que as coisas arrancam.
    Com dois aparelhos na série (ESP32 da cara + CyberPi) isso não é um
    pormenor: é o robô a mandar expressões para os motores.

    ⚠️ O by-id é um atalho para o /dev/ttyUSBx — são NOMES do mesmo aparelho,
    não aparelhos diferentes. Contá-los duas vezes dava um aviso falso de
    "há mais do que uma porta", por isso a lista é reduzida por destino real.
    """
    brutas = sorted(glob.glob("/dev/serial/by-id/*"))
    brutas += sorted(glob.glob("/dev/ttyUSB*")) + sorted(glob.glob("/dev/ttyACM*"))
    brutas += sorted(glob.glob("/dev/cu.usbserial*")) + sorted(glob.glob("/dev/cu.wchusbserial*"))

    vistas: set[str] = set()
    portas: list[str] = []
    for porta in brutas:
        real = os.path.realpath(porta)
        if real in vistas:
            continue
        vistas.add(real)
        portas.append(porta)
    return portas


def escolher_porta(pedida: str | None) -> str | None:
    seccao("portas série visíveis")
    lista = candidatas()
    if not lista:
        falhou("nenhuma. O CyberPi está ligado por USB e aceso?")
        return None

    cara = porta_da_cara()
    for porta in lista:
        real = os.path.realpath(porta)
        marca = ""
        if cara and (porta == cara or real == os.path.realpath(cara)):
            marca = "   ← é o NOME que o robot.yaml dá à cara"
        print(f"    {porta}{marca}")
        if porta != real:
            print(f"        → {real}")

    if pedida:
        ok(f"usar a pedida: {pedida}")
        return pedida

    if cara and len(lista) == 1:
        print("\n  (o robot.yaml aponta a cara para este mesmo nome. Enquanto o")
        print("   ESP32 não existir, quem apanha o /dev/ttyUSB0 é o CyberPi —")
        print("   quando a cara chegar, os dois vão disputá-lo: usar sempre by-id.)")

    escolhida = lista[0]
    if len(lista) > 1:
        aviso("há mais do que uma porta. Se a escolha abaixo estiver errada,")
        aviso("repete com --porta /dev/serial/by-id/… (o by-id não troca de nome)")
    ok(f"escolhida: {escolhida}")
    return escolhida


# ─────────────────────────────────────────────────────────────────────────────
# ligação
# ─────────────────────────────────────────────────────────────────────────────
class Prazo(Exception):
    """O despertador tocou antes de a função voltar."""


def com_prazo(segundos: float, funcao, *args):
    """Corre `funcao` com um despertador (armadilha 3).

    O `connect()` do pacote espera pelo `protocol.ready` num ciclo sem saída:
    se o CyberPi não responder, o script nunca mais volta e não há mensagem
    de erro nenhuma. SIGALRM resolve — e só funciona na thread principal,
    que é onde isto corre.
    """
    def _toca(_sinal, _frame):
        raise Prazo()

    anterior = signal.signal(signal.SIGALRM, _toca)
    signal.setitimer(signal.ITIMER_REAL, segundos)
    try:
        return funcao(*args)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, anterior)


def importar():
    """Devolve (makeblock, CyberPi, SerialPort). Contorna a armadilha 2.

    Sem nenhuma porta CH340 à vista, `import makeblock` rebenta a meio — mas
    rebenta DEPOIS de os submódulos que precisamos já estarem carregados, e
    o Python deixa-os em `sys.modules`. Vamos buscá-los lá.
    """
    rebentou = None
    try:
        import makeblock  # noqa: PLC0415, F401
    except ImportError as erro:
        raise RuntimeError(
            f"falta uma biblioteca ({erro}).\n"
            "      pip install makeblock pyserial"
        ) from erro
    except Exception as erro:  # noqa: BLE001
        rebentou = erro

    cyberpi = sys.modules.get("makeblock.boards.cyberpi")
    porta_mod = sys.modules.get("makeblock.comm.SerialPort")
    if cyberpi is None or porta_mod is None:
        raise RuntimeError(f"o pacote não carregou de todo: {rebentou}")
    mb = sys.modules.get("makeblock") or getattr(porta_mod, "makeblock", None)
    return mb, cyberpi, porta_mod.SerialPort, rebentou


def ja_ligado(porta: str):
    """A ligação que o `import` já fez sozinho — se for à porta certa.

    ⚠️ ISTO É O BUG QUE FAZIA O connect() ENCRAVAR, e custou uma sessão a
    perceber. A armadilha 1 não é só um incómodo: quando existe uma porta
    CH340 (e o CyberPi É CH340), o import ABRE-A e faz o aperto de mão todo —
    fica com uma ligação PRONTA. Se depois abrirmos uma SEGUNDA ligação ao
    mesmo /dev/ttyUSB0, ficam duas threads a ler o mesmo tty: cada uma apanha
    metade dos bytes, nenhuma resposta chega inteira, e o `protocol.ready` do
    segundo board nunca fica verdadeiro. Espera para sempre — por uma resposta
    que está a ser lida pelo outro.

    O sintoma que denuncia isto: o ecrã do CyberPi APAGA-SE (recebeu comandos,
    portanto o cabo e a porta estão bons) e mesmo assim ninguém responde.
    """
    api = sys.modules.get("makeblock.modules.cyberpi.api_cyberpi_api")
    if api is None or getattr(api, "module_auto", None) is None:
        return None, None
    board = getattr(api.module_auto, "_board", None)
    dev = getattr(board, "_dev", None) if board is not None else None
    aberta = getattr(getattr(dev, "_ser", None), "port", None)
    if not aberta:
        return None, None
    if os.path.realpath(aberta) != os.path.realpath(porta):
        aviso(f"a biblioteca agarrou {aberta}, que não é a que queremos — a fechar")
        try:
            dev.exit()
        except Exception:  # noqa: BLE001
            pass
        return None, None
    return api, dev


def ligar(porta: str, espera: float = 20.0):
    """Devolve (api, uart) ou (None, None).

    O import faz-se aqui dentro, e não no topo, por causa da armadilha 1:
    queremos ver a lista de portas ANTES de a biblioteca poder agarrar uma.
    """
    seccao("a ligar")
    try:
        makeblock, CyberPi, SerialPort, rebentou = importar()
    except RuntimeError as erro:
        falhou(str(erro))
        return None, None

    if rebentou is not None:
        ok("o import rebentou como é costume sem porta CH340 — contornado")

    abertas = [p for p in getattr(makeblock, "_ports", []) or [] if p is not None]
    if abertas:
        ok(f"o import abriu {len(abertas)} porta(s) sozinho (armadilha 1)")

    api, dev = ja_ligado(porta)
    if api is not None:
        ok("e essa ligação é a esta porta e já está feita — reaproveitada.")
        ok("abrir uma segunda ligação ao mesmo tty é o que encravava o connect().")
        return api, dev

    uart = SerialPort(porta, 115200)          # ⚠️ o construtor dorme 2 s
    if not hasattr(uart, "_ser"):
        falhou("não abriu a porta (ocupada por outro processo? sem permissões?)")
        print("      o utilizador está no grupo dialout? `groups`")
        return None, None

    print(f"  a apresentar-me (desisto ao fim de {espera:.0f} s)…")
    try:
        api = com_prazo(espera, CyberPi.connect, uart)
    except Prazo:
        falhou("o CyberPi não respondeu — o connect() ficaria aqui para sempre.")
        print("      · o ecrã do CyberPi apagou-se quando correste isto? Então ele")
        print("        RECEBEU comandos, e o problema é de quem está a LER as")
        print("        respostas — vê se há outro processo agarrado à porta:")
        print("          sudo fuser -v /dev/ttyUSB0")
        print("      · está aceso, com o shield ligado e a bateria com carga?")
        print("      · é mesmo esta a porta? (tenta as outras com --porta)")
        print("      · o firmware é recente? (mBlock → Ligar → Atualizar)")
        print("      · o fórum da Makeblock diz que este pacote gosta mais de")
        print("        'upload mode' do que de 'live mode' — experimenta trocar.")
        try:
            uart.exit()
        except Exception:  # noqa: BLE001
            pass
        return None, None

    ok("respondeu. A perguntar quem é…")
    return api, uart


def identificar(cyber) -> bool:
    """Uma resposta vinda de lá é a única prova de que a ligação existe."""
    seccao("do outro lado do cabo")
    versao = None
    try:
        versao = cyber.get_firmware_version()
    except Exception as erro:  # noqa: BLE001
        falhou(f"get_firmware_version: {erro}")

    if versao in (None, ""):
        falhou("ligou mas não diz a versão do firmware — desconfia da ligação.")
        return False

    ok(f"firmware: {versao}")
    # ⚠️ O CyberPi NÃO TEM BATERIA (confirmado na doc da Makeblock): a única
    # bateria do sistema é a do shield, e é ela que alimenta o CyberPi. Por isso
    # o `get_battery` é a bateria do shield, e o `get_extra_battery` é a de uma
    # Pocket Shield que aqui não existe — dar 0 é a resposta certa, não avaria.
    for nome, chamada in (
        ("nome", lambda: cyber.get_name()),
        ("bateria (é a do shield)", lambda: cyber.get_battery()),
        ("bateria extra (Pocket Shield, se houver)", lambda: cyber.get_extra_battery()),
    ):
        try:
            print(f"    {nome:<22} {chamada()}")
        except Exception as erro:  # noqa: BLE001
            print(f"    {nome:<22} — ({erro})")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# chamadas à medida — a parte EXPERIMENTAL, e a mais importante
# ─────────────────────────────────────────────────────────────────────────────
def classe_pacote():
    """A classe do pacote, sem RE-EXECUTAR o import que rebenta.

    Apanhado a ensaiar isto contra um mBot2 de mentira: depois da armadilha 2,
    o nome `makeblock` já não está em `sys.modules`, por isso um inocente
    `from makeblock.protocols.PackData import …` a meio do script volta a
    correr o import todo — rebenta outra vez e, pior, pode abrir a porta série
    uma segunda vez. Os submódulos, esses, ficaram vivos: é de lá que vêm.
    """
    modulo = sys.modules.get("makeblock.protocols.PackData")
    if modulo is None:
        from makeblock.protocols.PackData import HalocodePackData  # noqa: PLC0415

        return HalocodePackData
    return modulo.HalocodePackData


def pedido_a_medida(cyber, script: str, espera: float = 2.0):
    """Uma ida-e-volta só, a devolver VÁRIOS valores.

    Se isto funcionar, muda a arquitetura: em vez de três chamadas para saber
    dois encoders e a distância, faz-se uma. O ciclo de controlo passa a custar
    uma latência, não três.
    """
    HalocodePackData = classe_pacote()
    modulo = cyber.module_auto
    pack = HalocodePackData()
    pack.type = HalocodePackData.TYPE_SCRIPT
    pack.mode = HalocodePackData.TYPE_RUN_WITH_RESPONSE
    pack.script = script
    pack.on_response = modulo.common_request_response_cb
    modulo.send_script(pack)
    if modulo.wait_respond(pack, espera):
        return pack.request_value
    return None


def subscricao_a_medida(cyber, funcao: str, paras: str, espera: float = 2.0):
    """Põe o CyberPi a EMPURRAR um valor que o pacote só sabe pedir.

    O `ultrasonic2.get` já vem assim; o `EM_get_angle` não. Se isto pegar, os
    encoders passam a chegar sozinhos e a leitura fica de borla.
    """
    HalocodePackData = classe_pacote()
    modulo = cyber.module_auto
    pack = HalocodePackData()
    pack.type = HalocodePackData.TYPE_SCRIPT
    pack.mode = HalocodePackData.TYPE_RUN_WITH_RESPONSE
    # o {0} é preenchido com a chave da subscrição quando o pacote é enviado
    pack.script = f"subscribe.add_item({{0}}, {funcao}, {paras})"
    pack.on_response = modulo.common_subscribe_response_cb
    modulo.subscribe(pack)
    modulo.wait_respond(pack, espera)
    return pack


# ─────────────────────────────────────────────────────────────────────────────
# as medições
# ─────────────────────────────────────────────────────────────────────────────
def medir_cadencia(ler, segundos: float = 5.0) -> float:
    """De quanto em quanto tempo é que o valor subscrito se RENOVA.

    Ler uma subscrição custa zero — mas isso não serve de nada se o CyberPi só
    empurrar cinco vezes por segundo. É esta cadência, e não a latência da
    leitura, que passa a ser o teto da odometria. Mede-se a olhar para o valor
    e a cronometrar as mudanças.
    """
    anterior = ler()
    marcas: list[float] = []
    fim = time.time() + segundos
    while time.time() < fim:
        atual = ler()
        if atual != anterior:
            marcas.append(time.perf_counter())
            anterior = atual
        time.sleep(0.002)

    if len(marcas) < 3:
        aviso("o valor quase não mudou — sem mudanças não há cadência para medir.")
        return 0.0
    intervalos = [(b - a) * 1000.0 for a, b in zip(marcas, marcas[1:])]
    p50 = statistics.median(intervalos)
    print(f"  {len(marcas)} atualizações em {segundos:.0f} s · mediana "
          f"{p50:.0f} ms entre elas → ~{1000.0 / p50:.0f} Hz")
    return p50


def medir_latencias(cyber, n: int) -> dict[str, float]:
    titulo("LATÊNCIA — o número que decide tudo")
    resultados: dict[str, float] = {}

    seccao(f"pedidos (ida-e-volta bloqueante) × {n}")
    print("  A primeira linha não toca no shield: é o custo do CABO e do canal")
    print("  de script. As outras duas atravessam o shield, que é um segundo")
    print("  microcontrolador com o seu próprio barramento. A diferença entre")
    print("  elas diz QUEM está a ser lento — e isso muda a solução.")
    resultados["cyberpi"] = relatar(
        "só ao CyberPi (get_name)",
        cronometrar(n, lambda: cyber.get_name(), "get_name"),
        n,
    )
    resultados["ler"] = relatar(
        "ler um encoder (EM_get_angle)",
        cronometrar(n, lambda: cyber.mbot2.EM_get_angle("EM1"), "EM_get_angle"),
        n,
    )
    resultados["mandar"] = relatar(
        "mandar parar (drive_speed 0,0)",
        cronometrar(n, lambda: cyber.mbot2.drive_speed(0, 0), "drive_speed"),
        n,
    )

    seccao(f"subscrição (o CyberPi empurra) × {n}")
    t0 = time.perf_counter()
    try:
        cyber.ultrasonic2.get()
        primeira = (time.perf_counter() - t0) * 1000.0
        print(f"  {'primeira (instala a subscrição)':<34} {primeira:7.1f} ms")
        resultados["subscrito"] = relatar(
            "seguintes (ultrasonic2.get)",
            cronometrar(n, lambda: cyber.ultrasonic2.get(), "ultrasonic2"),
            n,
        )
    except Exception as erro:  # noqa: BLE001
        falhou(f"ultrassons: {erro} (o sensor está ligado à cadeia mBuild?)")

    seccao("cadência — de quanto em quanto tempo o valor subscrito se renova")
    print("  → abana a mão à frente dos ultrassons durante 5 segundos")
    try:
        cadencia = medir_cadencia(lambda: cyber.ultrasonic2.get(), 5.0)
        if cadencia:
            resultados["cadencia"] = cadencia
    except Exception as erro:  # noqa: BLE001
        falhou(f"cadência: {erro}")

    seccao("EXPERIMENTAL — três valores numa ida-e-volta só")
    print("  (se falhar, não é um problema: é o fim desta ideia, não do plano)")
    script = (
        "(cyberpi.mbot2.EM_get_angle('EM1'),"
        " cyberpi.mbot2.EM_get_angle('EM2'),"
        " cyberpi.ultrasonic2.get())"
    )
    try:
        valor = pedido_a_medida(cyber, script)
        if valor is None:
            falhou("sem resposta ao pacote à medida")
        else:
            ok(f"devolveu {valor}")
            resultados["pacote"] = relatar(
                "pacote à medida (3 valores)",
                cronometrar(n, lambda: pedido_a_medida(cyber, script), "pacote"),
                n,
            )
    except Exception as erro:  # noqa: BLE001
        falhou(f"pacote à medida: {erro}")

    seccao("EXPERIMENTAL — subscrever o encoder")
    try:
        pack = subscricao_a_medida(cyber, "cyberpi.mbot2.EM_get_angle", "('EM1',)")
        primeiro = pack.subscribe_value
        print(f"  valor inicial: {primeiro}")
        input("  Põe a mão na roda ESQUERDA e carrega Enter — depois roda-a ")
        print("  → RODA A RODA AGORA (6 segundos)")
        mudou = False
        fim = time.time() + 6.0
        while time.time() < fim:
            if pack.subscribe_value != primeiro:
                mudou = True
                break
            time.sleep(0.02)
        if mudou:
            ok(f"o valor mudou sozinho ({primeiro} → {pack.subscribe_value})")
            ok("os encoders podem chegar SEM ida-e-volta. É o melhor resultado possível.")
            resultados["encoder_subscrito"] = relatar(
                "ler o encoder subscrito",
                cronometrar(n, lambda: pack.subscribe_value, "cache"),
                n,
            )
        else:
            aviso("não mudou — ou não rodaste a roda, ou a subscrição não pegou")
    except Exception as erro:  # noqa: BLE001
        falhou(f"subscrição à medida: {erro}")

    return resultados


def medir_cpu(cyber, segundos: float = 5.0) -> None:
    """Quanto CPU custa manter a conversa aberta.

    A thread da biblioteca lê a série byte a byte em Python. No Pi, isso disputa
    com os 10 fps da deteção de caras — e o orçamento de CPU do robô já está
    escrito no robot.yaml. Melhor saber agora do que descobrir com a Lara à frente.
    """
    seccao(f"custo em CPU de {segundos:.0f} s de conversa")
    cpu0, parede0 = time.process_time(), time.perf_counter()
    fim = time.time() + segundos
    leituras = 0
    while time.time() < fim:
        try:
            cyber.ultrasonic2.get()
            leituras += 1
        except Exception:  # noqa: BLE001
            break
        time.sleep(0.02)
    cpu = time.process_time() - cpu0
    parede = time.perf_counter() - parede0
    print(f"  {leituras} leituras · CPU {cpu:.2f} s em {parede:.2f} s "
          f"= {100 * cpu / parede:.0f}% de um núcleo")
    if cpu / parede > 0.25:
        aviso("mais de um quarto de núcleo só para falar com o mBot2. Contar com isto.")


def medir_encoders_a_mao(cyber, diametro_cm: float = 8.0,
                         distancia_cm: float = 100.0) -> None:
    titulo("ENCODERS — a régua, medida à mão")
    print("  Isto dá o número que falta ao robot.yaml: quantos graus de encoder")
    print("  são uma volta da roda. Sem ele não há odometria.")
    try:
        cyber.mbot2.EM_reset_angle("EM1")
        cyber.mbot2.EM_reset_angle("EM2")
    except Exception as erro:  # noqa: BLE001
        falhou(f"EM_reset_angle: {erro}")
        return

    input("\n  Faz UMA volta completa na roda ESQUERDA, para a frente, e Enter ")
    try:
        e1 = cyber.mbot2.EM_get_angle("EM1")
        e2 = cyber.mbot2.EM_get_angle("EM2")
    except Exception as erro:  # noqa: BLE001
        falhou(f"EM_get_angle: {erro}")
        return

    print(f"\n    EM1 {e1}   EM2 {e2}")
    if e1 in (None, 0) and e2 in (None, 0):
        falhou("nenhum dos dois mexeu. Os motores estão nas portas EM1/EM2?")
        return
    a1, a2 = abs(e1 or 0), abs(e2 or 0)
    ambiguo = bool(a1 and a2 and min(a1, a2) / max(a1, a2) > 0.5)
    if ambiguo:
        aviso(f"os DOIS mexeram, e quase o mesmo ({e1} e {e2}).")
        aviso("o robô estava assente no chão? ao rodar uma roda ele pivota e a")
        aviso("outra roda também anda. Não dá para dizer qual é qual assim —")
        aviso("repete com o robô EM CIMA DE UM LIVRO, as duas rodas no ar.")
        valor = None
    else:
        movido, parado = ("EM1", "EM2") if a1 > a2 else ("EM2", "EM1")
        ok(f"a roda esquerda é a {movido} (a {parado} ficou quieta — como devia)")
        valor = e1 if movido == "EM1" else e2
    if valor and valor < 0:
        aviso("veio NEGATIVO: para a frente conta ao contrário. É um sinal no código,")
        aviso("não é um cabo trocado — não desmontes nada por causa disto.")
    if valor:
        graus = abs(valor)
        print(f"\n    → {graus:.0f} graus de encoder por volta da roda")
        perimetro = 3.14159 * diametro_cm
        print(f"      com rodas de {diametro_cm:.1f} cm de diâmetro "
              f"({perimetro:.1f} cm de perímetro):")
        print(f"      {graus / perimetro:.1f} graus por cm  ·  "
              f"{perimetro / graus * 10:.2f} mm por grau")
        print("      (é esta a régua da odometria — guarda os dois números)")
        if not 300 <= graus <= 420:
            aviso(f"{graus:.0f}° para uma volta inteira é estranho — esperava-se")
            aviso("perto de 360. A volta à mão é difícil de acertar; a régua boa")
            aviso("é a do passo seguinte, com fita métrica.")

    # A volta à mão serve para ver SE conta e em que SENTIDO. Para a régua a
    # sério mede-se uma distância grande: o erro de acertar o ponto de partida
    # dilui-se, e a conta já inclui o escorregamento das rodas no chão real.
    seccao("a régua boa — empurrar uma distância medida")
    print(f"  Vais empurrar o robô {distancia_cm:.0f} cm em LINHA RETA, no chão,")
    print("  com uma fita métrica ao lado. Marca onde ele começa.")
    resposta = input("  (Enter para pôr os contadores a zero, 's' para saltar) ")
    if resposta.strip().lower().startswith("s"):
        return
    try:
        cyber.mbot2.EM_reset_angle("EM1")
        cyber.mbot2.EM_reset_angle("EM2")
        input(f"  empurra os {distancia_cm:.0f} cm e carrega Enter ")
        g1 = abs(cyber.mbot2.EM_get_angle("EM1") or 0)
        g2 = abs(cyber.mbot2.EM_get_angle("EM2") or 0)
    except Exception as erro:  # noqa: BLE001
        falhou(f"EM_get_angle: {erro}")
        return

    print(f"\n    EM1 {g1:.0f}°   EM2 {g2:.0f}°  em {distancia_cm:.0f} cm")
    if not g1 or not g2:
        falhou("um dos encoders não contou — repete.")
        return
    print(f"    → {g1 / distancia_cm:.2f} e {g2 / distancia_cm:.2f} graus por cm")
    print(f"      ({distancia_cm / g1 * 10:.2f} e {distancia_cm / g2 * 10:.2f} mm por grau)")
    desvio = abs(g1 - g2) / max(g1, g2)
    if desvio > 0.05:
        aviso(f"as duas rodas diferem {desvio * 100:.0f}% — em linha reta deviam")
        aviso("contar quase o mesmo. Empurraste a direito? Se sim, é isto que o")
        aviso("compensacao_esq/dir andava a tapar, e agora dá-se para medir.")
    else:
        ok(f"as duas rodas concordam a {desvio * 100:.1f}% — a régua é de confiança")


def mexer_motores(cyber) -> None:
    titulo("MOTORES — ⚠️ AS RODAS VÃO RODAR")
    print("  PÕE O ROBÔ EM CIMA DE UM LIVRO, com as rodas no ar.")
    input("  (Enter quando estiver, Ctrl+C para saltar) ")

    try:
        cyber.mbot2.EM_reset_angle("EM1")
        seccao("EM1 a 50 RPM durante 2 s, em malha fechada no shield")
        cyber.mbot2.EM_set_speed(50, "EM1")
        amostras = []
        fim = time.time() + 2.0
        while time.time() < fim:
            amostras.append(cyber.mbot2.EM_get_speed("EM1"))
            time.sleep(0.1)
        cyber.mbot2.EM_stop("all")
        time.sleep(0.3)
        angulo = cyber.mbot2.EM_get_angle("EM1")
        limpas = [a for a in amostras if isinstance(a, (int, float))]
        if limpas:
            print(f"    velocidade lida: mín {min(limpas)}  mediana "
                  f"{statistics.median(limpas)}  máx {max(limpas)} (pedimos 50)")
        print(f"    andou {angulo} graus em ~2 s")
        ok("se a velocidade lida ficou perto de 50 sem afinares nada,")
        ok("a malha fechada é do shield — e o compensacao_esq/dir deixa de fazer falta.")
    except Exception as erro:  # noqa: BLE001
        falhou(f"motores: {erro}")
    finally:
        try:
            cyber.mbot2.EM_stop("all")
        except Exception:  # noqa: BLE001
            pass


def ver_sensores(cyber) -> None:
    titulo("SENSORES QUE JÁ LÁ ESTÃO")
    print("  ⚠️ Quase tudo isto são SUBSCRIÇÕES, e a primeira leitura devolve o")
    print("  marcador (zero) antes de o CyberPi empurrar o valor verdadeiro.")
    print("  Por isso lê-se duas vezes, com meio segundo pelo meio.")
    for nome, chamada in (
        ("ultrassons (cm)", lambda: cyber.ultrasonic2.get()),
        ("RGB quádruplo l1", lambda: cyber.quad_rgb_sensor.get_gray("l1")),
        ("RGB quádruplo r1", lambda: cyber.quad_rgb_sensor.get_gray("r1")),
        ("guinada do CyberPi", lambda: cyber.get_yaw()),
        ("volume do microfone", lambda: cyber.get_loudness()),
    ):
        try:
            primeira = chamada()
            time.sleep(0.5)
            segunda = chamada()
            extra = "" if primeira == segunda else f"   (1.ª leitura dizia {primeira})"
            print(f"    {nome:<22} {segunda}{extra}")
        except Exception as erro:  # noqa: BLE001
            print(f"    {nome:<22} — ({erro})")


def testar_servo(cyber, porta: str) -> None:
    titulo(f"SERVO na porta {porta} — ⚠️ vai mexer-se")
    print("  As 4 portas de servo do shield partilham os 5 V dele. Os braços da")
    print("  Lylla continuam no PCA9685 a 5,7 V — isto é para uma junta leve só.")
    input("  (Enter para varrer 90° → 60° → 120° → 90°) ")
    try:
        for angulo in (90, 60, 120, 90):
            cyber.mbot2.servo_set(angulo, porta)
            print(f"    {angulo}°")
            time.sleep(0.6)
        cyber.mbot2.servo_release(porta)
        ok("libertado (servo_release) — deixa de forçar e de aquecer")
    except Exception as erro:  # noqa: BLE001
        falhou(f"servo: {erro}")


def veredicto(r: dict[str, float]) -> None:
    titulo("O QUE ISTO QUER DIZER")
    ler = r.get("ler", 0.0)
    mandar = r.get("mandar", 0.0)
    if not ler or not mandar:
        aviso("faltam medições — não há veredicto para dar.")
        return

    ingenuo = 2 * ler + mandar
    print(f"\n  Um ciclo de controlo ingénuo (2 encoders + 1 comando):")
    print(f"    2 × {ler:.0f} ms + {mandar:.0f} ms = {ingenuo:.0f} ms  "
          f"→ no máximo {1000 / ingenuo:.1f} Hz")

    if "pacote" in r:
        esperto = r["pacote"] + mandar
        print(f"\n  O mesmo com o pacote à medida (tudo numa leitura):")
        print(f"    {r['pacote']:.0f} ms + {mandar:.0f} ms = {esperto:.0f} ms  "
              f"→ {1000 / esperto:.1f} Hz")
    if "encoder_subscrito" in r:
        esperto = mandar + r["encoder_subscrito"]
        print(f"\n  E com os encoders subscritos (chegam sozinhos):")
        print(f"    {mandar:.0f} ms + {r['encoder_subscrito']:.2f} ms ≈ {esperto:.0f} ms  "
              f"→ {1000 / esperto:.1f} Hz")

    base = r.get("cyberpi", 0.0)
    if base:
        print(f"\n  E de quem é a lentidão:")
        print(f"    pedido que NÃO passa pelo shield ... {base:6.0f} ms")
        print(f"    pedido ao shield (encoder) ......... {ler:6.0f} ms")
        if ler > base * 1.8:
            print("    → o que custa é atravessar o SHIELD (é um segundo")
            print("      microcontrolador, com barramento próprio). O cabo e o canal")
            print("      de script são mais baratos do que isso.")
        else:
            print("    → os dois custam o mesmo: o preço é do CANAL DE SCRIPT, e")
            print("      nenhuma afinação do shield o vai tirar. A saída é mandar")
            print("      menos vezes — subscrições e comandos que se mantêm.")
        print("    Em qualquer dos casos: o `EM_set_speed` é malha fechada NO")
        print("    shield, portanto a velocidade mantém-se sem ser reenviada. O")
        print("    ciclo não precisa de um comando por passo — só de correções.")

    if "cadencia" in r:
        cad = r["cadencia"]
        print(f"\n  Mas um valor subscrito só se renova de {cad:.0f} em {cad:.0f} ms")
        print(f"  (~{1000 / cad:.0f} Hz): ler mais depressa do que isso é ler duas")
        print("  vezes o mesmo. É este o teto verdadeiro da odometria.")

    print("\n  Régua para decidir:")
    print("    ≥ 20 Hz  → dá para a navegação toda; o mBot2 fica inteiro.")
    print("    10-20 Hz → dá para navegar, mas o desvio corrige-se mais devagar.")
    print("    < 10 Hz  → só serve para comandos de alto nível («anda 30 cm»),")
    print("               com o ciclo rápido a viver DENTRO do CyberPi.")
    print("\n  ⚠️ Seja qual for o número: precipício, paragem de emergência e o")
    print("     botão DPST NÃO passam por este cabo. Nunca.")
    print("\n  Mete os números em docs/ ou pede-me para os pôr na memória do")
    print("  projeto — a decisão de canibalizar ou não o mBot2 depende deles.\n")


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Spike do mBot2 por USB")
    parser.add_argument("--porta", help="porta série do CyberPi")
    parser.add_argument("--amostras", type=int, default=30, help="chamadas por medição")
    parser.add_argument("--com-motores", action="store_true", help="⚠️ roda as rodas")
    parser.add_argument("--servo", help="porta de servo a testar (S1…S4)")
    parser.add_argument("--sem-cpu", action="store_true", help="salta a medição de CPU")
    parser.add_argument("--diametro-roda", type=float, default=8.0,
                        help="diâmetro da roda em cm (mBot2: 8)")
    parser.add_argument("--empurrar-cm", type=float, default=100.0,
                        help="distância a empurrar para calibrar (cm)")
    args = parser.parse_args()

    titulo("SPIKE mBot2 — o shield e o CyberPi vistos do Pi, por um cabo USB")
    print("  Nada aqui corta, solda ou desmonta o que quer que seja.")

    porta = escolher_porta(args.porta)
    if porta is None:
        return 1

    cyber, uart = ligar(porta)
    if cyber is None:
        return 1

    # Armadilha 2: o handler do pacote fecha as portas e sai, com os motores a
    # rodar. Este substitui-o, e é instalado DEPOIS do import de propósito.
    def parar_e_sair(_sinal, _frame):
        print("\n\n⏹  Ctrl+C — a mandar parar os motores…")
        try:
            cyber.mbot2.EM_stop("all")
        except Exception:  # noqa: BLE001
            pass
        raise SystemExit(130)

    signal.signal(signal.SIGINT, parar_e_sair)

    try:
        if not identificar(cyber):
            return 1
        resultados = medir_latencias(cyber, args.amostras)
        if not args.sem_cpu:
            medir_cpu(cyber)
        ver_sensores(cyber)
        medir_encoders_a_mao(cyber, args.diametro_roda, args.empurrar_cm)
        if args.com_motores:
            mexer_motores(cyber)
        if args.servo:
            testar_servo(cyber, args.servo)
        veredicto(resultados)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            cyber.mbot2.EM_stop("all")
        except Exception:  # noqa: BLE001
            pass
        try:
            uart.exit()   # a thread de leitura não é daemon: sem isto fica pendurado
        except Exception:  # noqa: BLE001
            pass
        print("⏹  fim do spike.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
