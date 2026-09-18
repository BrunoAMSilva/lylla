"""OUVIR — o microfone é do Pi; quem transcreve é o mac mini.

╔══════════════════════════════════════════════════════════════════════════╗
║  O QUE FICA AQUI E O QUE VAI PARA O MINI                                 ║
║                                                                          ║
║  Fica aqui: gravar, e decidir QUANDO A FRASE ACABOU. As duas coisas      ║
║  têm de ser locais — a segunda é uma decisão que não pode depender da    ║
║  rede, e é aqui que está o microfone.                                    ║
║                                                                          ║
║  Vai para o mini: transcrever. É pesado, e no Pi 5 o `base` corre a 1-2× ║
║  o tempo real enquanto o `small` (o primeiro que percebe bem português)  ║
║  fica mais lento que o tempo real. Não há Whisper local nenhum neste     ║
║  ficheiro: com o mini desligado o robô não percebe o que lhe dizem, e    ║
║  diz isso — em vez de carregar 500 MB de modelo no cartão SD para um     ║
║  caso que a rede Tailscale torna raro.                                   ║
╚══════════════════════════════════════════════════════════════════════════╝

Duas maneiras de gravar:

  · `escutar_em_directo()` — um gerador que solta o áudio AOS BOCADOS
    enquanto a pessoa fala. É o que o /v1/escutar usa, e o que faz o mini
    transcrever ao mesmo tempo que ela fala.
  · `gravar_wav()` — grava tudo e devolve um WAV no fim. É o caminho do
    /v1/turno, que fica como recurso e para os scripts de teste.

🔒 O áudio NUNCA é escrito em disco. Passa em memória e é descartado.
"""

from __future__ import annotations

import time

import numpy as np

from robot import config

TAXA = 16_000
BLOCO = 1280      # 80 ms, o mesmo da palavra-chave

# ⚠️ ARMADILHA QUE JÁ NOS APANHOU UMA VEZ:
# a tentação é medir o ruído de fundo nos primeiros blocos da gravação. Mas
# isto começa LOGO A SEGUIR à palavra-chave — a pessoa já está a falar. O
# limiar ficaria calibrado ao nível da voz dela e nunca mais disparava: o robô
# gravava 10 s de nada e respondia "não percebi".
#
# Em vez disso: um chão ABSOLUTO (que apanha a fala mesmo que ela já tenha
# começado) combinado com o mínimo observado até agora (que se adapta a uma
# sala barulhenta).
CHAO_ABSOLUTO = 0.012


def abrir_microfone(sd, dtype: str):
    """O `InputStream` com o número de canais que o microfone REALMENTE tem.

    ⚠️ Um MEMS I2S ocupa UM dos dois slots do barramento (o `L/R` escolhe
       qual); o outro slot fica vazio. Pedir `channels=1` não dá o slot bom —
       dá uma mistura dele com o vazio, e o resultado media rms 0,0085 contra
       0,0893 do canal sozinho. Com esse sinal o detetor de silêncio nunca
       adormecia e a transcrição saía noutra língua.
    """
    return sd.InputStream(
        samplerate=TAXA,
        channels=int(config.obter("voz.canais_microfone", 1)),
        dtype=dtype,
        blocksize=BLOCO,
    )


def canal_util(dados: np.ndarray) -> np.ndarray:
    """A coluna onde o microfone está mesmo (ver `abrir_microfone`), já com o
    ganho do `voz.ganho_microfone` aplicado.

    O ganho é em SOFTWARE: o MEMS I2S não tem controlo de ganho nenhum que a
    ALSA exponha. Aplica-se aqui porque é por aqui que passam as três
    gravações (a palavra-chave, a escuta em contínuo e a gravação em lote) —
    assim o detetor de silêncio e o mini ouvem o MESMO sinal.
    """
    coluna = int(config.obter("voz.canal_microfone", 0))
    amostra = dados[:, min(coluna, dados.shape[1] - 1)]
    ganho = float(config.obter("voz.ganho_microfone", 1.0) or 1.0)
    if ganho == 1.0:
        return amostra
    if np.issubdtype(amostra.dtype, np.integer):
        return np.clip(amostra.astype(np.float32) * ganho, -32768, 32767).astype(amostra.dtype)
    return np.clip(amostra * ganho, -1.0, 1.0).astype(amostra.dtype)


