"""O CICLO PRINCIPAL DO ROBÔ.

    python -m robot.main                    no Raspberry Pi
    ROBO_SIMULAR=1 python -m robot.main     no Mac, sem hardware nenhum

O que acontece:

    1. Espera pela palavra "Olá robô"                    (no Pi, sempre)
    2. Acorda os olhos
    3. Abre o WebSocket e começa a mandar áudio JÁ  ─────────┐
       (a começar pelo pré-rolo: o que já estava em buffer)  │
    4. O mini vai transcrevendo enquanto ela fala            │
    5. O Pi deteta o silêncio e diz "acabou"                 │
    6. O robô muda a cara e toca cada frase mal ela chega  ◄─┘
    7. Executa as ações que vierem na resposta

Os passos 3 a 6 são UMA ligação, e as duas pontas trabalham ao mesmo tempo:
o mini transcreve enquanto ela fala, e escreve a segunda frase enquanto o
robô diz a primeira. É essa sobreposição que faz a diferença entre uma
conversa e um formulário.

Com o mini desligado o robô não percebe o que lhe dizem — e diz isso, com a
voz que tem em cache. Continua a andar, a ver e a obedecer aos comandos
diretos. Nada rebenta; é a regra da casa nº 3.
"""

from __future__ import annotations

import signal
import sys
import time

from robot import config
from robot.brain import cerebro, comandos_diretos, companion, contexto, follow, tools
from robot.brain.state import Estado, Maquina
from robot.hardware import arms, eyes, glow, motors, power, sensors
from robot.perception import faces
from robot.voice import listen, speak, wakeword

_a_correr = True

# O que ele diz quando o mini não responde. É uma frase FIXA de propósito:
# fica na cache de voz depois de ser dita uma vez, e a partir daí sai mesmo
# sem rede nenhuma. Uma frase diferente de cada vez nunca estaria em cache.
FRASE_SEM_CEREBRO = "O meu cérebro grande está a dormir. Mas ainda te vejo e ando!"


def _parar_tudo(*_args) -> None:
    """Ctrl+C ou systemctl stop — parar os motores IMEDIATAMENTE."""
    global _a_correr
    _a_correr = False
    follow.parar()
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
    saude = cerebro.saude()
    if saude:
        print(f"   cérebro: ✅ {saude['pensar']['modelo']} em {cerebro.base_url()}"
              f"  (ouvir: {saude['ouvir']['modelo']} · falar: {saude['falar']['voz']})")
    else:
        print(f"   cérebro: ❌ {cerebro.base_url()} não responde")
        print("      (sem ele o robô não percebe o que lhe dizem — mas anda,")
        print("       vê, e diz as frases que tem em cache)")
    pct = power.percentagem()
    print(f"   bateria: {f'{pct}%' if pct is not None else '(sem leitura)'}")
    print("\n   Diz «Olá robô» para começar. Ctrl+C para parar.\n")

    maquina = Maquina()
    maquina.mudar(Estado.ATENTO)
    speak.falar(f"Olá! Chamo-me {nome}.")
    arms.acenar(2)
    maquina.mudar(Estado.A_DORMIR)
    return maquina


def _fechar(eventos) -> None:
    """Acaba um turno a meio, do lado do robô.

    Fechar o gerador fecha o WebSocket; o mini vê o socket cair a meio de um
    `send`, fecha o gerador dele, e não chega a escrever nada no histórico.
    """
    try:
        eventos.close()
    except Exception:  # noqa: BLE001
        pass


def _executar(acoes: list[dict], maquina: Maquina) -> None:
    """Faz o que o cérebro pediu, e diz o que aconteceu se correr mal.

    ⚠️ O resultado de uma ação só se fala quando é UMA RECUSA. Antes, com
       tool calling, o texto vinha vazio e o resultado da ferramenta era a
       única resposta possível — daí a armadilha nº 3. Agora a fala vem
       sempre no mesmo JSON, e falar outra vez o "Andei 20 cm" só faz o robô
       repetir-se. Mas um "não posso, está aí uma parede" tem de sair.
    """
    if not acoes:
        return
    maquina.mudar(Estado.A_AGIR)
    for acao in acoes:
        print(f"   ⚙️  {acao['nome']}({acao['argumentos']})")
        resultado = tools.executar(acao["nome"], acao["argumentos"])
        print(f"      → {resultado}")
        if isinstance(resultado, tools.Recusa):
            speak.falar(resultado)


