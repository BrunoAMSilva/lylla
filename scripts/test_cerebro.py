#!/usr/bin/env python3
"""TESTAR O CÉREBRO — a peça de IA sozinha, como manda a regra da casa nº 1.

    python scripts/test_cerebro.py                 a conversar, à mão
    python scripts/test_cerebro.py "segue-me!"     uma frase e sai
    python scripts/test_cerebro.py --saude         só ver se está de pé
    python scripts/test_cerebro.py --ouvir f.wav   mandar um WAV gravado
    python scripts/test_cerebro.py --executar      FAZER mesmo as ações

⚠️ Por omissão as ações NÃO são executadas — só se mostram. Isto corre muitas
   vezes no portátil, longe do robô, e um `mover` executado por engano com o
   robô em cima da mesa acaba mal. `--executar` liga-as.

Não é preciso microfone: escreve-se o que se diria. É a forma de experimentar
o cérebro todo hoje, com o robô ainda por montar.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402
from robot.brain import cerebro, comandos_diretos, contexto  # noqa: E402


def _saude() -> bool:
    dados = cerebro.saude()
    print(f"\n🧠 {cerebro.base_url()}")
    if not dados:
        print("   ❌ não responde.\n")
        print("   No mini:  python -m cerebro.servidor")
        print("   Sem o mini à mão, para ver a API a andar aqui mesmo:")
        print("     python -m cerebro.servidor --teste\n")
        return False
    print(f"   ✅ {dados['nome']} · {dados['maquina']} · de pé há {dados['de_pe_ha_s']} s")
    print(f"      ouvir   {dados['ouvir']['motor']:8} {dados['ouvir']['modelo']}")
    print(f"      pensar  {dados['pensar']['motor']:8} {dados['pensar']['modelo']}"
          f"{'' if dados['pensar']['ligado'] else '   ⚠️ o modelo não responde'}")
    print(f"      falar   {dados['falar']['motor']:8} {dados['falar']['voz']}"
          f"   ({dados['falar']['em_cache']} frases em cache)")
    print()
    return True


def _turno(texto: str | None, wav: bytes | None, executar: bool, tocar: bool) -> None:
    ctx = contexto.montar()
    print(f"   contexto: {ctx}")
    inicio = time.perf_counter()
    acoes: list[dict] = []
    try:
        for evento in cerebro.turno(wav=wav, texto=texto, contexto=ctx):
            ms = int((time.perf_counter() - inicio) * 1000)
            tipo = evento["tipo"]
            if tipo == "ouvido":
                print(f"   [{ms:>5} ms] 👤 «{evento['texto']}»  ({evento['duracao_s']} s de áudio)")
            elif tipo == "expressao":
                print(f"   [{ms:>5} ms] 👀 {evento['nome']}")
            elif tipo == "frase":
                audio = evento.get("audio")
                print(f"   [{ms:>5} ms] 🤖 «{evento['texto']}»"
                      f"{f'  ({len(audio) // 1024} KB)' if audio else '  (sem áudio)'}")
                if tocar and audio:
                    from robot.voice import speak

                    speak.tocar(audio, esperar=False)
            elif tipo == "resposta":
                acoes = evento.get("acoes", [])
                for razao in evento.get("recusadas", []):
                    print(f"   [{ms:>5} ms] ↯ recusei: {razao}")
            elif tipo == "fim":
                t = evento.get("tempo_ms", {})
                print(f"   [{ms:>5} ms] ⏱️  ouvir {t.get('ouvir', 0)} · pensar {t.get('pensar', 0)}"
                      f" · falar {t.get('falar', 0)} · 1ª frase {t.get('primeira_frase', '?')}")
    except cerebro.SemCerebro as erro:
        print(f"   ❌ {erro}")
        return

    if tocar:
        from robot.voice import speak

        speak.esperar_acabar()

    for acao in acoes:
        if executar:
            from robot.brain import tools

            print(f"   ⚙️  {acao['nome']}({acao['argumentos']}) → {tools.executar(acao['nome'], acao['argumentos'])}")
        else:
            print(f"   ⚙️  {acao['nome']}({acao['argumentos']})   (não executada — usa --executar)")


def _escutar(caminho: Path, executar: bool, tocar: bool) -> None:
    """Manda um WAV como se estivesse a ser dito AGORA, e mostra os tempos.

    É a única forma de ver o ganho do streaming sem microfone: o áudio sai em
    bocados de 80 ms, em tempo real, e o mini vai transcrevendo. Repara em
    quantos parciais aparecem ANTES do «ouvido» — cada um é trabalho que já
    não fica para o fim.
    """
    import time
    import wave

    with wave.open(str(caminho), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != 16_000:
            print(f"   ⚠️  {caminho.name} não é 16 kHz mono 16-bit — o robô manda assim.")
        quadros = w.readframes(w.getnframes())
        duracao = w.getnframes() / w.getframerate()

    bloco = 16_000 * 2 * 80 // 1000        # 80 ms de int16 mono
    print(f"   {duracao:.1f} s de áudio · {len(quadros) // bloco} bocados\n")

    def pedacos():
        for i in range(0, len(quadros), bloco):
            time.sleep(0.08)               # em tempo real, como o microfone
            yield quadros[i:i + bloco]

    ctx = contexto.montar()
    inicio = time.perf_counter()
    parciais = 0
    acoes: list[dict] = []
    try:
        for evento in cerebro.escutar(pedacos(), contexto=ctx):
            ms = int((time.perf_counter() - inicio) * 1000)
            tipo = evento["tipo"]
            if tipo == "pronto":
                print(f"   [{ms:>5} ms] 🎧 escuta aberta"
                      f"{' (transcreve à medida)' if evento['incremental'] else ' (só no fim)'}")
            elif tipo == "parcial":
                parciais += 1
                print(f"   [{ms:>5} ms] … «{evento['texto']}»")
            elif tipo == "ouvido":
                print(f"   [{ms:>5} ms] 👤 «{evento['texto']}»")
            elif tipo == "expressao":
                print(f"   [{ms:>5} ms] 👀 {evento['nome']}")
            elif tipo == "frase":
                audio = evento.get("audio")
                print(f"   [{ms:>5} ms] 🤖 «{evento['texto']}»"
                      f"{f'  ({len(audio) // 1024} KB)' if audio else ''}")
                if tocar and audio:
                    from robot.voice import speak

                    speak.tocar(audio, esperar=False)
            elif tipo == "resposta":
                acoes = evento.get("acoes", [])
            elif tipo == "fim":
                t = evento.get("tempo_ms", {})
                print(f"\n   ⏱️  a Lara falou {t.get('fala_s', duracao)} s")
                print(f"       da última palavra dela à primeira dele: "
                      f"{t.get('primeira_frase', '?')} ms")
                print(f"       {parciais} transcrições parciais durante a fala"
                      f"{' — trabalho que não ficou para o fim' if parciais else ''}")
    except cerebro.SemCerebro as erro:
        print(f"   ❌ {erro}")
        return

    if tocar:
        from robot.voice import speak

        speak.esperar_acabar()
    for acao in acoes:
        if executar:
            from robot.brain import tools

            print(f"   ⚙️  {acao['nome']} → {tools.executar(acao['nome'], acao['argumentos'])}")
        else:
            print(f"   ⚙️  {acao['nome']}({acao['argumentos']})   (não executada)")


def main() -> int:
    p = argparse.ArgumentParser(description="Testa o cérebro no mac mini.")
    p.add_argument("frase", nargs="*", help="o que dirias ao robô")
    p.add_argument("--saude", action="store_true", help="só verificar e sair")
    p.add_argument("--ouvir", metavar="WAV", help="mandar um ficheiro WAV gravado")
    p.add_argument("--escutar", metavar="WAV",
                   help="o mesmo, mas EM CONTÍNUO — como se estivesses a falar agora")
    p.add_argument("--executar", action="store_true", help="fazer mesmo as ações")
    p.add_argument("--tocar", action="store_true", help="tocar o áudio das respostas")
    p.add_argument("--esquecer", action="store_true", help="limpar a conversa e sair")
    args = p.parse_args()

    if args.esquecer:
        cerebro.esquecer()
        print("   memória limpa.")
        return 0

    if not _saude():
        return 1
    if args.saude:
        return 0

    if args.executar and not config.a_simular():
        print("   ⚠️  as ações VÃO ser executadas no robô a sério.\n")

    if args.escutar:
        caminho = Path(args.escutar)
        if not caminho.is_file():
            print(f"❌ não há o ficheiro {caminho}")
            return 1
        print(f"→ {caminho.name}, em contínuo (bocados de 80 ms, como o microfone dá)\n")
        _escutar(caminho, args.executar, args.tocar)
        return 0

    if args.ouvir:
        caminho = Path(args.ouvir)
        if not caminho.is_file():
            print(f"❌ não há o ficheiro {caminho}")
            return 1
        print(f"→ {caminho.name}")
        _turno(None, caminho.read_bytes(), args.executar, args.tocar)
        return 0

    if args.frase:
        texto = " ".join(args.frase)
        print(f"→ «{texto}»")
        _turno(texto, None, args.executar, args.tocar)
        return 0

    print("Escreve o que dirias ao robô. Ctrl-C para sair.\n")
    while True:
        try:
            texto = input("👤 ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n   Adeus.\n")
            return 0
        if not texto:
            continue
        directa = comandos_diretos.tentar(texto)
        if directa is not None:
            print(f"   ⚡ comando direto (nem chega ao cérebro) → {directa}\n")
            continue
        _turno(texto, None, args.executar, args.tocar)
        print()


if __name__ == "__main__":
    sys.exit(main())
