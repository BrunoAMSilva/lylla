"""O CLIENTE DO CÉREBRO — o lado do Pi.

╔══════════════════════════════════════════════════════════════════════════╗
║  UM TURNO, UMA LIGAÇÃO                                                   ║
║                                                                          ║
║  O Pi grava a frase e manda o WAV ao mac mini. Em vez de esperar pela    ║
║  resposta toda, lê os eventos à medida que chegam:                       ║
║                                                                          ║
║    ouvido    → o que a Lara disse (o Whisper já acabou)                  ║
║    expressao → muda os olhos JÁ, antes de a primeira palavra sair        ║
║    frase     → uma frase, com o WAV dela pronto a tocar                  ║
║    resposta  → a fala toda e as ações a executar                         ║
║    fim       → tempos                                                    ║
║                                                                          ║
║  Enquanto o robô toca a primeira frase, o mini ainda está a escrever a   ║
║  segunda. É esta sobreposição que faz a diferença entre uma conversa e   ║
║  um formulário.                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝

Se o mini estiver desligado, `turno()` levanta `SemCerebro` e quem chama trata
disso. O robô continua a reconhecer pessoas no Pi e pode tocar frases que já
estejam em cache. Não entende novas ordens faladas.
"""

from __future__ import annotations

import base64
import io
import json
import threading
import wave
from typing import Iterator

import requests

from robot import config

TAXA = 16_000


class SemCerebro(RuntimeError):
    """O mac mini não respondeu."""


_avisado = False


def base_url() -> str:
    """O endereço do mini. `cerebro.url` no robot.yaml."""
    url = config.obter("cerebro.url", "http://mac.local:8420")
    return str(url).rstrip("/")


def _url(caminho: str) -> str:
    return f"{base_url()}{caminho}"


def _timeout(chave: str, omissao: float) -> float:
    return float(config.obter(f"cerebro.{chave}", omissao))


def ligado(timeout: float | None = None) -> bool:
    """O mini está de pé? Pergunta rápida, sem levantar nada."""
    if config.a_simular():
        return True
    try:
        r = requests.get(_url("/v1/saude"), timeout=timeout or _timeout("timeout_saude_s", 2))
        return r.status_code == 200
    except requests.RequestException:
        return False


def saude() -> dict | None:
    try:
        r = requests.get(_url("/v1/saude"), timeout=_timeout("timeout_saude_s", 2))
        return r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def _avisar(erro: Exception) -> None:
    """Queixa-se UMA vez, não a cada frase — senão o terminal enche-se."""
    global _avisado
    if not _avisado:
        _avisado = True
        print(f"⚠️  O cérebro não respondeu em {base_url()} ({erro}).")
        print("    No mini:  python -m cerebro.servidor")


def _ok() -> None:
    global _avisado
    _avisado = False


# --------------------------------------------------------------------- áudio


def para_wav(audio, taxa: int = TAXA) -> bytes:
    """float32 (-1..1) ou int16 → bytes de um WAV mono. É isto que vai na rede.

    3 segundos de fala são ~96 KB. Numa rede de casa, um piscar de olhos.
    """
    import numpy as np

    amostras = np.asarray(audio)
    if amostras.dtype != np.int16:
        amostras = np.clip(amostras, -1.0, 1.0)
        amostras = (amostras * 32767.0).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(amostras.tobytes())
    return buffer.getvalue()


# ------------------------------------------------------------------ os pedidos


def de_wav(dados: bytes):
    """WAV → float32 (-1..1). O caminho de volta do para_wav().

    ⚠️ Pelo módulo `wave`, não a cortar 44 bytes de cabeçalho. Um WAV pode
       trazer blocos extra (LIST, INFO, fact) antes dos dados, e nesse caso
       os "44 bytes" cortam pelo sítio errado: o áudio sai deslocado e o
       Whisper transcreve ruído — sem erro nenhum, que é a pior maneira de
       uma coisa falhar.
    """
    import numpy as np

    with wave.open(io.BytesIO(dados), "rb") as w:
        largura = w.getsampwidth()
        canais = w.getnchannels()
        bruto = w.readframes(w.getnframes())
    if largura != 2:
        raise ValueError(f"esperava 16 bits por amostra, veio {largura * 8}")
    amostras = np.frombuffer(bruto, dtype="<i2").astype(np.float32) / 32768.0
    return amostras.reshape(-1, canais).mean(axis=1) if canais > 1 else amostras


def transcrever(wav: bytes, lingua: str | None = None) -> str:
    """WAV → texto. "" se não der (nunca levanta)."""
    try:
        r = requests.post(
            _url("/v1/ouvir"),
            data=wav,
            headers={"Content-Type": "audio/wav"},
            params={"lingua": lingua} if lingua else None,
            timeout=_timeout("timeout_ouvir_s", 20),
        )
        r.raise_for_status()
        _ok()
        return (r.json().get("texto") or "").strip()
    except (requests.RequestException, ValueError) as erro:
        _avisar(erro)
        return ""