def _consumir_turno(maquina: Maquina, eventos) -> bool:
    """Lê os eventos de um turno e faz o robô reagir a cada um.

    Devolve True se o robô chegou a dizer alguma coisa.

    ⚠️ SAI SEMPRE COM O ROBÔ A TER DITO ALGUMA COISA. Qualquer que seja a
       forma como isto corra mal — o mini a morrer, um evento estragado, um
       erro que nunca previmos — a criança tem de ouvir uma explicação. Um
       robô que se cala sem razão parece avariado, e é aí que o projeto morre.
    """
    ouvido = ""
    falou = False
    resposta: dict = {}

    try:
        for evento in eventos:
            tipo = evento.get("tipo")

            if tipo == "parcial":
                # Só para o terminal: dá para ver o mini a perceber a frase
                # enquanto ela ainda está a ser dita.
                print(f"   … «{evento['texto']}»", end="\r", flush=True)

            elif tipo == "ouvido":
                ouvido = evento.get("texto", "")
                print(f"   👤 «{ouvido}»" + " " * 20)
                # Um comando de segurança nunca depende do modelo — nem
                # sequer de a rede estar boa. Ver comandos_diretos.py.
                directa = comandos_diretos.tentar(ouvido)
                if directa is not None:
                    print(f"   ⚡ comando direto → {directa}")
                    speak.falar(directa)
                    # ⚠️ Fechar o turno JÁ. Sem isto, o mini continuava a
                    #    pensar e a sintetizar uma resposta que ninguém ia
                    #    ouvir — e, pior, escrevia-a no histórico da conversa.
                    #    Ao fim de uns turnos o modelo estava a raciocinar
                    #    sobre uma conversa que nunca aconteceu.
                    _fechar(eventos)
                    return True

            elif tipo == "expressao":
                eyes.expressao(evento["nome"])

            elif tipo == "frase":
                if not falou:
                    falou = True
                    maquina.mudar(Estado.A_FALAR)
                print(f"   🤖 «{evento['texto']}»")
                if evento.get("audio"):
                    speak.tocar(evento["audio"], esperar=False)
                else:
                    speak.falar(evento["texto"], esperar=False)

            elif tipo == "resposta":
                resposta = evento

            elif tipo == "fim":
                ms = evento.get("tempo_ms", {})
                if evento.get("motivo") == "cancelado":
                    return True
                if ms.get("primeira_frase"):
                    falou_s = ms.get("fala_s")
                    quanto = f" · ela falou {falou_s} s" if falou_s else ""
                    print(f"   ⏱️  primeira frase {ms['primeira_frase']} ms"
                          f" · turno {ms.get('total')} ms{quanto}")
    except cerebro.SemCerebro as erro:
        # ⚠️ Se ainda não disse nada, TEM de dizer agora. O `escutar()` só
        #    levanta quando alguém o consome — a excepção nasce aqui dentro,
        #    não em quem nos chamou — e quem nos chamou não tem como saber
        #    que o robô ficou calado. Já esteve assim, e o robô emudecia
        #    sempre que a rede tossia.
        print(f"⚠️  {erro}")
        if not falou:
            speak.falar(FRASE_SEM_CEREBRO)
        return True
    except Exception as erro:  # noqa: BLE001
        # Qualquer outra coisa: um áudio estragado (binascii.Error, que é um
        # ValueError), um evento sem a chave que esperávamos, o que for. O
        # robô não sabe o que aconteceu, mas sabe que não conseguiu — e diz.
        print(f"⚠️  {type(erro).__name__}: {erro}")
        if not falou:
            speak.falar("Baralhei-me toda. Dizes outra vez?")
        return True

    # Sem `and ouvido`: o que interessa é ele NÃO TER DITO NADA. Com a
    # condição dupla, uma resposta com a fala vazia deixava o robô a
    # executar a ação em silêncio.
    if not falou:
        speak.falar("Não percebi. Podes repetir?")
        return True

    for razao in resposta.get("recusadas", []):
        print(f"   ↯ recusei: {razao}")

    speak.esperar_acabar()      # as ações vêm DEPOIS da fala, não por cima
    _executar(resposta.get("acoes", []), maquina)
    return True


