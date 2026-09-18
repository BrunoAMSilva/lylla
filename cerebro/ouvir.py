"""OUVIR — áudio para texto, no mac mini.

╔══════════════════════════════════════════════════════════════════════════╗
║  PORQUE É QUE O WHISPER SAIU DO PI                                       ║
║                                                                          ║
║  No Pi 5 o `base` transcreve a 1-2× o tempo real, e o `small` — que é o  ║
║  primeiro que percebe bem português — fica mais lento que o tempo real.  ║
║  No M4, com MLX, o `small` demora umas décimas de segundo, e há RAM      ║
║  para o `large-v3-turbo` se quisermos. Uma frase de 3 s chega ao mini    ║
║  em ~100 KB, o que na rede de casa é nada.                               ║
║                                                                          ║
║  O Pi fica com o que tem de ser rápido E local: a palavra-chave e o      ║
║  "gravar até haver silêncio". Isso não muda.                             ║
╚══════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════╗
║  PORQUÊ O PARAKEET E NÃO O WHISPER                                       ║
║                                                                          ║
║  O `parakeet-tdt-0.6b-v3` da NVIDIA é o ÚNICO modelo aberto cujo cartão  ║
║  diz, com todas as letras, que foi treinado com **português europeu**:   ║
║                                                                          ║
║    "Performance differences may be partly attributed to Portuguese       ║
║     variant differences — our training data uses European Portuguese     ║
║     while most benchmarks use Brazilian Portuguese."                     ║
║                                                                          ║
║  Todos os outros dizem só "pt". E isso não é um detalhe neste projeto:   ║
║  o benchmark CAMÕES (arXiv 2508.19721) mede o Whisper-large-v3 a 19,2%   ║
║  de WER em português europeu, e mostra que afinar num dos portugueses    ║
║  estraga o outro (12,5% em PE → 27,2% em PB). É a mesma lição que já     ║
║  tínhamos aprendido pelo ouvido com as VOZES — o prior brasileiro é      ║
║  real — só que agora do lado de ouvir.                                   ║
║                                                                          ║
║  E há um segundo motivo, que é o que torna o streaming possível: o       ║
║  descodificador é **TDT/RNN-T**, incremental por natureza. O Whisper     ║
║  trabalha em janelas de 30 s e, para "streamar", tem de reprocessar o    ║
║  que já ouviu. O Parakeet só avança.                                     ║
╚══════════════════════════════════════════════════════════════════════════╝

Quatro motores, a mesma função:

    parakeet → parakeet-mlx, Apple Silicon. É o do mini, e o único que
               transcreve à medida que o áudio chega.
    mlx      → mlx-whisper. Fica como alternativa para comparar no medir.py.
    faster   → faster-whisper, CPU, corre em qualquer máquina.
    teste    → não ouve nada; devolve um texto fixo. Para os testes correrem
               em qualquer lado, sem descarregar um modelo.

Os que não sabem transcrever em contínuo continuam a servir o /v1/escutar:
juntam o áudio todo e transcrevem no fim (ver SessaoAcumulada). O robô não
nota a diferença — só perde a vantagem.
"""

from __future__ import annotations

import io
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from cerebro import config

TAXA = 16_000

# ⚠️ O MLX tem STREAMS POR FIO. O modelo é criado num fio e as suas operações
#    só podem ser avaliadas nesse mesmo fio — noutro qualquer rebenta com
#    "There is no Stream(cpu, 1) in current thread". O servidor é FastAPI: cada
#    pedido cai num fio diferente da pool do anyio, portanto o /v1/ouvir
#    rebentava sempre (500) enquanto o `medir.py`, que corre no fio principal,
#    passava. Não é um erro de áudio nem do Parakeet: é de onde se chama.
#
#    Um único fio para TUDO o que é MLX resolve as duas coisas de uma vez —
#    a stream é sempre a mesma, e as transcrições ficam serializadas, que é o
#    que já queríamos (o `transcribe_stream` mexe no modelo partilhado).
_FIO_MLX = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")


def no_fio_mlx(funcao, *args, **kwargs):
    """Corre `funcao` no fio do MLX e espera pelo resultado."""
    return _FIO_MLX.submit(funcao, *args, **kwargs).result()


class AudioInvalido(ValueError):
    pass


