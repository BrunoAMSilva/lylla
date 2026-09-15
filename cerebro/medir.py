"""MEDIR — qual dos modelos serve, com números em vez de opiniões.

    python -m cerebro.medir                       mede o que está configurado
    python -m cerebro.medir --pensar gemma4:e2b,gemma4:e4b,gemma4:12b
    python -m cerebro.medir --ouvir mlx-community/whisper-base-mlx,…-small-mlx
    python -m cerebro.medir --so-falar

╔══════════════════════════════════════════════════════════════════════════╗
║  O QUE ESTE FICHEIRO MEDE, E PORQUÊ ESTAS COISAS                         ║
║                                                                          ║
║  A latência que conta NÃO é "tokens por segundo". É o tempo entre a      ║
║  Lara acabar de falar e o robô começar a responder — e nisso o que pesa  ║
║  é a PRIMEIRA frase, não a resposta toda. Um modelo que escreve devagar  ║
║  mas começa depressa ganha a um que faz o contrário.                     ║
║                                                                          ║
║  E mede-se a FIABILIDADE DO FORMATO: de dez perguntas, quantas devolvem  ║
║  uma resposta que o robô percebe? Um modelo bonito que falha 3 em 10 é   ║
║  um brinquedo partido — foi por isso que o gemma4 ganhou ao Mistral.     ║
║                                                                          ║
║  ⚠️ Cronometrar SÓ o que se quer medir. Já aconteceu neste projeto medir ║
║     "171 s por frase" quando 170 eram o download do modelo. Por isso há  ║
║     sempre uma volta de aquecimento que NÃO conta para a média.          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import argparse
import io
import math
import statistics
import sys
import time
import wave

from cerebro import config, falar, ouvir, pensar

# As perguntas de medição são as que a Lara faz mesmo, e cada uma exercita
# uma coisa diferente: conversa, uma ação, uma ação com argumento, uma
# pergunta sobre o que o robô vê, e uma coisa fora do âmbito.
PERGUNTAS = [
    ("Olá! Como te chamas?", None),
    ("Lylla, anda cá para a frente uns vinte centímetros.", "mover"),
    ("Segue-me até à cozinha!", "seguir"),
    ("Quem é que está aqui à minha frente?", None),
    ("Estou triste hoje.", None),
    ("Acena à avó!", "gesto"),
    ("Faz uma dança!", "dancar"),
    ("Quanto é sete vezes oito?", None),
]

CONTEXTO = {"pessoa": "Lara", "bateria_pct": 78, "distancia_cm": 120, "modo": "secretaria"}


def _barra(valor: float, maximo: float, largura: int = 24) -> str:
    if maximo <= 0:
        return ""
    return "█" * max(1, int(round(largura * valor / maximo)))


def _tom(segundos: float = 3.0, taxa: int = 16_000) -> bytes:
    """Um WAV de fala falsa — serve para medir o TEMPO, não a qualidade.

    Para medir a QUALIDADE da transcrição é preciso áudio a sério: grava com
    `python scripts/gravar_voz.py` e passa `--audio ficheiro.wav`.
    """
    import numpy as np

    t = np.linspace(0, segundos, int(taxa * segundos), endpoint=False)
    onda = 0.3 * np.sin(2 * np.pi * 140 * t) * (1 + 0.5 * np.sin(2 * np.pi * 3 * t))
    pcm = (onda * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm.tobytes())
    return buffer.getvalue()


# ------------------------------------------------------------------- ouvir


def medir_ouvir(modelos: list[str], motor: str, wav: bytes, repeticoes: int) -> None:
    print("\n🎧 OUVIR — transcrever uma frase\n")
    _, duracao = ouvir.descodificar_wav(wav)
    print(f"   áudio de {duracao:.1f} s · motor {motor} · {repeticoes} voltas + 1 de aquecimento\n")
    resultados = []
    for modelo in modelos:
        chave = {"parakeet": "modelo_parakeet", "mlx": "modelo"}.get(motor, "modelo_faster")
        config.carregar()["ouvir"][chave] = modelo
        try:
            ouvido = ouvir.Ouvido(motor)
            t = time.perf_counter()
            primeira = ouvido.transcrever_wav(wav)
            carregar = time.perf_counter() - t
            tempos = []
            for _ in range(repeticoes):
                r = ouvido.transcrever_wav(wav)
                tempos.append(r["tempo_ms"])
            mediana = statistics.median(tempos)
            resultados.append((modelo, mediana, carregar, primeira["texto"]))
        except Exception as erro:  # noqa: BLE001
            print(f"   ❌ {modelo}: {erro}")
    if not resultados:
        return
    pior = max(r[1] for r in resultados)
    print(f"   {'modelo':42} {'mediana':>9} {'RTF':>6}  {'1ª vez':>8}")
    for modelo, mediana, carregar, texto in resultados:
        rtf = (mediana / 1000) / max(duracao, 1e-6)
        print(f"   {modelo[:42]:42} {mediana:>7.0f}ms {rtf:>6.2f}  {carregar:>7.1f}s  {_barra(mediana, pior)}")
        print(f"   {'':42} «{texto[:60]}»")
    print("\n   RTF = tempo a transcrever ÷ duração do áudio. Abaixo de 0,3 é confortável.")

    # O que o streaming poupa, medido em vez de estimado.
    for modelo, *_ in resultados:
        if motor == "mlx":
            config.carregar()["ouvir"]["modelo"] = modelo
        elif motor == "parakeet":
            config.carregar()["ouvir"]["modelo_parakeet"] = modelo
        try:
            ouvido = ouvir.Ouvido(motor)
            sessao = ouvido.escutar(None)
        except Exception as erro:  # noqa: BLE001
            print(f"   ❌ {modelo}: sem escuta em contínuo ({erro})")
            continue
        if not sessao.incremental:
            print(f"   ·  {modelo}: não transcreve à medida — o /v1/escutar acumula")
            sessao.fechar()
            continue

        # Dar o áudio em bocados de 80 ms, como o microfone o dá, e medir o
        # que SOBRA depois da última palavra. É esse o número que a Lara sente.
        audio, duracao = ouvir.descodificar_wav(wav)
        bloco = int(ouvir.TAXA * 0.08)
        relogio = time.perf_counter()
        for i in range(0, len(audio), bloco):
            sessao.adicionar(audio[i:i + bloco])
        durante = (time.perf_counter() - relogio) * 1000
        relogio = time.perf_counter()
        sessao.terminar()
        depois = (time.perf_counter() - relogio) * 1000
        print(f"   ⏩ {modelo}: a transcrever durante a fala gasta {durante:.0f} ms"
              f" (espalhados por {duracao:.1f} s de fala)"
              f" e sobram {depois:.0f} ms depois de ela se calar")
        if durante < duracao * 1000:
            print(f"      → o robô acompanha a fala em tempo real. "
                  f"Poupa ~{max(0, med - depois):.0f} ms por frase.")
        else:
            print("      ⚠️  não acompanha a fala em tempo real: o áudio chega mais "
                  "depressa do que ele transcreve, e a dívida acumula.")


# ------------------------------------------------------------------ pensar


def medir_pensar(modelos: list[str], motor: str, lingua: str, repeticoes: int) -> None:
    print("\n🧠 PENSAR — a primeira frase é o que conta\n")
    print(f"   {len(PERGUNTAS)} perguntas × {repeticoes} · motor {motor} · língua {lingua}\n")
    for modelo in modelos:
        config.carregar()["pensar"]["modelo"] = modelo
        try:
            cerebro = pensar.Cerebro(motor)
        except ValueError as erro:
            print(f"   ❌ {erro}")
            return
        if not cerebro.motor.esta_ligado():
            print(f"   ❌ {modelo}: o motor não responde em {getattr(cerebro.motor, 'url', '?')}")
            continue

        print(f"   ── {modelo} ──")
        cerebro.aquecer()
        try:                       # a volta de aquecimento NÃO conta
            cerebro.responder("Olá!", CONTEXTO, sessao="aquecer", lingua=lingua)
        except pensar.CerebroIndisponivel as erro:
            print(f"   ❌ {erro}\n")
            continue

        primeiras, totais, tps = [], [], []
        boas = acertou_acao = pediu_acao = 0
        problemas: list[str] = []
        for volta in range(repeticoes):
            for pergunta, esperada in PERGUNTAS:
                cerebro.esquecer(f"medir{volta}")
                try:
                    r = cerebro.responder(pergunta, CONTEXTO, sessao=f"medir{volta}", lingua=lingua)
                except pensar.CerebroIndisponivel as erro:
                    problemas.append(str(erro)[:60])
                    continue
                ok = bool(r["fala"]) and not r["recusadas"]
                boas += ok
                if not ok and r["recusadas"]:
                    problemas.append(f"«{pergunta[:24]}» → {r['recusadas'][0][:50]}")
                if esperada:
                    pediu_acao += 1
                    acertou_acao += any(a["nome"] == esperada for a in r["acoes"])
                if r["tempo_ms"]["primeira_frase"] is not None:
                    primeiras.append(r["tempo_ms"]["primeira_frase"])
                totais.append(r["tempo_ms"]["total"])
                if r["estatisticas"].get("tokens_por_s"):
                    tps.append(r["estatisticas"]["tokens_por_s"])

        total_perguntas = len(PERGUNTAS) * repeticoes
        if primeiras:
            print(f"      1ª frase   mediana {statistics.median(primeiras):>6.0f} ms"
                  f"   pior {max(primeiras):>6.0f} ms")
        if totais:
            print(f"      resposta   mediana {statistics.median(totais):>6.0f} ms"
                  f"   pior {max(totais):>6.0f} ms")
        if tps:
            print(f"      velocidade {statistics.median(tps):>6.1f} tokens/s")
        print(f"      formato    {boas}/{total_perguntas} respostas boas"
              f"   {'✅' if boas == total_perguntas else '⚠️' if boas > total_perguntas * 0.8 else '❌'}")
        if pediu_acao:
            print(f"      ações      {acertou_acao}/{pediu_acao} certas"
                  f"   {'✅' if acertou_acao == pediu_acao else '⚠️'}")
        for problema in problemas[:4]:
            print(f"      ↯ {problema}")
        print()

    print("   A escolha: o modelo mais pequeno que acerte no formato e nas ações")
    print("   quase sempre. Rigor não é a prioridade — é um brinquedo.")


# ------------------------------------------------------------------- falar


def medir_falar(vozes: list[str], motor: str, repeticoes: int) -> None:
    print("\n🔊 FALAR — sintetizar uma frase\n")
    frase = "Olá, Lara! Que bom ver-te. Vamos brincar?"
    import tempfile

    for voz_pedida in vozes:
        try:
            voz = falar.Voz(motor, cache=tempfile.mkdtemp())
            voz.sintetizar(frase, voz_pedida)          # aquecer (e carregar o .onnx)
            tempos, tamanho = [], 0
            for i in range(repeticoes):
                t = time.perf_counter()
                audio, _ = voz.sintetizar(f"{frase} {'.' * i}", voz_pedida)
                tempos.append((time.perf_counter() - t) * 1000)
                tamanho = len(audio)
            with wave.open(io.BytesIO(audio), "rb") as w:
                segundos = w.getnframes() / w.getframerate()
            mediana = statistics.median(tempos)
            print(f"   {voz_pedida:32} {mediana:>7.0f} ms   RTF {(mediana / 1000) / segundos:>4.2f}"
                  f"   ({segundos:.1f} s de áudio, {tamanho // 1024} KB)")
        except Exception as erro:  # noqa: BLE001
            print(f"   ❌ {voz_pedida}: {erro}")
    print("\n   O que conta é o tempo da PRIMEIRA frase: é o que a Lara espera.")


# -------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Mede os modelos do cérebro.")
    p.add_argument("--ouvir", help="modelos de STT, separados por vírgulas")
    p.add_argument("--pensar", help="modelos de LLM, separados por vírgulas")
    p.add_argument("--falar", help="vozes, separadas por vírgulas")
    p.add_argument("--motor-ouvir", default=None, choices=sorted(ouvir.MOTORES))
    p.add_argument("--motor-pensar", default=None, choices=sorted(pensar.MOTORES))
    p.add_argument("--motor-falar", default=None, choices=sorted(falar.MOTORES))
    p.add_argument("--lingua", default=None, help="pt ou en (por omissão, a do robot.yaml)")
    p.add_argument("--audio", help="WAV a usar em vez do tom sintético")
    p.add_argument("-n", "--repeticoes", type=int, default=3)
    p.add_argument("--so-ouvir", action="store_true")
    p.add_argument("--so-pensar", action="store_true")
    p.add_argument("--so-falar", action="store_true")
    args = p.parse_args(argv)

    so = args.so_ouvir or args.so_pensar or args.so_falar
    from robot import config as config_robo

    lingua = args.lingua or str(config_robo.obter("lingua", "pt"))

    print("=" * 72)
    print("  MEDIR O CÉREBRO DA LYLLA")
    print("=" * 72)

    if args.so_ouvir or not so:
        motor = args.motor_ouvir or str(config.obter("ouvir.motor", "parakeet"))
        chave = {"parakeet": "ouvir.modelo_parakeet", "mlx": "ouvir.modelo"}.get(
            motor, "ouvir.modelo_faster")
        modelos = (args.ouvir or str(config.obter(chave))).split(",")
        wav = open(args.audio, "rb").read() if args.audio else _tom()
        medir_ouvir([m.strip() for m in modelos if m.strip()], motor, wav, args.repeticoes)

    if args.so_pensar or not so:
        motor = args.motor_pensar or str(config.obter("pensar.motor", "ollama"))
        modelos = (args.pensar or str(config.obter("pensar.modelo"))).split(",")
        medir_pensar([m.strip() for m in modelos if m.strip()], motor, lingua, args.repeticoes)

    if args.so_falar or not so:
        motor = args.motor_falar or str(config.obter("falar.motor", "piper"))
        vozes = (args.falar or str(config.obter("falar.voz"))).split(",")
        medir_falar([v.strip() for v in vozes if v.strip()], motor, args.repeticoes)

    print("\n" + "=" * 72)
    print("  Escrever a escolha no config/cerebro.yaml e reiniciar o serviço.")
    print("=" * 72 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
