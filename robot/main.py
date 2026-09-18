"""O CICLO PRINCIPAL DO ROBÔ.

    python -m robot.main                    no Raspberry Pi
    ROBO_SIMULAR=1 python -m robot.main     no Mac, sem hardware nenhum

O ciclo, dez vezes por segundo (ver `principal()`):

    1. cuidar do corpo      motores pendurados, sono, bateria
    2. olhar à volta        quem está à frente
    3. continuar tarefas    seguir, escondidas, ir a uma divisão
    4. conversar            quando alguém chama (Enter, ou a palavra mágica)

E cada conversa são quatro passos (robot/brain/conversa.py):

    OUVIR → INTERPRETAR → CONFIRMAR → EXECUTAR
    luzes verde→laranja · mini transcreve e pensa · bip, luz roxa, «hmm» ·
    falar, andar, seguir, aprender uma cara…

As luzes, os sons e as caras de cada momento são ROTINAS (robot/rotinas.py):
listas de enriquecimentos pequenos, que se mudam no robot.yaml.

Com o mini desligado o robô não percebe o que lhe dizem. Diz isso com a voz
que tem em cache e continua a reconhecer pessoas. Nenhuma ordem falada pode ser
transcrita. O timeout atual dos motores partilha este ciclo e ainda precisa de
ser separado para funcionar como watchdog durante uma espera de rede.
"""

from __future__ import annotations

import argparse
import importlib
import queue
import signal
import sys
import threading
import time

from robot import config, rotinas
# (comandos_diretos, contexto, tools, listen e sensors já não são usados aqui
#  dentro, mas os testes chegam a eles por `main.` — ficam importados.)
from robot.brain import cerebro, comandos_diretos, companion, contexto, conversa, follow, tools  # noqa: F401
from robot.brain.state import Estado, Maquina
from robot.hardware import arms, eyes, glow, motors, power, sensors  # noqa: F401
from robot.navigation import ir_para as navegar
from robot.navigation import procurar
from robot.perception import faces
from robot.voice import enchimentos, frases, listen, speak, wakeword  # noqa: F401

_a_correr = True


class Opcoes:
    """O que esta execução liga. Por omissão, o mínimo que funciona hoje.

    O robô tem muito mais escrito do que aquilo que está provado no hardware
    (seguir, escondidas, atravessar a casa). Tudo isso precisa do mBot2 e de
    sensores, e ligá-lo por omissão só dá erros a passear pelo terminal.
    Fica atrás do `--mbot`, que é também o interruptor dos motores.
    """

    mbot = False
    acordar = "tecla"


OPCOES = Opcoes()


def _ler_argumentos(argv: list[str] | None = None) -> Opcoes:
    p = argparse.ArgumentParser(prog="robot.main", description="O ciclo da Lylla.")
    p.add_argument("--mbot", action="store_true",
                   help="ligar o mBot2 (motores, seguir, escondidas, navegar)")
    p.add_argument("--acordar", choices=("tecla", "som"), default="tecla",
                   help="tecla: carregar no Enter para falar (por omissão) · "
                        "som: qualquer som alto acorda")
    args = p.parse_args(argv)
    OPCOES.mbot = args.mbot
    OPCOES.acordar = args.acordar
    return OPCOES


class _Enter:
    """O Enter como palavra-chave, sem bloquear o ciclo.

    ⚠️ Solução DE BANCADA, até o modelo da palavra-chave estar treinado. O
       substituto por som alto tem um problema que não se resolve com
       limiares: o robô ouve-se a si próprio pela coluna e volta a acordar —
       o AEC do reSpeaker é que fecha esse buraco. Com o Enter não há
       realimentação nenhuma e dá para trabalhar no resto.
    """

    def __init__(self) -> None:
        self._fila: queue.Queue[bool] = queue.Queue()
        fio = threading.Thread(target=self._ler, daemon=True)
        fio.start()

    def _ler(self) -> None:
        for _ in sys.stdin:
            self._fila.put(True)

    def carregou(self, timeout: float) -> bool:
        try:
            self._fila.get(timeout=timeout)
        except queue.Empty:
            return False
        while not self._fila.empty():   # vários Enters seguidos são um só
            self._fila.get_nowait()
        return True