class _Silencio:
    """Decide quando a frase acabou. Vive à parte para os dois caminhos de
    gravação usarem exatamente a mesma regra.

    ╔══════════════════════════════════════════════════════════════════════╗
    ║  AS PAUSAS DE UMA CRIANÇA                                            ║
    ║                                                                      ║
    ║  «What is… hmm… classes?» — com 1 s fixo de silêncio, o robô partia  ║
    ║  à procura de resposta depois de «What is». Por isso a pausa que     ║
    ║  fecha a frase é MAIOR no princípio (ela ainda está a arrumar a      ║
    ║  ideia) e volta ao normal depois de uns segundos de fala:            ║
    ║                                                                      ║
    ║      pausa = silencio_para_parar_s                                   ║
    ║            + silencio_extra_inicio_s   (enquanto falou < fala_curta) ║
    ║                                                                      ║
    ║  E se ela ainda nem começou, espera `espera_inicio_s` antes de       ║
    ║  desistir — o robô acordou, mas ela pode estar a pensar no que dizer.║
    ╚══════════════════════════════════════════════════════════════════════╝

    `progresso()` diz quanto do silêncio necessário já passou (0 → 1): é o
    que as luzes usam para passar de verde a laranja.
    """

    def __init__(self, silencio_s: float | None = None) -> None:
        self.silencio_s = float(
            silencio_s if silencio_s is not None
            else config.obter("voz.silencio_para_parar_s", 1.2)
        )
        self.extra_inicio_s = float(config.obter("voz.silencio_extra_inicio_s", 0.8))
        self.fala_curta_s = float(config.obter("voz.fala_curta_s", 1.5))
        self.espera_inicio_s = float(config.obter("voz.espera_inicio_s", 6.0))
        self.ruido_minimo = 1.0
        self.falou = False
        self.fala_s = 0.0               # quanto tempo com voz, ao todo
        self._inicio = time.monotonic()
        self._ultimo_som = self._inicio

    def pausa_necessaria(self) -> float:
        extra = self.extra_inicio_s if self.fala_s < self.fala_curta_s else 0.0
        return self.silencio_s + extra

    def progresso(self) -> float:
        """0 enquanto ela fala; sobe até 1 quando o silêncio chega para acabar."""
        if not self.falou:
            return 0.0
        return min(1.0, (time.monotonic() - self._ultimo_som) / self.pausa_necessaria())

    def acabou(self, amostra: np.ndarray) -> bool:
        energia = float(np.sqrt(np.mean(amostra.astype(np.float32) ** 2)))
        self.ruido_minimo = min(self.ruido_minimo, energia)
        agora = time.monotonic()
        if energia > max(CHAO_ABSOLUTO, self.ruido_minimo * 3.0):
            self._ultimo_som = agora
            self.falou = True
            self.fala_s += len(amostra) / TAXA
            return False
        if not self.falou:
            # Ainda não disse nada: dá-lhe tempo, mas não para sempre.
            return agora - self._inicio > self.espera_inicio_s
        return agora - self._ultimo_som > self.pausa_necessaria()


def _max_segundos(pedido: float | None) -> float:
    return float(pedido if pedido is not None else config.obter("voz.max_frase_s", 15.0))


def _avisar(ao_progresso, detetor: _Silencio) -> None:
    if ao_progresso is None:
        return
    try:
        ao_progresso(detetor.progresso())
    except Exception:  # noqa: BLE001 — uma luz nunca pode parar o microfone
        pass


class Escuta:
    """Os bocados de PCM de uma frase, à medida que o microfone os dá.

    É um objeto e não uma função geradora por uma razão só: quem consome
    precisa de saber **quanto pré-rolo** foi enviado, para o mini não contar
    esse tempo como "tempo em que ela esteve a falar". Um gerador não tem
    onde guardar isso.

    >>> escuta = Escuta()
    >>> for pedaco in escuta:
    ...     websocket.send(pedaco)
    >>> escuta.pre_rolo_s
    1.6
    """

    def __init__(self, max_segundos: float | None = None, silencio_s: float | None = None,
                 ao_progresso=None, ao_acabar=None) -> None:
        self.max_segundos = _max_segundos(max_segundos)
        self.silencio_s = silencio_s
        self.ao_progresso = ao_progresso
        # ⚠️ Em contínuo, quem consome isto é o WebSocket, lá dentro do
        #    cerebro.escutar(): o fim da frase acontece longe de quem chamou.
        #    É por aqui que o «ouvi» (bip + luz roxa) sai no instante certo.
        self.ao_acabar = ao_acabar
        self.falou = False
        self.pre_rolo_s = 0.0
        self.segundos = 0.0
        self._gerador = self._correr()

    def __iter__(self):
        return self._gerador

    def close(self) -> None:
        self._gerador.close()

    def _correr(self):
        if config.a_simular():
            config.sim("microfone → (simulação: nada gravado)")
            return

        from robot.voice import wakeword

        # O PRÉ-ROLO: o que já estava em buffer quando a palavra disparou.
        # Sem isto, o princípio da frase perdia-se no tempo que leva a fechar
        # um stream e abrir outro — e as crianças não esperam.
        anterior = wakeword.pre_rolo()
        wakeword.esquecer_pre_rolo()
        if anterior is not None and len(anterior):
            self.pre_rolo_s = round(len(anterior) / TAXA, 2)
            self.segundos = self.pre_rolo_s
            yield anterior.astype("<i2").tobytes()

        try:
            import sounddevice as sd
        except Exception as erro:  # noqa: BLE001
            print(f"⚠️  Microfone indisponível ({erro}).")
            return

        detetor = _Silencio(self.silencio_s)
        inicio = time.monotonic()
        try:
            with abrir_microfone(sd, "int16") as stream:
                while time.monotonic() - inicio < self.max_segundos:
                    dados, _ = stream.read(BLOCO)
                    amostra = canal_util(dados)
                    self.segundos += BLOCO / TAXA
                    yield amostra.astype("<i2").tobytes()
                    acabou = detetor.acabou(amostra.astype(np.float32) / 32768.0)
                    self.falou = detetor.falou
                    _avisar(self.ao_progresso, detetor)
                    if acabou:
                        break
            if self.ao_acabar is not None:
                try:
                    self.ao_acabar()
                except Exception:  # noqa: BLE001
                    pass
        except GeneratorExit:
            return          # quem consome desistiu: fechar o microfone e sair
        except Exception as erro:  # noqa: BLE001
            print(f"⚠️  Falha a gravar: {erro}")


