"""O CICLO PRINCIPAL DO ROBÔ.

    python -m robot.main                    no Raspberry Pi
    ROBO_SIMULAR=1 python -m robot.main     no Mac, sem hardware nenhum

O que acontece:

    1. Espera pela palavra "Olá robô"
    2. Acorda os olhos
    3. Grava até haver silêncio
    4. Transcreve com o Whisper
    5. Vê quem está à frente (câmara)
    6. Manda a pergunta ao LLM no Mac
    7. Fala a resposta
    8. Executa as ações que o LLM tenha pedido
"""

from __future__ import annotations

import signal
import sys
import time

from robot import config
from robot.brain import comandos_diretos, companion, llm, tools
from robot.brain.state import Estado, Maquina
from robot.hardware import arms, eyes, glow, motors, power, sensors
from robot.perception import faces
from robot.voice import listen, speak, wakeword

_a_correr = True


def _parar_tudo(*_args) -> None:
    """Ctrl+C ou systemctl stop — parar os motores IMEDIATAMENTE."""
    global _a_correr
    _a_correr = False
    motors.parar()
    arms.relaxar()
    glow.apagar()
    eyes.expressao("a_dormir")
    print("\n👋 Adeus!")
    sys.exit(0)


def arrancar() -> Maquina:
    nome = config.nome_do_robo()
    print(f"\n🤖 {nome} a arrancar…")
    if config.a_simular():
        print("   ⚠️  MODO SIMULAÇÃO — não há hardware. Tudo sai no terminal.\n")

    eyes.expressao("a_dormir")
    eyes.comecar_a_piscar_sozinho()
    arms.bracos_ao_lado()
    glow.respirar("base")   # a base pulsa devagar — lê-se como "vivo em repouso"

    # ⚠️ O modo é definido ANTES de qualquer movimento poder acontecer. Se
    #    fosse definido mais tarde, havia uma janela em que um comando à
    #    velocidade do chão podia atirar o robô da secretária abaixo.
    if companion.ligada():
        motors.modo("secretaria")

    conhecidos = faces.pessoas_conhecidas()
    print(f"   conhece: {', '.join(conhecidos) if conhecidos else '(ninguém ainda)'}")
    print(f"   modo: {motors.modo_atual()}"
          f"{'  · companheiro de secretária ligado' if companion.ligada() else ''}")
    print(f"   cérebro grande: {'✅ ligado' if llm.esta_ligado() else '❌ offline'}")
    pct = power.percentagem()
    print(f"   bateria: {f'{pct}%' if pct is not None else '(sem leitura)'}")
    print("\n   Diz «Olá robô» para começar. Ctrl+C para parar.\n")

    maquina = Maquina()
    maquina.mudar(Estado.ATENTO)
    speak.falar(f"Olá! Eu sou o {nome}.")
    arms.acenar(2)
    maquina.mudar(Estado.A_DORMIR)
    return maquina