_enter: _Enter | None = None


def _acordou(timeout: float) -> bool:
    """Chegou a vez de ouvir uma frase?"""
    if OPCOES.acordar == "tecla":
        global _enter
        if _enter is None:
            _enter = _Enter()
        return _enter.carregou(timeout)
    return wakeword.esperar_pela_palavra(timeout=timeout)

def __getattr__(nome: str):
    """`main.FRASE_SEM_CEREBRO` continua a existir, na língua do momento.

    É uma frase FIXA de propósito: fica na cache de voz depois de ser dita uma
    vez, e a partir daí sai mesmo sem rede nenhuma.
    """
    if nome == "FRASE_SEM_CEREBRO":
        return frases.dizer("sem_cerebro")
    raise AttributeError(nome)


def _carregar_comandos_da_lara() -> None:
    """Carrega os comandos pessoais sem impedir o arranque se houver um erro."""
    try:
        importlib.import_module("meus_comandos")
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Não consegui carregar meus_comandos.py ({erro})")


def _parar_tudo(*_args) -> None:
    """Ctrl+C ou systemctl stop — parar os motores IMEDIATAMENTE."""
    global _a_correr
    _a_correr = False
    follow.parar()
    procurar.parar()
    navegar.parar()
    motors.parar()
    arms.relaxar()
    glow.apagar()
    eyes.expressao("a_dormir")
    print("\n👋 Adeus!")
    sys.exit(0)


def arrancar() -> Maquina:
    nome = config.nome_do_robo()
    print(f"\n🤖 {nome} a arrancar…")
    _carregar_comandos_da_lara()
    if config.a_simular():
        print("   ⚠️  MODO SIMULAÇÃO — não há hardware. Tudo sai no terminal.\n")

    eyes.expressao("a_dormir")
    eyes.comecar_a_piscar_sozinho()
    arms.bracos_ao_lado()

    # ⚠️ O mBot2 liga-se AQUI, antes das luzes. A ligação só pode ser aberta na
    #    thread principal (ver mbot2.ligar()), e as luzes saem por ele: se a
    #    animação arrancasse primeiro, era ela a tentar abri-la, numa thread
    #    onde o prazo não funciona.
    if OPCOES.mbot:
        from robot.hardware import mbot2

        print(f"   mBot2: {'✅ ligado' if mbot2.ligar() else '❌ não respondeu'}")

    rotinas.correr("acabei")   # a base pulsa devagar — lê-se como "vivo em repouso"

    # ⚠️ O modo é definido ANTES de qualquer movimento poder acontecer. Se
    #    fosse definido mais tarde, havia uma janela em que um comando à
    #    velocidade do chão podia atirar o robô da secretária abaixo.
    if OPCOES.mbot and companion.ligada():
        motors.modo("secretaria")

    conhecidos = faces.pessoas_conhecidas()
    print(f"   conhece: {', '.join(conhecidos) if conhecidos else '(ninguém ainda)'}")
    print(f"   modo: {motors.modo_atual()}"
          f"{'  · companheiro de secretária ligado' if companion.ligada() else ''}")
    saude = cerebro.saude()
    if saude:
        print(f"   cérebro: ✅ {saude['pensar']['modelo']} em {cerebro.base_url()}"
              f"  (ouvir: {saude['ouvir']['modelo']} · falar: {saude['falar']['voz']})")
    else:
        print(f"   cérebro: ❌ {cerebro.base_url()} não responde")
        print("      (sem ele o robô não percebe o que lhe dizem, mas continua")
        print("       a ver e pode dizer as frases que tem em cache)")
    pct = power.percentagem()
    print(f"   bateria: {f'{pct}%' if pct is not None else '(sem leitura)'}")
    if not OPCOES.mbot:
        print("   mBot2: desligado (usa --mbot para ligar os motores)")
    if OPCOES.acordar == "tecla":
        print("\n   Carrega no ENTER e fala. Ctrl+C para parar.\n")
    else:
        print("\n   Faz um som para começar. Ctrl+C para parar.\n")

    # Os «hmm» pedem-se já ao mini, em fundo: quando for preciso o primeiro,
    # tem de estar em cache — um «hmm» que vai à rede chega depois da resposta.
    enchimentos.preparar()

    maquina = Maquina()
    maquina.mudar(Estado.ATENTO)
    speak.falar(frases.dizer("ola", nome=nome))
    arms.acenar(2)
    maquina.mudar(Estado.A_DORMIR)
    return maquina