def escutar_em_directo(max_segundos: float | None = None, silencio_s: float | None = None,
                       ao_progresso=None, ao_acabar=None) -> Escuta:
    """Uma frase, aos bocados, à medida que ela a diz. Ver `Escuta`."""
    return Escuta(max_segundos, silencio_s, ao_progresso, ao_acabar)


def gravar_ate_silencio(
    max_segundos: float | None = None, silencio_s: float | None = None, ao_progresso=None
) -> np.ndarray | None:
    """Grava enquanto houver voz e para depois de um bocado de silêncio.

    É o caminho do /v1/turno: junta tudo e só no fim é que há alguma coisa
    para enviar. O `escutar_em_directo()` faz o mesmo sem esperar pelo fim.
    """
    if config.a_simular():
        config.sim("microfone → (simulação: nada gravado)")
        return None

    try:
        import sounddevice as sd
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Microfone indisponível ({erro}).")
        return None

    max_segundos = _max_segundos(max_segundos)
    detetor = _Silencio(silencio_s)
    blocos: list[np.ndarray] = []
    inicio = time.monotonic()
    try:
        with abrir_microfone(sd, "float32") as stream:
            while time.monotonic() - inicio < max_segundos:
                dados, _ = stream.read(BLOCO)
                amostra = canal_util(dados)
                blocos.append(amostra.copy())
                acabou = detetor.acabou(amostra)
                _avisar(ao_progresso, detetor)
                if acabou:
                    break
    except Exception as erro:  # noqa: BLE001
        print(f"⚠️  Falha a gravar: {erro}")
        return None

    return np.concatenate(blocos) if detetor.falou and blocos else None


def gravar_wav(max_segundos: float | None = None, ao_progresso=None) -> bytes | None:
    """Grava uma frase e devolve-a já em WAV, pronta a ir para o mini."""
    from robot.brain import cerebro

    audio = gravar_ate_silencio(max_segundos, ao_progresso=ao_progresso)
    return None if audio is None else cerebro.para_wav(audio, TAXA)


def transcrever(audio: np.ndarray) -> str:
    """Áudio → texto, no mini. "" se ele não responder."""
    if audio is None or not len(audio):
        return ""
    from robot.brain import cerebro

    return cerebro.transcrever(cerebro.para_wav(audio, TAXA))


def ouvir(max_segundos: float | None = None, ao_progresso=None) -> str:
    """Grava uma frase e devolve o texto. É esta a função que se usa.

    >>> texto = ouvir()
    >>> print(texto)
    'que horas são'

    🔒 O áudio NUNCA é escrito em disco. É transcrito em memória e
       descartado no fim desta função.
    """
    if config.a_simular():
        try:
            return input("[SIM] escreve o que dirias ao robô: ").strip()
        except (EOFError, KeyboardInterrupt):
            return ""
    audio = gravar_ate_silencio(max_segundos, ao_progresso=ao_progresso)
    if audio is None:
        return ""
    return transcrever(audio)


def disponivel() -> bool:
    """Há alguma forma de perceber o que dizem? Só há uma: o mini."""
    if config.a_simular():
        return True
    from robot.brain import cerebro

    return cerebro.ligado()
