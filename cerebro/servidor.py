"""O SERVIÇO — a API HTTP do cérebro, no mac mini.

    python -m cerebro.servidor                # porta 8420, motores do config/cerebro.yaml
    python -m cerebro.servidor --teste        # sem modelo nenhum: para ver a API a andar
    python -m cerebro.servidor --pensar teste # só o LLM de mentira (STT e TTS a sério)

A API (tudo em JSON, exceto o áudio):

    GET  /v1/saude          está tudo de pé? que motores, que modelos
    GET  /v1/capacidades    o contrato: ações, caras e o esquema JSON
    POST /v1/ouvir          WAV  → {"texto": …}                     (STT)
    POST /v1/pensar         texto → {"expressao", "fala", "acoes"}  (LLM)
    POST /v1/falar          texto → WAV                             (TTS)
    POST /v1/turno          WAV ou texto → fluxo de eventos, uma linha JSON cada:
                              ouvido · expressao · frase (com áudio) · resposta · fim
    WS   /v1/escutar        o mesmo, mas com o áudio a chegar EM CONTÍNUO
    POST /v1/esquecer       apaga o histórico da conversa
    GET  /v1/memoria        o que ela sabe de cada pessoa
    POST /v1/memoria/esquecer   {"pessoa": "Lara"} apaga o que sabe dela

O /v1/turno é o que o robô usa. Os outros existem para se testar cada peça
sozinha com um `curl` — a regra da casa nº 1, aplicada à IA.

⚠️ Fica à escuta na rede local, sem senha. Qualquer computador de casa pode
   pôr o robô a falar. É uma rede doméstica; fica registado.
"""

from __future__ import annotations

import argparse
import base64
import json
import platform
import sys
import threading
import time
from typing import Any, Iterator

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from cerebro import config, falar, ouvir, pensar
from robot.brain import acoes

VERSAO = "1.0"


# ------------------------------------------------------------- os pedidos


class PedidoPensar(BaseModel):
    texto: str
    contexto: dict[str, Any] | None = None
    sessao: str = "lylla"
    lingua: str | None = None
    stream: bool = False


class PedidoFalar(BaseModel):
    texto: str
    voz: str | None = None
    velocidade: float | None = None


class PedidoTurno(BaseModel):
    texto: str
    contexto: dict[str, Any] | None = None
    sessao: str = "lylla"
    lingua: str | None = None
    voz: str | None = None
    velocidade: float | None = None


class PedidoEsquecer(BaseModel):
    sessao: str | None = None


class PedidoMemoria(BaseModel):
    pessoa: str


# ------------------------------------------------------------------ a app