def sintetizar(texto: str, voz: str | None = None, velocidade: float | None = None) -> bytes | None:
    """Texto → bytes de um WAV. None se não der (nunca levanta).

    Quem guarda isto em disco é o speak.py — a cache é dele, e é o que faz o
    robô continuar a falar com o mini desligado.
    """
    corpo: dict = {"texto": texto}
    if voz:
        corpo["voz"] = voz
    if velocidade:
        corpo["velocidade"] = velocidade
    try:
        r = requests.post(_url("/v1/falar"), json=corpo, timeout=_timeout("timeout_falar_s", 10))
        r.raise_for_status()
        _ok()
        return r.content or None
    except requests.RequestException as erro:
        _avisar(erro)
        return None


def turno(
    wav: bytes | None = None,
    texto: str | None = None,
    contexto: dict | None = None,
    sessao: str = "lylla",
) -> Iterator[dict]:
    """Um turno completo. Gera os eventos à medida que o mini os manda.

    Os eventos "frase" trazem o áudio já em bytes (o campo `audio`), não em
    base64 — quem chama só tem de o tocar.
    """
    if wav is None and not texto:
        raise ValueError("é preciso o áudio ou o texto")

    try:
        if wav is not None:
            campos = {"sessao": sessao}
            if contexto:
                campos["contexto"] = json.dumps(contexto, ensure_ascii=False)
            if texto:
                campos["texto"] = texto
            resposta = requests.post(
                _url("/v1/turno"),
                files={"audio": ("fala.wav", wav, "audio/wav")},
                data=campos,
                stream=True,
                timeout=(_timeout("timeout_ligar_s", 3), _timeout("timeout_turno_s", 60)),
            )
        else:
            resposta = requests.post(
                _url("/v1/turno"),
                json={"texto": texto, "contexto": contexto, "sessao": sessao},
                stream=True,
                timeout=(_timeout("timeout_ligar_s", 3), _timeout("timeout_turno_s", 60)),
            )
        resposta.raise_for_status()
    except requests.RequestException as erro:
        _avisar(erro)
        raise SemCerebro(str(erro)) from erro

    _ok()
    try:
        # ⚠️ O `close()` no fim não é arrumação: quem chama pode sair a meio
        #    (um comando direto no meio da frase, por exemplo) e sem isto a
        #    ligação ficava aberta e o mini a sintetizar para o vazio.
        for linha in resposta.iter_lines():
            if not linha:
                continue
            try:
                evento = json.loads(linha)
            except ValueError:
                continue
            if evento.get("tipo") == "erro":
                raise SemCerebro(evento.get("mensagem", "erro no cérebro"))
            if evento.get("audio_b64"):
                evento["audio"] = base64.b64decode(evento.pop("audio_b64"))
            yield evento
    except requests.RequestException as erro:
        # A ligação caiu a meio: quem chama já disse as frases que recebeu.
        _avisar(erro)
        raise SemCerebro(str(erro)) from erro
    finally:
        resposta.close()


# ------------------------------------------------------------------ escutar