# ============================================================================
# A CONVERSA vive em robot/brain/conversa.py — ouvir → interpretar →
# confirmar → executar. Estes nomes ficam para quem já os usava (os testes).
# ============================================================================


def _consumir_turno(maquina: Maquina, eventos) -> bool:
    return conversa.consumir(maquina, eventos)


def _executar(acoes: list[dict], maquina: Maquina) -> None:
    conversa.executar_acoes(acoes, maquina)


def uma_interacao(maquina: Maquina, obs=None) -> None:
    conversa.uma_interacao(maquina, obs, cancelar=lambda: not _a_correr)


_avisou_bateria = False


def _desligar_o_pi() -> None:
    """Desliga o Raspberry Pi como deve ser.

    Sair do programa não chega: o Pi continuaria a puxar ~6 W até o BMS da
    bateria cortar — que é exatamente o que queríamos evitar — e há risco de
    corromper o cartão SD quando a corrente falha a meio de uma escrita.
    """
    import subprocess

    motors.parar()
    arms.relaxar()
    eyes.expressao("a_dormir")
    try:
        subprocess.run(["sudo", "systemctl", "poweroff"], check=False, timeout=10)
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Não consegui desligar o Pi: {erro}")
    _parar_tudo()


def _verificar_bateria(maquina: Maquina) -> None:
    """Avisa quando a bateria está a acabar, e desliga-se se ficar crítica.

    ⚠️ Só medimos com o robô PARADO. Com os motores ou os servos a puxar
       corrente, a tensão cai 0,3-0,5 V e a leitura não significa nada.
    """
    global _avisou_bateria
    if maquina.estado not in (Estado.ATENTO, Estado.A_DORMIR):
        return

    if power.critico():
        eyes.expressao("a_dormir")
        speak.falar(frases.dizer("bateria_critica"))
        motors.parar()
        arms.relaxar()
        _desligar_o_pi()
    elif power.tem_fome() and not _avisou_bateria:
        _avisou_bateria = True
        eyes.expressao("bateria_fraca")
        speak.falar(frases.dizer("bateria_fraca", pct=power.percentagem()))


def principal(argv: list[str] | None = None) -> None:
    _ler_argumentos(argv)
    signal.signal(signal.SIGINT, _parar_tudo)
    signal.signal(signal.SIGTERM, _parar_tudo)

    maquina = arrancar()

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  O CICLO — dez vezes por segundo, sempre pela mesma ordem:       ║
    # ║                                                                  ║
    # ║    1. cuidar do corpo      motores pendurados, sono, bateria     ║
    # ║    2. olhar à volta        quem está à frente (modo secretária)  ║
    # ║    3. continuar tarefas    seguir, escondidas, ir a uma divisão  ║
    # ║    4. conversar            se alguém chamou: ouvir → interpretar ║
    # ║                            → confirmar → executar                ║
    # ╚══════════════════════════════════════════════════════════════════╝
    while _a_correr:
        try:
            _cuidar_do_corpo(maquina)
            obs = _olhar_a_volta(maquina)
            _continuar_tarefas(obs)

            # ⚠️ Timeout curto de propósito: o motors.verificar_timeout() só
            #    corre entre voltas. Com timeout=30 a rede de segurança de 3 s
            #    dos motores seria, na prática, de 30 s.
            if _acordou(0.5):
                maquina.mudar(Estado.ATENTO)
                uma_interacao(maquina, obs)
            else:
                time.sleep(0.05)

        except KeyboardInterrupt:
            _parar_tudo()
        except Exception as erro:  # noqa: BLE001
            # REGRA DE OURO: nada rebenta à frente de uma criança.
            print(f"⚠️  Erro no ciclo principal: {erro}")
            follow.parar()
            procurar.parar()
            navegar.parar()
            motors.parar()
            arms.relaxar()
            eyes.expressao("surpreso")
            time.sleep(2)
            maquina.mudar(Estado.ATENTO)