def _ndjson(eventos: Iterator[dict]) -> StreamingResponse:
    def linhas():
        try:
            for evento in eventos:
                yield (json.dumps(evento, ensure_ascii=False) + "\n").encode("utf-8")
        except pensar.CerebroIndisponivel as erro:
            yield (json.dumps({"tipo": "erro", "mensagem": str(erro), "offline": True},
                              ensure_ascii=False) + "\n").encode("utf-8")
        except Exception as erro:  # noqa: BLE001 — nunca deixar o fluxo morrer calado
            yield (json.dumps({"tipo": "erro", "mensagem": str(erro)},
                              ensure_ascii=False) + "\n").encode("utf-8")

    return StreamingResponse(linhas(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


def criar_app(
    ouvido: ouvir.Ouvido | None = None,
    cerebro: pensar.Cerebro | None = None,
    voz: falar.Voz | None = None,
    aquecer: bool = False,
) -> FastAPI:
    """Monta a app. Os motores podem ser injetados (é assim que os testes
    correm com os motores `teste`, sem descarregar modelo nenhum)."""
    ouvido = ouvido or ouvir.Ouvido()
    cerebro = cerebro or pensar.Cerebro()
    voz = voz or falar.Voz()
    arranque = time.time()

    app = FastAPI(title=str(config.obter("nome", "Cérebro da Lylla")), version=VERSAO,
                  docs_url="/docs", redoc_url=None)
    app.state.ouvido, app.state.cerebro, app.state.voz = ouvido, cerebro, voz

    if aquecer:
        def _aquecer():
            for nome, motor in (("ouvir", ouvido), ("pensar", cerebro), ("falar", voz)):
                try:
                    t = time.perf_counter()
                    motor.aquecer()
                    print(f"   {nome}: pronto em {time.perf_counter() - t:.1f} s")
                except Exception as erro:  # noqa: BLE001
                    print(f"⚠️  {nome}: não consegui aquecer ({erro})")
        threading.Thread(target=_aquecer, daemon=True).start()

    # -- erros que viram respostas calmas -----------------------------------

    @app.exception_handler(pensar.CerebroIndisponivel)
    async def _offline(_req, erro):
        return JSONResponse({"erro": str(erro), "offline": True}, status_code=503)

    @app.exception_handler(falar.VozIndisponivel)
    async def _sem_voz(_req, erro):
        return JSONResponse({"erro": str(erro)}, status_code=503)

    @app.exception_handler(ouvir.AudioInvalido)
    async def _audio_mau(_req, erro):
        return JSONResponse({"erro": str(erro)}, status_code=400)

    @app.exception_handler(ValueError)
    async def _valor_mau(_req, erro):
        return JSONResponse({"erro": str(erro)}, status_code=400)

    # -- saúde e contrato ---------------------------------------------------

    @app.get("/")
    def raiz():
        return {"nome": app.title, "versao": VERSAO, "documentacao": "/docs",
                "endpoints": ["/v1/saude", "/v1/capacidades", "/v1/ouvir", "/v1/pensar",
                              "/v1/falar", "/v1/turno", "/v1/esquecer", "/v1/memoria"]}

    @app.get("/v1/saude")
    def saude():
        return {
            "ok": True,
            "nome": app.title,
            "versao": VERSAO,
            "maquina": platform.node(),
            "de_pe_ha_s": int(time.time() - arranque),
            "ouvir": ouvido.descricao(),
            "pensar": cerebro.descricao(),
            "falar": voz.descricao(),
            "sessoes": cerebro.sessoes(),
        }

    @app.get("/v1/capacidades")
    def capacidades():
        return {
            "acoes": acoes.ACOES,
            "expressoes": acoes.expressoes_disponiveis(),
            "esquema": acoes.esquema_json(),
        }

    # -- ouvir --------------------------------------------------------------

    async def _ler_audio(pedido: Request) -> tuple[bytes, dict[str, str]]:
        """Aceita o WAV cru no corpo, ou um formulário multipart com `audio`."""
        tipo = pedido.headers.get("content-type", "")
        campos: dict[str, str] = {}
        if tipo.startswith("multipart/form-data"):
            formulario = await pedido.form()
            ficheiro = formulario.get("audio")
            dados = await ficheiro.read() if ficheiro is not None and hasattr(ficheiro, "read") else b""
            campos = {k: str(v) for k, v in formulario.items() if k != "audio"}
        else:
            dados = await pedido.body()
        campos.update({k: v for k, v in pedido.query_params.items()})
        return dados, campos

    @app.post("/v1/ouvir")
    async def ouvir_endpoint(pedido: Request):
        dados, campos = await _ler_audio(pedido)
        if not dados:
            raise ValueError("falta o áudio (corpo audio/wav, ou campo multipart 'audio')")
        import anyio

        return await anyio.to_thread.run_sync(ouvido.transcrever_wav, dados, campos.get("lingua"))

    # -- pensar -------------------------------------------------------------

    @app.post("/v1/pensar")
    def pensar_endpoint(pedido: PedidoPensar, request: Request):
        quer_fluxo = pedido.stream or "application/x-ndjson" in request.headers.get("accept", "")
        if quer_fluxo:
            return _ndjson(cerebro.pensar(pedido.texto, pedido.contexto, pedido.sessao, pedido.lingua))
        return cerebro.responder(pedido.texto, pedido.contexto, pedido.sessao, pedido.lingua)

    @app.post("/v1/esquecer")
    def esquecer(pedido: PedidoEsquecer | None = None):
        cerebro.esquecer(pedido.sessao if pedido else None)
        return {"ok": True, "sessoes": cerebro.sessoes()}

    # -- memória ------------------------------------------------------------
    #
    # 🔒 AGENTS.md: «a pessoa pode ver a lista e apagar os seus dados». É isto.

    @app.get("/v1/memoria")
    def memoria_ver():
        return cerebro.memoria.tudo()

    @app.post("/v1/memoria/esquecer")
    def memoria_esquecer(pedido: PedidoMemoria):
        cerebro.memoria.esquecer(pedido.pessoa)
        cerebro.esquecer(f"lylla:{pedido.pessoa.strip().lower()}")
        return {"ok": True, "memoria": cerebro.memoria.tudo()}

    @app.post("/v1/memoria/recarregar")
    def memoria_recarregar():
        """Depois de editar o data/memoria.json à mão, sem reiniciar o serviço."""
        cerebro.memoria.recarregar()
        return cerebro.memoria.tudo()

    # -- falar --------------------------------------------------------------

    def _wav(texto: str, voz_pedida: str | None, velocidade: float | None) -> Response:
        audio, da_cache = voz.sintetizar(texto, voz_pedida, velocidade)
        return Response(audio, media_type="audio/wav",
                        headers={"X-Cache": "hit" if da_cache else "miss"})

    @app.post("/v1/falar")
    def falar_endpoint(pedido: PedidoFalar):
        return _wav(pedido.texto, pedido.voz, pedido.velocidade)

    @app.get("/v1/falar")
    def falar_get(texto: str, voz: str | None = None, velocidade: float | None = None):
        """Para testar no browser: /v1/falar?texto=Olá"""
        return _wav(texto, voz, velocidade)

    @app.post("/falar", include_in_schema=False)
    def falar_antigo(pedido: PedidoFalar):
        """O caminho do antigo scripts/servidor_voz.py, para os Pi que ainda
        tenham `voz.servidor` a apontar para cá."""
        return _wav(pedido.texto, pedido.voz, pedido.velocidade)

    # -- o turno completo ---------------------------------------------------

    def _turno(texto: str | None, audio: bytes | None, contexto: dict | None, sessao: str,
               lingua: str | None, lingua_ouvir: str | None, voz_pedida: str | None,
               velocidade: float | None) -> Iterator[dict]:
        inicio = time.perf_counter()
        tempos: dict[str, Any] = {}

        if audio:
            ouvido_r = ouvido.transcrever_wav(audio, lingua_ouvir)
            tempos["ouvir"] = ouvido_r["tempo_ms"]
            texto = ouvido_r["texto"]
            yield {"tipo": "ouvido", **ouvido_r}
            if not texto:
                yield {"tipo": "fim", "ouvido": "", "motivo": "nao_percebi",
                       "tempo_ms": {**tempos, "total": int((time.perf_counter() - inicio) * 1000)}}
                return
        if not texto:
            raise ValueError("falta o texto ou o áudio")

        tts_ms = 0
        for evento in cerebro.pensar(texto, contexto, sessao, lingua):
            if evento["tipo"] == "frase":
                t = time.perf_counter()
                try:
                    wav, _ = voz.sintetizar(evento["texto"], voz_pedida, velocidade)
                    evento = {**evento, "audio_b64": base64.b64encode(wav).decode("ascii"),
                              "formato": "wav"}
                except Exception as erro:  # noqa: BLE001 — sem voz, o texto segue na mesma
                    evento = {**evento, "audio_b64": None, "erro_voz": str(erro)}
                tts_ms += int((time.perf_counter() - t) * 1000)
                if "primeira_frase" not in tempos:
                    tempos["primeira_frase"] = int((time.perf_counter() - inicio) * 1000)
            elif evento["tipo"] == "resposta":
                tempos["pensar"] = evento.get("tempo_ms", {}).get("total")
            yield evento
        tempos["falar"] = tts_ms
        tempos["total"] = int((time.perf_counter() - inicio) * 1000)
        yield {"tipo": "fim", "tempo_ms": tempos}

    # -- escutar em contínuo ------------------------------------------------
    #
    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  PORQUE É QUE ISTO EXISTE                                            ║
    # ║                                                                      ║
    # ║  No /v1/turno a transcrição só COMEÇA quando a frase acaba: o robô   ║
    # ║  grava 3 s, envia, e só então o mini começa a trabalhar. O tempo de  ║
    # ║  transcrever fica todo no caminho crítico, à frente da resposta.     ║
    # ║                                                                      ║
    # ║  Aqui o áudio chega enquanto a Lara ainda está a falar, e o Parakeet ║
    # ║  vai transcrevendo. Quando ela se cala já quase não falta nada: o    ║
    # ║  LLM arranca praticamente no instante em que ela acaba a frase.      ║
    # ║                                                                      ║
    # ║  Quem decide que a frase acabou continua a ser o PI. É uma decisão   ║
    # ║  que não pode depender da rede — e é o Pi que tem o microfone.       ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    #
    # O protocolo, do lado de quem liga:
    #   1. abre o WebSocket
    #   2. manda UMA mensagem de texto: {"contexto": {...}, "sessao": "...",
    #      "lingua": "...", "voz": "...", "velocidade": 1.0}
    #   3. manda mensagens BINÁRIAS: PCM int16 mono 16 kHz, aos bocados
    #   4. manda {"fim": true} quando a pessoa se calar
    #   5. lê os eventos (os mesmos do /v1/turno, mais o "parcial")
    #
    # A qualquer momento pode mandar {"cancelar": true} — é assim que um
    # comando direto («pára») interrompe um turno a meio sem esperar por ele.

    @app.websocket("/v1/escutar")
    async def escutar_endpoint(ws: WebSocket):
        import anyio

        await ws.accept()
        sessao_stt = None
        inicio = time.perf_counter()
        amostras = 0
        try:
            abertura = await ws.receive_json()
        except Exception:  # noqa: BLE001
            await ws.close(code=1003)
            return

        contexto = abertura.get("contexto")
        # O pré-rolo é áudio anterior à palavra-chave: conta para transcrever,
        # mas não é "tempo que ela esteve a falar". Vem no {"fim": ...},
        # porque é só aí que o Pi sabe quanto dele enviou.
        pre_rolo_s = 0.0
        nome_sessao = abertura.get("sessao") or "lylla"
        lingua = abertura.get("lingua")
        voz_pedida = abertura.get("voz")
        velocidade = abertura.get("velocidade")

        try:
            sessao_stt = await anyio.to_thread.run_sync(ouvido.escutar,
                                                        abertura.get("lingua_ouvir"))
            await ws.send_json({"tipo": "pronto", "incremental": sessao_stt.incremental})

            texto = ""
            cancelado = False
            while True:
                mensagem = await ws.receive()
                if mensagem["type"] == "websocket.disconnect":
                    return
                dados = mensagem.get("bytes")
                if dados is not None:
                    audio = ouvir.de_pcm16(dados)
                    amostras += len(audio)
                    parcial = await anyio.to_thread.run_sync(sessao_stt.adicionar, audio)
                    if parcial and parcial != texto:
                        texto = parcial
                        await ws.send_json({"tipo": "parcial", "texto": texto})
                    continue
                pedido = json.loads(mensagem.get("text") or "{}")
                if pedido.get("cancelar"):
                    cancelado = True
                    break
                if pedido.get("fim"):
                    pre_rolo_s = float(pedido.get("pre_rolo_s") or 0.0)
                    break

            if cancelado:
                await ws.send_json({"tipo": "fim", "motivo": "cancelado"})
                return

            texto = await anyio.to_thread.run_sync(sessao_stt.terminar)
            duracao = round(max(0.0, amostras / ouvir.TAXA - pre_rolo_s), 2)
            # ⚠️ Isto conta desde que o WebSocket abriu, portanto INCLUI o tempo
            #    em que a Lara esteve a falar. Não é comparável ao "ouvir" do
            #    /v1/turno. O número que interessa é o do evento "fim": o que
            #    vai da última palavra dela à primeira dele.
            ouvir_ms = int((time.perf_counter() - inicio) * 1000)
            await ws.send_json({"tipo": "ouvido", "texto": texto, "duracao_s": duracao,
                                "tempo_ms": ouvir_ms})
            if not texto:
                await ws.send_json({"tipo": "fim", "motivo": "nao_percebi",
                                    "tempo_ms": {"ouvir": ouvir_ms, "fala_s": duracao}})
                return

            gerador = _turno(texto, None, contexto, nome_sessao, lingua, None,
                             voz_pedida, velocidade)

            # ⚠️ UM EVENTO DE CADA VEZ, e não `list(gerador)`.
            #
            #    O `list()` parecia inofensivo — é só juntar o que o gerador
            #    dá — mas corre o LLM E o TTS de TODAS as frases antes de o
            #    primeiro evento sair. Medido: a primeira frase chegava ao
            #    robô 2,4× mais tarde do que pelo /v1/turno, e a expressão
            #    chegava junto com o áudio em vez de vir à frente. Ou seja: o
            #    endpoint feito para ser mais rápido era mais lento, e
            #    anulava o próprio desenho.
            #
            #    Cada `next()` corre numa thread (é código síncrono), e o
            #    evento sai para o robô mal esteja pronto.
            iterador = iter(gerador)
            fim_do_gerador = object()

            def proximo():
                try:
                    return next(iterador)
                except StopIteration:
                    return fim_do_gerador

            while True:
                evento = await anyio.to_thread.run_sync(proximo)
                if evento is fim_do_gerador:
                    break
                if evento["tipo"] == "fim":
                    evento = {**evento,
                              "tempo_ms": {**evento.get("tempo_ms", {}),
                                           "escuta": ouvir_ms, "fala_s": duracao}}
                try:
                    await ws.send_json(evento)
                except Exception:  # noqa: BLE001
                    # O Pi desligou-se a meio — quase sempre porque um comando
                    # direto («pára») acabou o turno. Fechar o gerador em vez
                    # de o deixar correr: sem isto o mini continuava a pensar
                    # e a sintetizar para ninguém, e ainda escrevia no
                    # histórico da conversa uma resposta que nunca foi dita.
                    gerador.close()
                    return
        except WebSocketDisconnect:
            return
        except Exception as erro:  # noqa: BLE001
            try:
                await ws.send_json({"tipo": "erro", "mensagem": str(erro),
                                    "offline": True})
            except Exception:  # noqa: BLE001
                pass
        finally:
            if sessao_stt is not None:
                try:
                    sessao_stt.fechar()
                except Exception:  # noqa: BLE001
                    pass          # era a única linha do finally sem rede
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass

    @app.post("/v1/turno")
    async def turno_endpoint(pedido: Request):
        tipo = pedido.headers.get("content-type", "")
        if tipo.startswith("application/json"):
            corpo = PedidoTurno(**(await pedido.json()))
            gerador = _turno(corpo.texto, None, corpo.contexto, corpo.sessao, corpo.lingua,
                             None, corpo.voz, corpo.velocidade)
        else:
            dados, campos = await _ler_audio(pedido)
            contexto = json.loads(campos["contexto"]) if campos.get("contexto") else None
            velocidade = float(campos["velocidade"]) if campos.get("velocidade") else None
            gerador = _turno(campos.get("texto"), dados or None, contexto,
                             campos.get("sessao") or "lylla", campos.get("lingua"),
                             campos.get("lingua_ouvir"), campos.get("voz"), velocidade)
        return _ndjson(gerador)

    return app


# ------------------------------------------------------------------ arrancar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="O cérebro da Lylla — STT, LLM e TTS no mac mini.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--porta", type=int, default=None)
    parser.add_argument("--ouvir", choices=sorted(ouvir.MOTORES), default=None, help="motor de STT")
    parser.add_argument("--pensar", choices=sorted(pensar.MOTORES), default=None, help="motor de LLM")
    parser.add_argument("--falar", choices=sorted(falar.MOTORES), default=None, help="motor de TTS")
    parser.add_argument("--teste", action="store_true", help="os três motores de mentira")
    parser.add_argument("--sem-aquecer", action="store_true", help="não carregar os modelos ao arrancar")
    args = parser.parse_args(argv)

    import uvicorn

    host = args.host or str(config.obter("host", "0.0.0.0"))  # noqa: S104
    porta = args.porta or int(config.obter("porta", 8420))
    motores = {
        "ouvir": args.ouvir or ("teste" if args.teste else None),
        "pensar": args.pensar or ("teste" if args.teste else None),
        "falar": args.falar or ("teste" if args.teste else None),
    }
    try:
        app = criar_app(
            ouvir.Ouvido(motores["ouvir"]),
            pensar.Cerebro(motores["pensar"]),
            falar.Voz(motores["falar"]),
            aquecer=not args.sem_aquecer,
        )
    except ValueError as erro:
        print(f"❌ {erro}")
        return 1

    o, c, v = app.state.ouvido, app.state.cerebro, app.state.voz
    print(f"\n🧠 {app.title} de pé em http://{host}:{porta}   (documentação: /docs)")
    print(f"   ouvir:  {o.motor.nome} · {o.motor.modelo}")
    print(f"   pensar: {c.motor.nome} · {c.motor.modelo}"
          f"{'' if c.motor.esta_ligado() else '   ⚠️ o modelo não responde'}")
    print(f"   falar:  {v.motor_omissao} · {v.voz_omissao} · cache em {v.cache}")
    print(f"\n   No Pi, no config/robot.yaml:\n     cerebro:\n       url: \"http://{platform.node()}:{porta}\"")
    print("\n   Ctrl-C para parar.\n")
    uvicorn.run(app, host=host, port=porta, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
