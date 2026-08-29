#!/usr/bin/env python3
"""ENSINAR UMA CARA AO ROBÔ.

    python scripts/enrol_face.py Lara          registar
    python scripts/enrol_face.py --listar      ver quem ele conhece
    python scripts/enrol_face.py --apagar Lara esquecer alguém

💡 COM UMA CRIANÇA, USA ANTES O `scripts/ver_visao.py`: a pose aparece ao lado
   do vídeo, ela vê a própria cara com a caixa à volta enquanto posa, e é ela
   que carrega no botão. Este script serve para quando só há terminal.

🔒 ANTES DE CORRER ISTO, LÊ EM VOZ ALTA À PESSOA:

   "Vou ensinar o robô a reconhecer-te. Ele NÃO guarda fotografias — guarda
    128 números que o ajudam a saber que és tu. Esses números ficam só neste
    robô, nunca saem de casa, e podes pedir para os apagar quando quiseres."

   Se a pessoa não quiser, não se regista. Simples.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402
from robot.perception import camera, faces  # noqa: E402

POSES = [
    "olha para a câmara",
    "sorri",
    "vira um bocadinho para a esquerda",
    "vira um bocadinho para a direita",
    "levanta um pouco o queixo",
    "baixa um pouco o queixo",
    "faz uma cara séria",
    "chega-te mais perto",
]


def registar(nome: str) -> int:
    n = int(config.obter("faces.fotos_por_pessoa", 8))

    print(f"\n{'=' * 58}")
    print(f"  A ENSINAR O ROBÔ A RECONHECER: {nome}")
    print(f"{'=' * 58}")
    print("\n  🔒 O robô guarda 128 números, não fotografias.")
    print("     Ficam só aqui e podem ser apagados a qualquer momento.\n")

    if input("  A pessoa concorda? (sim/não) ").strip().lower() not in ("sim", "s"):
        print("\n  Não foi registado. E fez bem em perguntar.")
        return 1

    if config.a_simular():
        print("\n  ⚠️  Modo simulação — não há câmara. Nada foi guardado.")
        return 1

    if not camera.disponivel():
        print("\n  ❌ Câmara indisponível. Verifica o cabo adaptador CSI 22→15.")
        return 1

    print(f"\n  Vou tirar {n} fotos. Muda de posição em cada uma —")
    print("  quanto mais variedade, melhor ele reconhece.\n")

    vetores = []
    for i in range(n):
        pose = POSES[i % len(POSES)]
        print(f"  [{i + 1}/{n}] {pose}…")
        # ⚠️ Aqui havia uma contagem 3-2-1 de dois segundos. Não funcionava:
        #    quem está a posar está virado para a CÂMARA, de costas para o
        #    ecrã, e nunca chega a ler a pose. Metade das fotos saíam com a
        #    pose errada ou sem cara nenhuma. Agora espera — quem posa é que
        #    decide quando está pronto.
        input("        (Enter quando estiveres em posição, Ctrl+C para sair) ")

        imagem = camera.tirar_foto()
        if imagem is None:
            print("        ❌ falhou a foto")
            continue

        caras = faces.detetar(imagem)
        if not caras:
            print("        ⚠️  não vi nenhuma cara — chega-te mais perto")
            continue
        if len(caras) > 1:
            print(f"        ⚠️  vi {len(caras)} caras — fica só uma pessoa à frente")
            continue

        vetor = faces.assinatura(imagem, caras[0])
        if vetor is not None:
            vetores.append(vetor)
            print(f"        ✅ boa ({len(vetores)} guardadas)")

    if len(vetores) < 3:
        print(f"\n  ❌ Só consegui {len(vetores)} fotos boas — preciso de pelo menos 3.")
        print("     Tenta com mais luz, de frente para a janela.")
        return 1

    caminho = faces.guardar_pessoa(nome, vetores)
    print(f"\n  🎉 Pronto! O robô já conhece {nome}.")
    print(f"     ({len(vetores)} fotos → 1 assinatura em {caminho.name})")
    print(f"\n  Conhece agora: {', '.join(faces.pessoas_conhecidas())}\n")
    return 0


def listar() -> int:
    pessoas = faces.pessoas_conhecidas()
    print()
    if pessoas:
        print(f"  O robô conhece {len(pessoas)} pessoa(s):")
        for p in pessoas:
            print(f"    · {p}")
    else:
        print("  O robô ainda não conhece ninguém.")
        print("  Corre:  python scripts/enrol_face.py Lara")
    print()
    return 0


def apagar(nome: str) -> int:
    print()
    if faces.apagar_pessoa(nome):
        print(f"  🗑️  {nome} foi apagado. O robô já não o reconhece.")
        print("     (direito a ser esquecido — um comando, e desaparece)")
    else:
        print(f"  ❓ O robô não conhecia ninguém chamado '{nome}'.")
        print(f"     Conhece: {', '.join(faces.pessoas_conhecidas()) or '(ninguém)'}")
    print()
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--listar":
        return listar()
    if args[0] == "--apagar":
        if len(args) < 2:
            print("  Falta o nome. Exemplo: --apagar Lara")
            return 1
        return apagar(args[1])
    return registar(args[0])


if __name__ == "__main__":
    sys.exit(main())