def _cuidar_do_corpo(maquina: Maquina) -> None:
    """1. A rede de segurança dos motores, o sono e a bateria."""
    motors.verificar_timeout()      # um movimento pendurado pára aqui

    # Cai no sono ao fim de 5 minutos sem ninguém falar com ele.
    if maquina.deve_adormecer():
        maquina.mudar(Estado.A_DORMIR)
        arms.relaxar()              # servos parados deixam de aquecer
        rotinas.correr("adormecer")

    _verificar_bateria(maquina)


def _olhar_a_volta(maquina: Maquina):
    """2. Modo secretária: reparar em quem chega, seguir com os olhos,
    entreter-se sozinho. Nunca fala — para isso é a palavra-chave."""
    obs = companion.tick(maquina, mexer=OPCOES.mbot)
    if obs.presente:
        maquina.registar_presenca()
    return obs


def _continuar_tarefas(obs) -> None:
    """3. O que o robô está a meio de fazer: seguir, escondidas, navegar.

    Ligados pelas ações do cérebro; desligados pelo «pára» e pelo veto dos
    sensores (dentro de cada um_passo()). Os três FALAM SEMPRE no fim:
    chegar em silêncio e desistir em silêncio parecem a mesma coisa.
    """
    if not OPCOES.mbot:
        return

    if follow.a_seguir():
        comando = follow.um_passo(obs)
        if comando.parado and not obs.presente:
            follow.parar()
            speak.falar(frases.dizer("perdi_te"), esperar=False)

    # Ou anda a procura ou anda a navegação — nunca os dois nos mesmos motores.
    if procurar.a_procurar():
        jogada = procurar.um_passo(obs)
        if jogada.terminou:
            speak.falar(_fim_do_jogo(jogada), esperar=False)
            eyes.expressao("contente" if jogada.encontrou else "triste")
            # ⚠️ «perdi-me» NÃO acaba o jogo: ele fica à espera que lhe
            #    digam onde está (ação ir_para com estou_aqui=true).
            if jogada.razao != "onde estou":
                procurar.parar()
    elif navegar.a_navegar():
        passo = navegar.um_passo()
        if passo.terminou:
            speak.falar(_fim_da_viagem(passo.razao), esperar=False)


def _fim_do_jogo(jogada) -> str:
    if jogada.encontrou:
        onde = f" {navegar.em_ingles(jogada.onde, 'em')}" if jogada.onde else ""
        return f"Found you{onde}!"
    return {
        "não te encontrei": "I give up! Where are you?",
        "onde estou": "Wait... I'm lost. Which room am I in?",
        "desisti": "I can't get there. You win!",
        "precipício": "I stopped the game, there's a step here!",
    }.get(jogada.razao, "Game over.")


def _fim_da_viagem(razao: str) -> str:
    """Uma frase para cada maneira de uma viagem acabar. Nunca «erro»."""
    return {
        "cheguei": "I'm here!",
        "precipício": "I stopped, there's a step here!",
        "encravada": "I'm stuck, I can't get through.",
        "perdi-me": "I'm not sure where I am. Which room am I in?",
        "demorou de mais": "I gave up, it was taking too long.",
    }.get(razao, "Stopped.")


if __name__ == "__main__":
    principal()