def uma_interacao(maquina: Maquina, obs=None) -> None:
    """Um ciclo completo: ouvir → (mini) → falar → agir."""
    maquina.mudar(Estado.A_OUVIR)
    ctx = contexto.montar(maquina, obs)
    if ctx.get("pessoa"):
        maquina.pessoa = ctx["pessoa"]
        print(f"   👁️  vejo: {ctx['pessoa']}")

    if config.a_simular():
        # Em simulação não há microfone: escreve-se a frase e manda-se texto.
        texto = listen.ouvir()
        if texto:
            directa = comandos_diretos.tentar(texto)
            if directa is not None:
                print(f"   ⚡ comando direto → {directa}")
                speak.falar(directa)
            else:
                maquina.mudar(Estado.A_PENSAR)
                try:
                    _consumir_turno(maquina, cerebro.turno(texto=texto, contexto=ctx))
                except cerebro.SemCerebro as erro:
                    print(f"⚠️  {erro}")
                    speak.falar(FRASE_SEM_CEREBRO)
        glow.respirar("base")
        maquina.mudar(Estado.ATENTO)
        return

    maquina.mudar(Estado.A_PENSAR)
    glow.pulsar("base")     # a pulsar depressa enquanto ouve e pensa
    try:
        if config.obter("cerebro.escutar_em_directo", True):
            # O caminho normal: o áudio vai a caminho do mini enquanto ela
            # fala, e ele vai transcrevendo. Ver docs/AI-config.md.
            #
            # O `cancelar` é o botão vermelho da conversa: se o robô tiver de
            # parar enquanto ela ainda fala (bateria crítica, o botão de
            # emergência), o turno acaba sem esperar pelo modelo.
            eventos = cerebro.escutar(listen.escutar_em_directo(), contexto=ctx,
                                      cancelar=lambda: not _a_correr)
        else:
            # O caminho antigo: gravar tudo, e só depois enviar. Fica como
            # interruptor — se o streaming der problemas em casa, uma linha
            # no robot.yaml põe o robô a funcionar como funcionava.
            wav = listen.gravar_wav()
            if wav is None:
                speak.falar("Não percebi. Podes repetir?")
                maquina.mudar(Estado.ATENTO)
                return
            eventos = cerebro.turno(wav=wav, contexto=ctx)
        _consumir_turno(maquina, eventos)
    except cerebro.SemCerebro as erro:
        print(f"⚠️  {erro}")
        speak.falar(FRASE_SEM_CEREBRO)

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

            # Modo seguir: andar atrás de quem o robô está a ver. Ligado pela
            # ação `seguir` do cérebro; desligado pelo "pára" e pelo veto dos
            # sensores, que estão dentro do um_passo(). Ver D17.
            if follow.a_seguir():
                comando = follow.um_passo(obs)
                if comando.parado and not obs.presente:
                    follow.parar()
                    speak.falar("Perdi-te de vista!", esperar=False)

            # ⚠️ Timeout curto de propósito: o motors.verificar_timeout() só
            #    corre entre chamadas desta função. Com timeout=30 a rede de
            #    segurança de 3 s dos motores seria, na prática, de 30 s.
            if wakeword.esperar_pela_palavra(timeout=0.5):
                maquina.mudar(Estado.ATENTO)
                uma_interacao(maquina, obs)
            else:
                # Sem palavra-chave — respirar e voltar ao topo do ciclo,
                # onde o timeout dos motores é verificado outra vez.
                time.sleep(0.05)

        except KeyboardInterrupt:
            _parar_tudo()
        except Exception as erro:  # noqa: BLE001
            # REGRA DE OURO: nada rebenta à frente de uma criança.
            print(f"⚠️  Erro no ciclo principal: {erro}")
            follow.parar()
            motors.parar()
            arms.relaxar()
            eyes.expressao("surpreso")
            time.sleep(2)
            maquina.mudar(Estado.ATENTO)


if __name__ == "__main__":
    principal()
