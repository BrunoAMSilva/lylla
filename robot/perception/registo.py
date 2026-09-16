"""REGISTAR UMA CARA PELA VOZ.

O `scripts/enrol_face.py` faz o mesmo no terminal, com Enter entre poses. Isto
é a versão que a Lara usa sem teclado: o robô DIZ a pose, espera, e tira a
foto sozinho.

⚠️ Porque é que não há contagem "3, 2, 1": quem está a posar está virado para a
   CÂMARA, de costas para o ecrã. Foi a lição do enrol_face — metade das fotos
   saíam com a pose errada. Aqui a instrução é FALADA, que é a única que chega
   a quem está de frente para a lente.

🔒 Guardam-se 128 números por pessoa, não fotografias. E pergunta-se primeiro.
"""

from __future__ import annotations

import time

from robot import config

# Cada pose é dita em voz alta. Curtas de propósito: uma criança de frente para
# a câmara não decora uma frase longa.
POSES = (
    "Olha de frente para mim.",
    "Sorri.",
    "Vira um bocadinho para a esquerda.",
    "Vira um bocadinho para a direita.",
    "Levanta o queixo.",
    "Baixa o queixo.",
    "Faz uma cara séria.",
    "Chega-te mais perto.",
)

MINIMO_BOAS = 3


def _segundos_para_posar() -> float:
    return float(config.obter("faces.segundos_por_pose", 2.0))


def registar_pela_voz(nome: str, dizer, fotos: int | None = None) -> str:
    """Guia a pessoa pelas poses, falando, e guarda a assinatura dela.

    `dizer(texto)` é a função de falar — vem de fora para isto não depender do
    `speak` e poder ser testado sem hardware nenhum.
    """
    from robot.perception import camera, faces

    nome = (nome or "").strip()
    if not nome:
        return "Não percebi o nome. Diz outra vez: quem é que queres que eu aprenda?"
    if config.a_simular():
        return "Em simulação não há câmara — não registei ninguém."
    if not camera.disponivel():
        return "Não tenho câmara. Não consigo aprender caras assim."

    quantas = int(fotos or config.obter("faces.fotos_por_pessoa", 8))
    dizer(f"Vou aprender a cara de {nome}. Guardo números, não fotografias, "
          "e podes apagá-los quando quiseres.")

    vetores = []
    falhas = []
    for i in range(quantas):
        pose = POSES[i % len(POSES)]
        dizer(pose)
        time.sleep(_segundos_para_posar())

        imagem = camera.tirar_foto()
        if imagem is None:
            falhas.append("a foto falhou")
            continue
        caras = faces.detetar(imagem)
        if not caras:
            falhas.append("não vi ninguém")
            continue
        if len(caras) > 1:
            falhas.append("vi mais do que uma pessoa")
            continue
        vetor = faces.assinatura(imagem, caras[0])
        if vetor is not None:
            vetores.append(vetor)

    if len(vetores) < MINIMO_BOAS:
        # ⚠️ Dizer o número é o que torna isto reparável: "não consegui" manda
        #    a criança tentar outra vez ao acaso; "só consegui 2 de 8, chega-te
        #    à janela" diz-lhe o que mudar.
        return (f"Só consegui {len(vetores)} fotos boas de {quantas} e preciso de "
                f"{MINIMO_BOAS}. Tenta com mais luz, de frente para a janela.")

    faces.guardar_pessoa(nome, vetores)
    faces.carregar_conhecidos()
    return f"Já sei quem é {nome}! Guardei {len(vetores)} medições."