def descodificar_wav(dados: bytes) -> tuple[np.ndarray, float]:
    """Bytes de um WAV → (float32 mono a 16 kHz, duração em segundos).

    O Pi manda 16 kHz mono 16-bit, que é o que o Whisper quer. Se vier outra
    coisa (um ficheiro gravado à mão, por exemplo), convertemos aqui em vez
    de exigir ao Pi que saiba isso.
    """
    try:
        with wave.open(io.BytesIO(dados), "rb") as w:
            canais, largura, taxa, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            bruto = w.readframes(n)
    except Exception as erro:  # noqa: BLE001
        raise AudioInvalido(f"não é um WAV que eu perceba ({erro})") from erro

    if largura == 2:
        amostras = np.frombuffer(bruto, dtype="<i2").astype(np.float32) / 32768.0
    elif largura == 4:
        amostras = np.frombuffer(bruto, dtype="<i4").astype(np.float32) / 2147483648.0
    elif largura == 1:
        amostras = (np.frombuffer(bruto, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise AudioInvalido(f"WAV com {largura * 8} bits por amostra — só sei 8, 16 e 32")

    if canais > 1:
        amostras = amostras.reshape(-1, canais).mean(axis=1)
    if taxa != TAXA and len(amostras):
        # Interpolação linear: chega para voz, e evita depender do ffmpeg.
        novo_n = int(round(len(amostras) * TAXA / taxa))
        amostras = np.interp(
            np.linspace(0.0, len(amostras) - 1, novo_n, dtype=np.float64),
            np.arange(len(amostras), dtype=np.float64),
            amostras.astype(np.float64),
        ).astype(np.float32)
    return amostras, len(amostras) / TAXA


def de_pcm16(dados: bytes) -> np.ndarray:
    """PCM int16 cru (o que vem pelo WebSocket) → float32 -1..1.

    Sem cabeçalho nenhum: no streaming não há ficheiro, há uma torneira. O
    Pi manda exatamente o que o microfone lhe dá, a 16 kHz mono.
    """
    if len(dados) % 2:
        dados = dados[:-1]
    return np.frombuffer(dados, dtype="<i2").astype(np.float32) / 32768.0


def _lingua(pedida: str | None) -> str | None:
    lingua = pedida or config.obter("ouvir.lingua", "auto")
    return None if lingua in ("auto", "", None) else str(lingua)


# ---------------------------------------------------------------- os motores


class Sessao:
    """Uma escuta em curso: recebe áudio aos bocados e vai dizendo o que ouviu.

    É a interface que o /v1/escutar usa. Há duas realizações: a incremental
    (o Parakeet, que só avança) e a acumulada (todos os outros, que juntam
    tudo e transcrevem no fim).
    """

    def adicionar(self, audio: np.ndarray) -> str:
        """Mais um bocado de áudio. Devolve o texto TODO ouvido até agora."""
        raise NotImplementedError

    def terminar(self) -> str:
        """A pessoa calou-se. Devolve a transcrição final."""
        raise NotImplementedError

    def fechar(self) -> None:
        pass

    @property
    def incremental(self) -> bool:
        """True se transcreve à medida; False se só sabe fazê-lo no fim."""
        return False


class SessaoAcumulada(Sessao):
    """Junta o áudio todo e transcreve uma vez, no fim.

    Não é streaming — é o que os modelos de janela (o Whisper) sabem fazer.
    Serve para o /v1/escutar funcionar com qualquer motor: o robô manda o
    áudio à medida que grava (o que já poupa o tempo de envio), e a
    transcrição acontece toda no fim, como antes.
    """

    def __init__(self, motor: "_Base", lingua: str | None) -> None:
        self._motor = motor
        self._lingua = lingua
        self._pedacos: list[np.ndarray] = []

    def adicionar(self, audio: np.ndarray) -> str:
        self._pedacos.append(audio)
        return ""

    def terminar(self) -> str:
        if not self._pedacos:
            return ""
        junto = np.concatenate(self._pedacos)
        if len(junto) < TAXA * 0.1:
            return ""
        return self._motor.transcrever(junto, self._lingua)["texto"]


class _Base:
    nome = "?"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.modelo = "?"

    def carregar(self) -> None:  # noqa: D401 — pré-aquecer, opcional
        pass

    def transcrever(self, audio: np.ndarray, lingua: str | None) -> dict:
        raise NotImplementedError

    def sessao(self, lingua: str | None) -> Sessao:
        """Por omissão, acumular. Quem souber melhor, que redefina."""
        return SessaoAcumulada(self, lingua)

    def pronto(self) -> bool:
        return True


class MotorMLX(_Base):
    """mlx-whisper: Metal, Apple Silicon. O modelo desce do Hugging Face na
    primeira vez (uns 500 MB para o small) e fica em ~/.cache/huggingface."""

    nome = "mlx"

    def __init__(self) -> None:
        super().__init__()
        self.modelo = str(config.obter("ouvir.modelo", "mlx-community/whisper-small-mlx"))
        self._mlx = None

    def carregar(self) -> None:
        if self._mlx is None:
            import mlx_whisper  # importado aqui: só existe em Apple Silicon

            self._mlx = mlx_whisper
            # Um pedido vazio força o download e aquece o modelo — no fio do
            # MLX, pela mesma razão do Parakeet: o modelo nasce onde é usado.
            no_fio_mlx(self._mlx.transcribe, np.zeros(TAXA, dtype=np.float32),
                       path_or_hf_repo=self.modelo)

    def transcrever(self, audio: np.ndarray, lingua: str | None) -> dict:
        self.carregar()
        # A PISTA: o Whisper escreve o que acha mais provável, e «Lylla» não é
        # uma palavra que ele conheça. Um prompt inicial com o nome e o tipo
        # de frase que costuma ouvir puxa-o para «Boa noite, Lylla» em vez de
        # «Boa noite, Lila» (ou pior). Não é uma instrução — é contexto.
        pista = config.obter("ouvir.prompt_inicial") or None
        with self._lock:
            resultado = no_fio_mlx(
                self._mlx.transcribe,
                audio,
                path_or_hf_repo=self.modelo,
                language=lingua,
                initial_prompt=pista,
                fp16=True,
                condition_on_previous_text=False,
            )
        return {
            "texto": (resultado.get("text") or "").strip(),
            "lingua": resultado.get("language") or lingua or "?",
        }


class SessaoParakeet(Sessao):
    """A escuta incremental do Parakeet.

    O `transcribe_stream()` é um gestor de contexto: entra-se nele, vai-se
    dando áudio com `add_audio()`, e lê-se `result.text` a qualquer momento.
    O descodificador TDT só avança — não reprocessa o que já ouviu, que é a
    diferença toda para o Whisper.

    `context_size` é o compromisso: mais contexto à direita = melhor
    transcrição e mais atraso. (256, 256) é o valor da biblioteca; para
    frases curtas de criança podemos apertar.
    """

    def __init__(self, modelo, contexto: tuple[int, int], depth: int,
                 lock=None) -> None:
        # ⚠️ O `transcribe_stream()` MUDA O MODELO: ao entrar põe a atenção em
        #    "rel_pos_local_attn" e ao sair repõe "rel_pos". O modelo é
        #    partilhado, portanto duas escutas ao mesmo tempo estragam-se uma
        #    à outra — a segunda a fechar repõe a atenção enquanto a primeira
        #    ainda está a ouvir, e a transcrição sai lixo sem erro nenhum.
        #    Acontece de verdade: o Pi religar-se depressa, ou um curl ao
        #    /v1/ouvir durante uma escuta.
        #
        #    Uma escuta de cada vez, portanto. O robô só tem uma criança.
        self._lock = lock
        if self._lock is not None and not self._lock.acquire(timeout=5):
            raise RuntimeError("já estou a ouvir outra pessoa — só sei ouvir uma de cada vez")
        try:
            self._gestor = modelo.transcribe_stream(context_size=contexto, depth=depth)
            self._transcritor = no_fio_mlx(self._gestor.__enter__)
        except Exception:
            self._largar()
            raise
        self._ultimo = ""

        # ⚠️ JUNTAR OS BOCADOS ANTES DE OS DAR AO MODELO.
        #
        #    O microfone do Pi dá 80 ms de cada vez, e um frame de encoder do
        #    Parakeet é ~80 ms (mel de 10 ms, subamostragem 8×). Ou seja, cada
        #    `add_audio()` entregava UM frame, quando o exemplo da biblioteca
        #    usa 1 segundo. Medido a 17/09/2026, o mesmo WAV de 10 s:
        #      lote      → a frase certa, 297 ms
        #      contínuo  → «Yeah.» · «I'm not sure.» · vazio, 35 861 ms
        #
        #    São duas avarias com a mesma causa. A LENTIDÃO: cada chamada volta
        #    a correr o encoder sobre a janela em cache, e com contexto
        #    (256, 256) isso é muito trabalho — 125 vezes em vez de 10. O
        #    DISPARATE: com `depth=1` só a primeira camada tem cache exata, o
        #    resto é aproximação, e o erro acumula-se em cada FRONTEIRA entre
        #    bocados. 125 fronteiras em vez de 10.
        #
        #    A rede continua a levar 80 ms — o que muda é só o tamanho com que
        #    se alimenta o modelo.
        self._por_juntar: list[np.ndarray] = []
        self._amostras_juntas = 0
        self._minimo = max(1, int(TAXA * float(
            config.obter("ouvir.segundos_por_bocado", 1.0))))

    def _largar(self) -> None:
        if self._lock is not None:
            try:
                self._lock.release()
            except RuntimeError:
                pass
            self._lock = None

    def _mx(self, audio: np.ndarray):
        try:
            import mlx.core as mx

            return mx.array(audio.astype(np.float32))
        except ImportError:
            return audio.astype(np.float32)

    def _despejar(self) -> str:
        """Dá ao modelo tudo o que está por juntar. Devolve o texto até aqui."""
        if not self._por_juntar:
            return self._ultimo
        junto = (self._por_juntar[0] if len(self._por_juntar) == 1
                 else np.concatenate(self._por_juntar))
        self._por_juntar = []
        self._amostras_juntas = 0

        # O `mx.array` também é MLX: tem de nascer no mesmo fio que o usa.
        def _passo() -> str:
            self._transcritor.add_audio(self._mx(junto))
            return (self._transcritor.result.text or "").strip()

        self._ultimo = no_fio_mlx(_passo)
        return self._ultimo

    def adicionar(self, audio: np.ndarray) -> str:
        self._por_juntar.append(np.asarray(audio, dtype=np.float32))
        self._amostras_juntas += len(audio)
        if self._amostras_juntas < self._minimo:
            return self._ultimo     # ainda não há bocado que chegue
        return self._despejar()

    def terminar(self) -> str:
        try:
            # O resto que ficou por juntar vai agora: é o fim da frase dela, e
            # é a parte que mais falta faz.
            self._despejar()
            self._ultimo = no_fio_mlx(
                lambda: (self._transcritor.result.text or "").strip())
        finally:
            self.fechar()
        return self._ultimo

    def fechar(self) -> None:
        if self._gestor is not None:
            try:
                no_fio_mlx(self._gestor.__exit__, None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._gestor = None
        self._largar()

    @property
    def incremental(self) -> bool:
        return True


class MotorParakeet(_Base):
    """parakeet-mlx: o `parakeet-tdt-0.6b-v3` em Metal.

    Deteta a língua sozinho, o que é exatamente o que o modo inglês precisa
    (a Lara fala português, o robô responde em inglês). Por isso o parâmetro
    `lingua` é ignorado — não há como lho pedir, nem é preciso.
    """

    nome = "parakeet"

    def __init__(self) -> None:
        super().__init__()
        self.modelo = str(config.obter("ouvir.modelo_parakeet",
                                       "mlx-community/parakeet-tdt-0.6b-v3"))
        self._modelo = None

    def carregar(self) -> None:
        if self._modelo is None:
            from parakeet_mlx import from_pretrained  # só existe em Apple Silicon

            # O modelo NASCE no fio do MLX — se nascer noutro, nenhuma das
            # operações dele funciona a partir dos fios do servidor.
            self._modelo = no_fio_mlx(from_pretrained, self.modelo)

    def transcrever(self, audio: np.ndarray, lingua: str | None) -> dict:
        """⚠️ O `transcribe()` do parakeet-mlx recebe um CAMINHO de ficheiro,
        não um array — a primeira linha do corpo dele é `Path(path)`. Passar-lhe
        um array dava TypeError em todas as chamadas.

        Por isso escrevemos um WAV temporário. Custa uns milissegundos para uma
        frase de 3 s, e é o que a biblioteca espera. (O caminho em contínuo,
        que é o normal, não passa por aqui: o `add_audio()` esse recebe mesmo
        um array.)
        """
        import tempfile
        import wave

        self.carregar()
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            caminho = tmp.name
        try:
            with wave.open(caminho, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(TAXA)
                w.writeframes(pcm)
            with self._lock:
                resultado = no_fio_mlx(self._modelo.transcribe, caminho)
        finally:
            Path(caminho).unlink(missing_ok=True)
        return {"texto": (resultado.text or "").strip(), "lingua": "auto"}

    def sessao(self, lingua: str | None) -> Sessao:
        self.carregar()
        contexto = tuple(config.obter("ouvir.contexto_streaming", [256, 256]))
        return SessaoParakeet(self._modelo, contexto,
                              int(config.obter("ouvir.profundidade_streaming", 1)),
                              self._lock)


class MotorFaster(_Base):
    """faster-whisper em CPU (int8). Corre em qualquer máquina; é o que o
    Pi usa quando o mini não responde."""

    nome = "faster"

    def __init__(self) -> None:
        super().__init__()
        self.modelo = str(config.obter("ouvir.modelo_faster", "small"))
        self._whisper = None

    def carregar(self) -> None:
        if self._whisper is None:
            from faster_whisper import WhisperModel

            self._whisper = WhisperModel(self.modelo, device="cpu", compute_type="int8")

    def transcrever(self, audio: np.ndarray, lingua: str | None) -> dict:
        self.carregar()
        with self._lock:
            segmentos, info = self._whisper.transcribe(
                audio, language=lingua, beam_size=1, vad_filter=True,
                condition_on_previous_text=False,
            )
            texto = " ".join(s.text.strip() for s in segmentos).strip()
        return {"texto": texto, "lingua": getattr(info, "language", None) or lingua or "?"}


class MotorTeste(_Base):
    """Não ouve. Devolve um texto fixo — ou o que estiver em `texto_seguinte`,
    para os testes poderem dizer o que o robô "ouviu"."""

    nome = "teste"
    texto_seguinte: str | None = None

    def __init__(self) -> None:
        super().__init__()
        self.modelo = "nenhum"

    def transcrever(self, audio: np.ndarray, lingua: str | None) -> dict:
        texto = self.texto_seguinte if self.texto_seguinte is not None else "olá robô"
        self.texto_seguinte = None
        if len(audio) < TAXA * 0.2:      # menos de 200 ms de áudio: nem vale a pena
            texto = ""
        return {"texto": texto, "lingua": lingua or "pt"}

    def sessao(self, lingua: str | None) -> Sessao:
        texto = self.texto_seguinte if self.texto_seguinte is not None else "olá robô"
        self.texto_seguinte = None
        return SessaoTeste(texto)


class SessaoTeste(Sessao):
    """Finge que transcreve à medida: vai soltando mais uma palavra por cada
    bocado de áudio. É o suficiente para exercitar o caminho todo."""

    def __init__(self, texto: str) -> None:
        self._palavras = texto.split()
        self._quantas = 0

    def adicionar(self, audio: np.ndarray) -> str:
        self._quantas = min(self._quantas + 1, len(self._palavras))
        return " ".join(self._palavras[:self._quantas])

    def terminar(self) -> str:
        return " ".join(self._palavras) if self._quantas else ""

    @property
    def incremental(self) -> bool:
        return True


MOTORES = {"parakeet": MotorParakeet, "mlx": MotorMLX,
           "faster": MotorFaster, "teste": MotorTeste}


# ------------------------------------------------------------------ a fachada


class Ouvido:
    def __init__(self, motor: str | None = None) -> None:
        nome = motor or str(config.obter("ouvir.motor", "parakeet"))
        if nome not in MOTORES:
            raise ValueError(f"motor de STT desconhecido: {nome} (há {sorted(MOTORES)})")
        self.motor = MOTORES[nome]()

    def aquecer(self) -> None:
        self.motor.carregar()

    def transcrever_wav(self, dados: bytes, lingua: str | None = None) -> dict:
        """WAV → {"texto", "lingua", "duracao_s", "tempo_ms"}."""
        inicio = time.perf_counter()
        audio, duracao = descodificar_wav(dados)
        if duracao < 0.1:
            return {"texto": "", "lingua": lingua or "?", "duracao_s": round(duracao, 2), "tempo_ms": 0}
        resultado = self.motor.transcrever(audio, _lingua(lingua))
        resultado["duracao_s"] = round(duracao, 2)
        resultado["tempo_ms"] = int((time.perf_counter() - inicio) * 1000)
        return resultado

    def escutar(self, lingua: str | None = None) -> Sessao:
        """Abre uma escuta em contínuo. Ver /v1/escutar."""
        return self.motor.sessao(_lingua(lingua))

    def descricao(self) -> dict:
        return {"motor": self.motor.nome, "modelo": self.motor.modelo,
                "incremental": self.motor.nome in ("parakeet", "teste")}
