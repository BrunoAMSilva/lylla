#!/usr/bin/env python3
"""TESTAR A CÂMARA E O RECONHECIMENTO DE CARAS.

    python scripts/test_camera.py            tira uma foto e conta as caras
    python scripts/test_camera.py --continuo mostra quem vê, a cada segundo
    python scripts/test_camera.py --guardar   grava uma foto para ver

⚠️  Se a câmara não aparecer, a causa nº1 é o CABO ADAPTADOR CSI 22→15 PINOS.
    O Pi 5 mudou de conector e a Camera Module 3 vem com o cabo antigo.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config
from robot.perception import camera, faces


def uma_vez() -> int:
    print("\n📷 A tirar uma foto…")
    imagem = camera.tirar_foto()
    if imagem is None:
        print("   ❌ Sem câmara.")
        print("      rpicam-hello --list-cameras")
        print("      ⚠️  Tens o cabo adaptador 22→15 pinos? E o venv é --system-site-packages?\n")
        return 1

    altura, largura = imagem.shape[:2]
    print(f"   ✅ imagem {largura}×{altura}  ← o hardware está bom")

    # ⚠️ Parar AQUI se a visão não arrancou. Antes seguia em frente e imprimia
    #    "0 cara(s) encontrada(s) em 0 ms", que se lê como "não está lá
    #    ninguém" — e manda a pessoa mexer outra vez no cabo CSI por causa de
    #    um pacote de Python que falta. Os 0 ms eram a única pista.
    if not faces.disponivel():
        print("\n   ❌ A câmara funciona, mas a VISÃO não arrancou.")
        print("      O erro está no aviso acima. Não é o cabo.\n")
        return 1

    inicio = time.monotonic()
    caras = faces.detetar(imagem)
    ms = (time.monotonic() - inicio) * 1000
    print(f"   🔍 {len(caras)} cara(s) encontrada(s) em {ms:.0f} ms")

    for i, cara in enumerate(caras):
        x, y, w, h = (int(v) for v in cara[:4])
        nome, semelhanca = faces.identificar(faces.assinatura(imagem, cara))
        etiqueta = nome if nome else "desconhecido"
        print(f"      [{i + 1}] {etiqueta:12s} "
              f"(semelhança {semelhanca:.2f}) em ({x},{y}) {w}×{h}px")

    limiar = config.obter("faces.limiar", 0.45)
    print(f"\n   limiar atual: {limiar}")
    print("   (mais alto = mais exigente. Mexe no config/robot.yaml)\n")
    return 0


def continuo() -> int:
    print("\n📷 Modo contínuo. Ctrl+C para parar.\n")
    conhecidos = faces.pessoas_conhecidas()
    print(f"   conhece: {', '.join(conhecidos) if conhecidos else '(ninguém)'}\n")
    try:
        while True:
            imagem = camera.tirar_foto()
            if imagem is None:
                print("   sem imagem")
                time.sleep(2)
                continue
            caras = faces.detetar(imagem)
            if not caras:
                print("   … não vejo ninguém          ", end="\r", flush=True)
            else:
                nomes = []
                for cara in caras:
                    nome, valor = faces.identificar(faces.assinatura(imagem, cara))
                    nomes.append(f"{nome or '?'} ({valor:.2f})")
                print(f"   👁️  {', '.join(nomes)}                    ", end="\r", flush=True)
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n\n   parado.\n")
    return 0


def guardar() -> int:
    destino = "/tmp/robo_foto.jpg"
    if camera.guardar_foto(destino):
        print(f"\n   ✅ guardada em {destino}")
        print("      (copia para o Mac com: scp robo.local:/tmp/robo_foto.jpg .)\n")
        return 0
    print("\n   ❌ não consegui.\n")
    return 1


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--continuo":
        return continuo()
    if args and args[0] == "--guardar":
        return guardar()
    return uma_vez()


if __name__ == "__main__":
    sys.exit(main())
