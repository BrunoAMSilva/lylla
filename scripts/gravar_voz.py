#!/usr/bin/env python3
"""GRAVAR A VOZ DO ROBÔ — o guião, o microfone e a paciência.

    python scripts/gravar_voz.py --quem bruno        # grava (continua de onde parou)
    python scripts/gravar_voz.py --quem bruno --verificar
    python scripts/gravar_voz.py --dispositivos      # que microfones há

## Porque é que isto existe

A voz da GLaDOS e a voz `tugão` que a Lara rejeitou são o MESMO modelo: Piper,
VITS, 63 MB, o mesmo ficheiro de configuração até nos três números de inferência.
Uma soa a atriz profissional, a outra a papa. A diferença não é a arquitetura —
é que uma foi treinada com horas de estúdio e a outra com 1,5 h gravadas pelo
browser em WEBM comprimido.

Não há áudio bom de português europeu para descarregar. Mas há aqui alguém que
fala português europeu e um microfone. É isso que este script recolhe.

## O que sai daqui

    data/gravacoes/<quem>/
        bruto/0001.wav       48 kHz, por cortar — o original, nunca se apaga
        wavs/0001.wav        22050 Hz mono, aparado — é o que vai para o treino
        metadata.csv         0001.wav|A frase que foi lida.

O formato é o que o `piper.train fit` come. Grava-se a 48 kHz e guarda-se a
22050 porque re-gravar uma pessoa é caro e disco é barato: se um dia quisermos
treinar um modelo de qualidade `high` a 24 kHz, o original ainda cá está.

## Como correr uma sessão

Enter começa a gravar, Enter outra vez pára, e a seguir ouves. Se não gostares,
`r` repete. Não tentes fazer isto tudo de uma vez — vinte minutos de cada vez,
sempre no mesmo sítio, com o mesmo microfone e à mesma distância. A consistência
conta mais do que o número de frases.

Regras que valem mais do que qualquer definição:
  · sempre o mesmo quarto, o mesmo microfone, a mesma distância (um palmo)
  · janelas fechadas, frigorífico longe, telemóvel noutra divisão
  · ler com energia normal, como se estivesses a falar com alguém
  · se te enganares, repete a frase inteira — não emendes a meio
  · se te apetecer tossir, tosse ANTES de carregar no Enter
"""

from __future__ import annotations

import argparse
import array
import csv
import shutil
import subprocess
import sys
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
GUIAO = RAIZ / "config" / "guiao_voz.txt"
GRAVACOES = RAIZ / "data" / "gravacoes"

TAXA_BRUTO = 48000
TAXA_TREINO = 22050
MARGEM_S = 0.08          # silêncio que se deixa antes e depois de aparar
LIMIAR_CORTE = 0.02      # abaixo disto conta como silêncio
PICO_MAXIMO = 0.98       # acima disto está a cortar (clipping)
RUIDO_BOM = 0.006        # chão de ruído aceitável


# --------------------------------------------------------------------- áudio


def ler_amostras(caminho: Path) -> tuple[array.array, int]:
    with wave.open(str(caminho), "rb") as f:
        if f.getsampwidth() != 2:
            raise ValueError("esperava 16 bits por amostra")
        dados = array.array("h")
        dados.frombytes(f.readframes(f.getnframes()))
        return dados, f.getframerate()


