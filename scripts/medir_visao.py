#!/usr/bin/env python3
"""MEDIR A VISÃO — quanto custa ver, a cada resolução.

    python scripts/medir_visao.py                     100 medições por resolução
    python scripts/medir_visao.py --medicoes 30       mais depressa
    python scripts/medir_visao.py --imagem foto.jpg   sem câmara (dá no Mac)
    python scripts/medir_visao.py --csv medidas.csv   para quem preferir o Excel

É a experiência da FASE 9 (sessão A) do PLANO.md, e responde a três perguntas:

  1. Quanto custa DETETAR uma cara, e como cresce isso com o número de píxeis?
  2. Quanto custa RECONHECER quem é? (a surpresa: não depende da resolução)
  3. A 10 imagens por segundo, quanto é isso de um núcleo do Pi?

⚠️ USAMOS A MESMA IMAGEM nas três resoluções, reduzida ANTES de o cronómetro
   arrancar. É de propósito, e são duas regras da casa ao mesmo tempo:

   · se cada resolução visse uma imagem diferente, não se saberia se a
     diferença no tempo vem dos píxeis ou do que estava à frente da câmara;
   · cronometra-se só o que se quer medir — a redução da imagem e as primeiras
     voltas de aquecimento ficam de fora da conta.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402
from robot.perception import camera, faces  # noqa: E402

RESOLUCOES = [(160, 120), (320, 240), (640, 480)]
AQUECIMENTO = 10


# ---------------------------------------------------------------------------
# arranjar uma imagem para medir
# --------------------------------------------------------------------------- 
def obter_imagem(caminho: str | None):
    """Devolve (imagem, ms_para_tirar_a_foto). A imagem é None se falhar."""
    import cv2

    if caminho:
        imagem = cv2.imread(caminho)
        if imagem is None:
            print(f"\n  ❌ Não consegui ler '{caminho}'.\n")
            return None, None
        print(f"  imagem de referência: {caminho}")
        return imagem, None

    if config.a_simular():
        print("\n  ❌ Modo simulação — não há câmara aqui.")
        print("     Mede na mesma com uma fotografia qualquer que tenha uma cara:")
        print("     python scripts/medir_visao.py --imagem foto.jpg\n")
        return None, None

    camera.tirar_foto()  # a primeira não conta (autofoco, exposição)
    tempos, imagem = [], None
    for _ in range(5):
        inicio = time.perf_counter()
        tirada = camera.tirar_foto()
        tempos.append((time.perf_counter() - inicio) * 1000)
        if tirada is not None:
            imagem = tirada

    if imagem is None:
        print("\n  ❌ Sem câmara. Vê o docs/FASE9-visao.md, passo 2.\n")
        return None, None

    altura, largura = imagem.shape[:2]
    print(f"  imagem de referência: {largura}×{altura} da câmara")
    return imagem, statistics.median(tempos)


# --------------------------------------------------------------------------- 
# as medições
# --------------------------------------------------------------------------- 
def medir_detecao(imagem, largura: int, altura: int, n: int):
    """Cronometra o YuNet a uma resolução. Devolve (tempos_ms, caras_vistas)."""
    import cv2

    pequena = cv2.resize(imagem, (largura, altura))

    for _ in range(AQUECIMENTO):
        faces.detetar(pequena)

    tempos, caras = [], []
    for _ in range(n):
        inicio = time.perf_counter()
        encontradas = faces.detetar(pequena)
        tempos.append((time.perf_counter() - inicio) * 1000)
        caras.append(len(encontradas))

    return tempos, statistics.mode(caras)


def medir_reconhecimento(imagem, n: int):
    """Cronometra o SFace na cara maior. None se não houver cara nenhuma."""
    encontradas = faces.detetar(imagem)
    if not encontradas:
        return None
    maior = max(encontradas, key=lambda c: c[2] * c[3])

    for _ in range(AQUECIMENTO):
        faces.assinatura(imagem, maior)

    tempos = []
    for _ in range(n):
        inicio = time.perf_counter()
        faces.assinatura(imagem, maior)
        tempos.append((time.perf_counter() - inicio) * 1000)
    return tempos


# --------------------------------------------------------------------------- 
# mostrar
# --------------------------------------------------------------------------- 
def barra(valor: float, maximo: float, largura: int = 20) -> str:
    if maximo <= 0:
        return ""
    return "█" * max(1, round(valor / maximo * largura))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--medicoes", type=int, default=100)
    p.add_argument("--imagem", type=str, default=None)
    p.add_argument("--csv", type=str, default=None)
    args = p.parse_args()

    nome = config.nome_do_robo()
    print(f"\n{'=' * 66}")
    print(f"  QUANTO CUSTA VER — {nome}")
    print(f"{'=' * 66}\n")

    imagem, ms_foto = obter_imagem(args.imagem)
    if imagem is None:
        return 1

    if not faces.pessoas_conhecidas():
        print("  (ninguém registado ainda — não faz mal, aqui só medimos tempos)")

    n = args.medicoes
    print(f"  medições por resolução: {n}   (+{AQUECIMENTO} de aquecimento, "
          f"que não contam)")
    if ms_foto is not None:
        print(f"  tirar a foto:           {ms_foto:.1f} ms")

    # ---------------------------------------------------------- detetar
    print("\n" + "-" * 66)
    print("  DETETAR (YuNet) — «está aqui alguém, e onde?»")
    print("-" * 66)

    linhas = []
    for largura, altura in RESOLUCOES:
        tempos, caras = medir_detecao(imagem, largura, altura, n)
        linhas.append({
            "resolucao": f"{largura}×{altura}",
            "pixeis": largura * altura,
            "mediana": statistics.median(tempos),
            "min": min(tempos),
            "max": max(tempos),
            "caras": caras,
        })

    pior = max(linha["mediana"] for linha in linhas)
    print(f"\n  {'resolução':>9}  {'píxeis':>9}  {'mediana':>9}  {'min':>9}  "
          f"{'caras':>5}")
    for linha in linhas:
        pixeis = f"{linha['pixeis']:,}".replace(",", " ")
        print(f"  {linha['resolucao']:>9}  {pixeis:>9}  "
              f"{linha['mediana']:>6.1f} ms  {linha['min']:>6.1f} ms  "
              f"{linha['caras']:>5}   {barra(linha['mediana'], pior)}")

    # como é que cresce
    print("\n  o que acontece quando se sobe de resolução:")
    for anterior, seguinte in zip(linhas, linhas[1:]):
        vezes_px = seguinte["pixeis"] / anterior["pixeis"]
        vezes_ms = (seguinte["mediana"] / anterior["mediana"]
                    if anterior["mediana"] > 0 else float("nan"))
        print(f"    {anterior['resolucao']:>9} → {seguinte['resolucao']:<9} "
              f"{vezes_px:.0f}× os píxeis  →  {vezes_ms:.1f}× o tempo")

    # o aviso que interessa mais do que o tempo
    vistas = {linha["resolucao"]: linha["caras"] for linha in linhas}
    if min(vistas.values()) < max(vistas.values()):
        cegas = [r for r, c in vistas.items() if c < max(vistas.values())]
        print(f"\n  ⚠️  A {' e a '.join(cegas)} ele vê MENOS caras.")
        print("      Depressa não serve de nada se deixar de ver — é este o")
        print("      compromisso todo, e é por isto que a experiência se faz")
        print("      com uma pessoa à frente da câmara, não com uma imagem vazia.")

    # ---------------------------------------------------------- reconhecer
    print("\n" + "-" * 66)
    print("  RECONHECER (SFace) — «quem é?»")
    print("-" * 66)

    tempos_sface = medir_reconhecimento(imagem, n)
    if tempos_sface is None:
        ms_sface = None
        print("\n  ⚠️  Não vi nenhuma cara na imagem, por isso não dá para medir.")
        print("      Põe-te à frente da câmara (ou usa --imagem com uma foto).")
    else:
        ms_sface = statistics.median(tempos_sface)
        print(f"\n  mediana: {ms_sface:.1f} ms   "
              f"(min {min(tempos_sface):.1f} · max {max(tempos_sface):.1f})")
        print("\n  Repara: este número é UM SÓ — não há coluna por resolução.")
        print("  O SFace recorta e endireita a cara para 112×112 antes de a ver,")
        print("  portanto custa o mesmo quer a imagem venha de 160×120 ou de")
        print("  640×480. Detetar paga-se aos píxeis; reconhecer paga-se à cara.")

    # ---------------------------------------------------------- o orçamento
    fps = float(config.obter("secretaria.fps_deteccao", 10))
    reidentificar = float(config.obter("secretaria.reidentificar_s", 4.0))

    print("\n" + "-" * 66)
    print(f"  O ORÇAMENTO — a {fps:.0f} imagens por segundo")
    print("-" * 66 + "\n")
    for linha in linhas:
        pct = linha["mediana"] * fps / 10.0
        print(f"    detetar a {linha['resolucao']:>9} …… {pct:5.1f}% de um núcleo")
    if ms_sface is not None:
        pct_sface = ms_sface / (reidentificar * 1000) * 100
        print(f"    reconhecer de {reidentificar:.0f} em {reidentificar:.0f} s "
              f"…… {pct_sface:5.1f}% de um núcleo")
        escolhida = config.obter("secretaria.resolucao_deteccao", [320, 240])
        for linha in linhas:
            if linha["resolucao"] == f"{int(escolhida[0])}×{int(escolhida[1])}":
                total = linha["mediana"] * fps / 10.0 + pct_sface
                print(f"\n    o que o robô faz mesmo (detetar a "
                      f"{linha['resolucao']} + reconhecer): {total:.1f}%")

    # ---------------------------------------------------------- para o papel
    print("\n" + "-" * 66)
    print("  PARA O GRÁFICO DA LARA — píxeis no eixo do X, ms no do Y")
    print("-" * 66 + "\n")
    print(f"    {'píxeis':>8}   {'ms':>6}")
    for linha in linhas:
        print(f"    {linha['pixeis']:>8}   {linha['mediana']:>6.1f}")
    print("\n  Antes de o desenhar, pergunta-lhe: «se o dobro dos píxeis")
    print("  demorasse o dobro do tempo, os pontos ficavam numa linha reta")
    print("  ou numa curva?» E só depois é que se marcam os pontos.\n")

    if args.csv:
        with open(args.csv, "w", encoding="utf-8") as f:
            f.write("resolucao,pixeis,mediana_ms,min_ms,max_ms,caras\n")
            for linha in linhas:
                f.write(f"{linha['resolucao']},{linha['pixeis']},"
                        f"{linha['mediana']:.3f},{linha['min']:.3f},"
                        f"{linha['max']:.3f},{linha['caras']}\n")
        print(f"  💾 guardado em {args.csv}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