def escutar(
    pedacos,
    contexto: dict | None = None,
    sessao: str = "lylla",
    cancelar=None,
) -> Iterator[dict]:
    """Um turno com o áudio a ir EM CONTÍNUO, pelo WebSocket.

    `pedacos` é um gerador de PCM int16 mono a 16 kHz (o
    `listen.escutar_em_directo()`). Vai-se mandando à medida que a Lara fala;
    o mini transcreve ao mesmo tempo, e quando o gerador acabar — é ele que
    deteta o silêncio — o LLM arranca quase de imediato.

    `cancelar` é uma função sem argumentos: se devolver True a meio, o turno
    é interrompido no mini (é assim que um «pára» não fica à espera).

    Gera os mesmos eventos do turno(), mais:
        {"tipo": "pronto",  "incremental": bool}   ← o mini abriu a escuta
        {"tipo": "parcial", "texto": "..."}        ← o que já se percebeu

    ⚠️ Uma thread manda o áudio, esta lê os eventos. Tem de ser: o mini
       responde com parciais ENQUANTO recebe, e um só fio de execução a
       alternar entre enviar e ler ficaria bloqueado no primeiro dos dois.
    """
    try:
        import websocket  # websocket-client, síncrono
    except ImportError as erro:  # pragma: no cover
        raise SemCerebro(f"falta o websocket-client no Pi ({erro})") from erro

    url = base_url().replace("http://", "ws://").replace("https://", "wss://")

    # ⚠️ Ligar com o tempo CURTO, e só depois alargar para o do turno.
    #
    #    O `create_connection` usa o mesmo `timeout` para abrir a ligação e
    #    para esperar por dados, e o `websocket-client` engole em silêncio as
    #    opções que não conhece (um `open_timeout=` não dá erro nenhum, não
    #    faz nada). Contra um mini que aceita o TCP mas não responde ao
    #    handshake — a carregar o modelo, em swap, preso num turno anterior —
    #    o robô ficava os 60 s do turno parado e calado à frente da criança.
    #    E durante esse tempo o motors.verificar_timeout() não corre.
    try:
        ligacao = websocket.create_connection(
            f"{url}/v1/escutar", timeout=_timeout("timeout_ligar_s", 3))
        ligacao.settimeout(_timeout("timeout_turno_s", 60))
    except Exception as erro:  # noqa: BLE001
        _avisar(erro)
        raise SemCerebro(str(erro)) from erro

    _ok()
    # ⚠️ Guardar o TEXTO do erro, não o objeto: a excepção segura o traceback,
    #    que segura o frame do enviar(), que segura o gerador de áudio — e o
    #    gerador segura o microfone ABERTO até o coletor de ciclos passar. A
    #    volta seguinte do ciclo principal tentava abrir o microfone outra vez
    #    para a palavra-chave e apanhava "Device unavailable".
    problema: list[str] = []

    def enviar() -> None:
        try:
            ligacao.send(json.dumps({"contexto": contexto, "sessao": sessao},
                                    ensure_ascii=False))
            for pedaco in pedacos:
                if cancelar is not None and cancelar():
                    ligacao.send(json.dumps({"cancelar": True}))
                    return
                ligacao.send_binary(pedaco)
            # O pré-rolo vai no FIM e não na abertura: só aqui é que já se
            # sabe quanto dele foi mesmo enviado (ver listen.Escuta). Sem
            # isto, o mini contava os 1,6 s de pré-rolo como tempo em que a
            # Lara esteve a falar, e o número que serve para afinar tudo saía
            # sempre inflacionado.
            ligacao.send(json.dumps(
                {"fim": True, "pre_rolo_s": float(getattr(pedacos, "pre_rolo_s", 0.0))}))
        except Exception as erro:  # noqa: BLE001
            problema.append(f"{type(erro).__name__}: {erro}")
            try:
                ligacao.close()
            except Exception:  # noqa: BLE001
                pass

    fio = threading.Thread(target=enviar, name="lylla-enviar-audio", daemon=True)
    fio.start()

    try:
        while True:
            try:
                bruto = ligacao.recv()
            except Exception as erro:  # noqa: BLE001
                if problema:
                    raise SemCerebro(problema[0]) from erro
                raise SemCerebro(str(erro)) from erro
            if not bruto:
                # ⚠️ O websocket-client devolve "" quando recebe um CLOSE, e
                #    NÃO levanta. Sem esta verificação, uma falha do lado do
                #    envio (o mini a reiniciar, um socket meio-aberto) fazia o
                #    escutar() acabar como se tivesse corrido bem: o robô
                #    dizia «Não percebi, podes repetir?» — a culpar a criança
                #    de um problema de rede — em vez da frase que tem em
                #    cache e que funciona sem rede nenhuma.
                if problema:
                    raise SemCerebro(problema[0])
                break
            if isinstance(bruto, bytes):
                bruto = bruto.decode("utf-8", errors="replace")
            try:
                evento = json.loads(bruto)
            except ValueError:
                continue
            if evento.get("tipo") == "erro":
                raise SemCerebro(evento.get("mensagem", "erro no cérebro"))
            if evento.get("audio_b64"):
                evento["audio"] = base64.b64decode(evento.pop("audio_b64"))
            yield evento
            if evento.get("tipo") == "fim":
                break
    finally:
        try:
            ligacao.close()
        except Exception:  # noqa: BLE001
            pass
        fio.join(timeout=1)
        # ⚠️ FECHAR O MICROFONE, explicitamente.
        #
        #    O `pedacos` é o gerador do listen.escutar_em_directo(), e enquanto
        #    ele não fechar o `sd.InputStream` fica ABERTO. Não basta largá-lo:
        #    quando isto sai por uma excepção, o traceback segura o frame desta
        #    função, que segura o gerador — e ele só fecha quando o coletor de
        #    ciclos passar, que pode ser daqui a muito tempo.
        #
        #    A volta seguinte do ciclo principal abre o microfone outra vez
        #    para a palavra-chave. Com o anterior ainda aberto, o Pi responde
        #    "Device unavailable" e o robô deixa de responder ao «Olá robô».
        try:
            pedacos.close()
        except AttributeError:
            pass          # não era um gerador (uma lista, nos testes)
        except Exception:  # noqa: BLE001
            pass


def esquecer(sessao: str | None = None) -> None:
    """Apaga o histórico da conversa no mini."""
    try:
        requests.post(_url("/v1/esquecer"), json={"sessao": sessao},
                      timeout=_timeout("timeout_saude_s", 2))
    except requests.RequestException:
        pass