def analisar(caminho: Path) -> dict[str, float]:
    """Pico, energia e chão de ruído. Sem numpy, para não obrigar a instalar nada."""
    amostras, taxa = ler_amostras(caminho)
    if not amostras:
        return {"duracao": 0.0, "pico": 0.0, "rms": 0.0, "ruido": 0.0,
                "inicio": 0.0, "fim": 0.0}

    pico = max(abs(v) for v in amostras) / 32768.0
    soma = sum(v * v for v in amostras)
    rms = (soma / len(amostras)) ** 0.5 / 32768.0

    # Chão de ruído: a janela de 100 ms mais silenciosa do clip. Se a pessoa
    # respirou fundo antes de começar, é aí que se vê.
    janela = int(taxa * 0.1)
    ruido = rms
    for inicio in range(0, max(len(amostras) - janela, 1), janela):
        pedaco = amostras[inicio:inicio + janela]
        if not pedaco:
            continue
        energia = (sum(v * v for v in pedaco) / len(pedaco)) ** 0.5 / 32768.0
        ruido = min(ruido, energia)

    # Onde é que a fala começa e acaba de facto
    limiar = max(LIMIAR_CORTE, ruido * 3) * 32768
    primeiro, ultimo = 0, len(amostras) - 1
    while primeiro < ultimo and abs(amostras[primeiro]) < limiar:
        primeiro += 1
    while ultimo > primeiro and abs(amostras[ultimo]) < limiar:
        ultimo -= 1

    return {
        "duracao": len(amostras) / taxa,
        "pico": pico,
        "rms": rms,
        "ruido": ruido,
        "inicio": max(primeiro / taxa - MARGEM_S, 0.0),
        "fim": min(ultimo / taxa + MARGEM_S, len(amostras) / taxa),
    }


def chao_de_ruido(bruto: Path) -> float:
    """A sala, medida no silêncio ANTES de a fala começar.

    Isto tem de ser feito no ficheiro bruto. Uma versão anterior media a janela
    mais silenciosa do ficheiro já aparado — e num clip curto sem pausas essa
    janela não é a sala, é uma consoante fraca. Dava chãos de ruído dez a cem
    vezes acima do real e mandava regravar gravações boas.
    """
    amostras, taxa = ler_amostras(bruto)
    if not amostras:
        return 0.0
    medidas = analisar(bruto)
    fim_do_silencio = int(max(medidas["inicio"] - MARGEM_S, 0.0) * taxa)
    if fim_do_silencio < taxa * 0.05:          # menos de 50 ms: não dá para medir
        return analisar(bruto)["ruido"]
    silencio = amostras[:fim_do_silencio]
    return (sum(v * v for v in silencio) / len(silencio)) ** 0.5 / 32768.0


def comentar(medidas: dict[str, float]) -> list[str]:
    avisos = []
    fala = medidas["fim"] - medidas["inicio"]
    if medidas["pico"] >= PICO_MAXIMO:
        avisos.append("está a CORTAR (clipping) — afasta-te um pouco do microfone")
    elif medidas["pico"] < 0.15:
        avisos.append("muito baixinho — chega-te ao microfone ou sobe o ganho")
    if medidas["ruido"] > RUIDO_BOM:
        avisos.append(f"chão de ruído alto ({medidas['ruido']:.4f}) — algo está a fazer barulho")
    if fala < 0.4:
        avisos.append("quase não há fala aqui — falhou a gravação?")
    return avisos


# ------------------------------------------------------------------ gravação


def dispositivos() -> int:
    if not shutil.which("ffmpeg"):
        print("❌ falta o ffmpeg:  brew install ffmpeg")
        return 1
    print("\nEntradas de áudio (usa o índice em --dispositivo, ex: \":1\"):\n")
    resultado = subprocess.run(
        ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True, text=True, check=False,
    )
    a_mostrar = False
    for linha in resultado.stderr.splitlines():
        if "audio devices" in linha:
            a_mostrar = True
            continue
        if a_mostrar and "]" in linha:
            print("   " + linha.split("] ", 1)[-1])
    print()
    return 0


def gravar_bruto(destino: Path, dispositivo: str) -> bool:
    processo = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "avfoundation", "-i", dispositivo,
         "-ar", str(TAXA_BRUTO), "-ac", "1", str(destino), "-loglevel", "error"],
        stdin=subprocess.PIPE,
    )
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass
    try:
        processo.communicate(input=b"q", timeout=10)
    except subprocess.TimeoutExpired:
        processo.terminate()
        processo.wait(timeout=5)
    return destino.is_file() and destino.stat().st_size > 1000