def uma_interacao(maquina: Maquina) -> None:
    """Um ciclo completo: ouvir → pensar → responder → agir."""
    # 1 · ouvir
    maquina.mudar(Estado.A_OUVIR)
    texto = listen.ouvir()
    if not texto:
        speak.falar("Não percebi. Podes repetir?")
        maquina.mudar(Estado.ATENTO)
        return
    print(f"   👤 «{texto}»")

    # 1b · comandos que NÃO passam pelo LLM
    #
    # ⚠️ "pára" e "para de olhar" têm de funcionar 100% das vezes, não 90%.
    #    Ver robot/brain/comandos_diretos.py — a explicação está toda lá.
    resposta_direta = comandos_diretos.tentar(texto)
    if resposta_direta is not None:
        print(f"   ⚡ comando direto → {resposta_direta}")
        speak.falar(resposta_direta)
        maquina.mudar(Estado.ATENTO)
        return

    # 2 · ver quem está a falar (dá contexto ao LLM)
    contexto = None
    pessoa = faces.quem_esta_a_ver()
    if pessoa:
        maquina.pessoa = pessoa
        contexto = f"Estás a falar com a/o {pessoa}."
        print(f"   👁️  vejo: {pessoa}")

    # 3 · pensar
    maquina.mudar(Estado.A_PENSAR)
    glow.pulsar("base")     # a pulsar depressa enquanto pensa
    resposta = llm.perguntar(texto, contexto=contexto, ferramentas=tools.FERRAMENTAS)

    # 4 · falar
    if resposta["texto"]:
        maquina.mudar(Estado.A_FALAR)
        print(f"   🤖 «{resposta['texto']}»")
        speak.falar(resposta["texto"])

    # 5 · agir
    #
    # ⚠️ Quando o LLM devolve uma ação, o campo de texto vem quase sempre
    #    VAZIO — toda a resposta está na chamada da ferramenta. Se não
    #    falarmos o resultado aqui, o robô executa a ação em silêncio e
    #    parece avariado. Perguntar "quem está aqui?" daria zero resposta.
    if resposta["acoes"]:
        maquina.mudar(Estado.A_AGIR)
        for acao in resposta["acoes"]:
            print(f"   ⚙️  {acao['nome']}({acao['argumentos']})")
            resultado = tools.executar(acao["nome"], acao["argumentos"])
            print(f"      → {resultado}")
            if resultado:
                print(f"   🤖 «{resultado}»")
                speak.falar(resultado)

    glow.respirar("base")
    maquina.mudar(Estado.ATENTO)


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
        speak.falar("Já não tenho bateria nenhuma. Vou dormir. Até já!")
        motors.parar()
        arms.relaxar()
        _desligar_o_pi()
    elif power.tem_fome() and not _avisou_bateria:
        _avisou_bateria = True
        eyes.expressao("bateria_fraca")
        speak.falar(f"Estou com fome. Tenho só {power.percentagem()} por cento de bateria.")


def principal() -> None:
    signal.signal(signal.SIGINT, _parar_tudo)
    signal.signal(signal.SIGTERM, _parar_tudo)

    maquina = arrancar()

    while _a_correr:
        try:
            # Rede de segurança: se um movimento ficou pendurado, parar.
            motors.verificar_timeout()

            # Cai no sono ao fim de 5 minutos sem ninguém falar com ele.
            if maquina.deve_adormecer():
                maquina.mudar(Estado.A_DORMIR)
                arms.relaxar()   # servos parados deixam de aquecer
                glow.respirar("base", periodo=7.0, minimo=0.03, maximo=0.15)

            # Bateria a acabar — avisar uma vez, e desligar-se se for crítico.
            _verificar_bateria(maquina)

            # Modo secretária: reparar em quem chega, seguir com os olhos,
            # entreter-se sozinho. Nunca fala — para isso é a palavra-chave.
            obs = companion.tick(maquina)
            if obs.presente:
                maquina.registar_presenca()

            # ⚠️ Timeout curto de propósito: o motors.verificar_timeout() só
            #    corre entre chamadas desta função. Com timeout=30 a rede de
            #    segurança de 3 s dos motores seria, na prática, de 30 s.
            if wakeword.esperar_pela_palavra(timeout=0.5):
                maquina.mudar(Estado.ATENTO)
                uma_interacao(maquina)
            else:
                # Sem palavra-chave — respirar e voltar ao topo do ciclo,
                # onde o timeout dos motores é verificado outra vez.
                time.sleep(0.05)

        except KeyboardInterrupt:
            _parar_tudo()
        except Exception as erro:  # noqa: BLE001
            # REGRA DE OURO: nada rebenta à frente de uma criança.
            print(f"⚠️  Erro no ciclo principal: {erro}")
            motors.parar()
            arms.relaxar()
            eyes.expressao("surpreso")
            time.sleep(2)
            maquina.mudar(Estado.ATENTO)


if __name__ == "__main__":
    principal()