def aparar(bruto: Path, destino: Path, medidas: dict[str, float]) -> None:
    """Corta o silêncio das pontas e converte para a taxa do treino."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(bruto),
         "-ss", f"{medidas['inicio']:.3f}",
         "-t", f"{max(medidas['fim'] - medidas['inicio'], 0.1):.3f}",
         "-ar", str(TAXA_TREINO), "-ac", "1",
         str(destino), "-loglevel", "error"],
        check=True,
    )


def tocar(caminho: Path) -> None:
    for comando in (["afplay"], ["aplay", "-q"],
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
        if shutil.which(comando[0]):
            subprocess.run([*comando, str(caminho)], check=False)
            return


# ------------------------------------------------------------------- guião


def ler_guiao() -> list[str]:
    if not GUIAO.is_file():
        print(f"❌ falta o guião: {GUIAO}")
        return []
    return [
        linha.strip()
        for linha in GUIAO.read_text(encoding="utf-8").splitlines()
        if linha.strip() and not linha.lstrip().startswith("#")
    ]


def ler_metadata(pasta: Path) -> dict[str, str]:
    ficheiro = pasta / "metadata.csv"
    if not ficheiro.is_file():
        return {}
    feitas = {}
    with ficheiro.open(encoding="utf-8") as f:
        for linha in csv.reader(f, delimiter="|"):
            if len(linha) >= 2:
                feitas[linha[1]] = linha[0]
    return feitas


def acrescentar_metadata(pasta: Path, nome: str, texto: str) -> None:
    with (pasta / "metadata.csv").open("a", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter="|", lineterminator="\n").writerow([nome, texto])


# ---------------------------------------------------------------- relatório


def relatorio(pasta: Path) -> int:
    wavs = sorted((pasta / "wavs").glob("*.wav"))
    if not wavs:
        print(f"\n   Ainda não há nada em {pasta}\n")
        return 1

    total = 0.0
    problemas: list[tuple[str, list[str]]] = []
    piores_ruidos = []
    for caminho in wavs:
        medidas = analisar(caminho)
        # O ruído mede-se no bruto, no silêncio antes da fala. Ver chao_de_ruido().
        bruto = pasta / "bruto" / caminho.name
        if bruto.is_file():
            medidas["ruido"] = chao_de_ruido(bruto)
        total += medidas["duracao"]
        piores_ruidos.append((medidas["ruido"], caminho.name))
        avisos = comentar(medidas)
        if avisos:
            problemas.append((caminho.name, avisos))

    minutos = total / 60
    print(f"\n📊 {len(wavs)} frases · {minutos:.1f} minutos de fala aparada")
    print(f"   média de {total / len(wavs):.1f} s por frase")

    # O que é preciso para treinar, com as balizas que a comunidade usa
    for alvo, nome in ((10, "teste — dá para ouvir se a gravação presta"),
                       (60, "mínimo para afinar um Piper decente"),
                       (120, "bom — é aqui que deixa de soar a robô barato")):
        marca = "✅" if minutos >= alvo else "  "
        print(f"   {marca} {alvo:>3} min · {nome}")

    piores_ruidos.sort(reverse=True)
    if piores_ruidos:
        pior = piores_ruidos[0]
        print(f"\n   Chão de ruído mais alto: {pior[0]:.4f} em {pior[1]}"
              f"   ({'bom' if pior[0] <= RUIDO_BOM else 'alto — vale a pena regravar'})")

    if problemas:
        print(f"\n⚠️  {len(problemas)} ficheiros com problemas:")
        for nome, avisos in problemas[:15]:
            print(f"     {nome}: {'; '.join(avisos)}")
        if len(problemas) > 15:
            print(f"     … e mais {len(problemas) - 15}")
        print("\n   Para regravar um: apaga o wavs/<nome> e a linha dele no metadata.csv.")
    else:
        print("\n   ✅ Nenhum ficheiro com problemas.")
    print()
    return 0


# -------------------------------------------------------------------- main


def sessao(pasta: Path, dispositivo: str, limite: int | None) -> int:
    frases = ler_guiao()
    if not frases:
        return 1

    (pasta / "bruto").mkdir(parents=True, exist_ok=True)
    (pasta / "wavs").mkdir(parents=True, exist_ok=True)
    feitas = ler_metadata(pasta)
    em_falta = [f for f in frases if f not in feitas]

    print(f"\n🎙️  {pasta.name} · {len(feitas)} gravadas, {len(em_falta)} por gravar")
    if not em_falta:
        print("   Guião todo gravado. Acrescenta frases ao config/guiao_voz.txt.\n")
        return relatorio(pasta)

    print("   Enter começa · Enter pára · depois ouves e decides")
    print("   [Enter] fica  ·  r  repete  ·  s  salta  ·  q  acaba a sessão\n")

    contador = len(feitas)
    nesta_sessao = 0
    for frase in em_falta:
        if limite and nesta_sessao >= limite:
            print(f"\n   Chegaste às {limite} desta sessão. Descansa a voz.")
            break

        while True:
            contador += 1
            nome = f"{contador:04d}.wav"
            bruto = pasta / "bruto" / nome
            final = pasta / "wavs" / nome

            print(f"\n  [{len(feitas) + nesta_sessao + 1}/{len(frases)}]  {frase}")
            try:
                input("      [Enter para gravar] ")
            except (EOFError, KeyboardInterrupt):
                print("\n   Sessão interrompida.\n")
                return relatorio(pasta)

            print("      🔴 a gravar — Enter para parar")
            if not gravar_bruto(bruto, dispositivo):
                print("      ❌ não gravou nada. O microfone está certo?")
                print("         python scripts/gravar_voz.py --dispositivos")
                return 1

            medidas = analisar(bruto)
            aparar(bruto, final, medidas)
            fala = medidas["fim"] - medidas["inicio"]
            print(f"      {fala:.1f} s · pico {medidas['pico']:.2f} · ruído {medidas['ruido']:.4f}")
            for aviso in comentar(medidas):
                print(f"      ⚠️  {aviso}")

            tocar(final)
            escolha = input("      [Enter] fica · r repete · s salta · q acaba: ").strip().lower()

            if escolha == "r":
                bruto.unlink(missing_ok=True)
                final.unlink(missing_ok=True)
                contador -= 1
                continue
            if escolha == "s":
                bruto.unlink(missing_ok=True)
                final.unlink(missing_ok=True)
                contador -= 1
                break
            acrescentar_metadata(pasta, nome, frase)
            nesta_sessao += 1
            if escolha == "q":
                print("\n   Até à próxima.")
                return relatorio(pasta)
            break

    return relatorio(pasta)


def main() -> int:
    parser = argparse.ArgumentParser(description="Grava o guião para treinar a voz do robô.")
    parser.add_argument("--quem", help="de quem é a voz (bruno, lara, …)")
    parser.add_argument("--dispositivo", default=":0", help="entrada de áudio do avfoundation")
    parser.add_argument("--dispositivos", action="store_true", help="listar microfones e sair")
    parser.add_argument("--verificar", action="store_true", help="só analisar o que já está gravado")
    parser.add_argument("--limite", type=int, default=40,
                        help="máximo de frases por sessão (0 = sem limite)")
    args = parser.parse_args()

    if args.dispositivos:
        return dispositivos()
    if not args.quem:
        parser.print_help()
        print("\n   Começa por aqui:  python scripts/gravar_voz.py --dispositivos\n")
        return 1
    if not shutil.which("ffmpeg"):
        print("❌ falta o ffmpeg:  brew install ffmpeg")
        return 1

    pasta = GRAVACOES / args.quem
    if args.verificar:
        return relatorio(pasta)
    return sessao(pasta, args.dispositivo, args.limite or None)


if __name__ == "__main__":
    sys.exit(main())
