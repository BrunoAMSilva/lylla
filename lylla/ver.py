"""VER — a câmara e as caras.

    from lylla import ver
    ver.quem_vejo()                     # 'Lara', ou None
    ver.guardar_face("Lara", aviso=dizer)

Toda a parte difícil — detetar a cara, tirar a assinatura de 128 números,
fazer a média de várias fotos, rejeitar as fotos más — vive aqui dentro. Quem
escreve uma função nova só precisa de saber que isto devolve True ou False.

🔒 O QUE FICA GUARDADO, E PORQUÊ ISTO IMPORTA MAIS DO QUE O CÓDIGO
   O robô NÃO guarda fotografias. Guarda 128 números por pessoa, que só servem
   para dizer «és tu». Ficam neste robô, não saem de casa, e apagam-se com um
   comando (`ver.esquecer("Lara")`). É por isso que a `guardar_face` diz isto
   em voz alta ANTES de tirar a primeira foto: quem está a ser registado tem de
   saber o que está a acontecer. Não é burocracia — é a diferença entre um
   brinquedo e uma câmara de vigilância.
"""

from __future__ import annotations

import time

from robot import config
from robot.perception import camera, faces

# A ordem importa: começa-se pela pose fácil, para haver logo uma foto boa.
POSES = (
    "olha para mim",
    "sorri",
    "vira a cabeça um bocadinho para a esquerda",
    "vira a cabeça um bocadinho para a direita",
    "levanta um pouco o queixo",
    "baixa um pouco o queixo",
    "faz uma cara séria",
    "chega-te mais perto",
)

PRIVACIDADE = (
    "Vou aprender a tua cara. Não guardo fotografias: guardo cento e vinte e "
    "oito números que me ajudam a saber que és tu. Ficam só dentro de mim, e "
    "podes pedir-me para os esquecer quando quiseres."
)

MINIMO_DE_FOTOS_BOAS = 3


def quem_vejo() -> str | None:
    """O nome de quem está à frente da câmara, ou None."""
    if config.a_simular():
        return None
    return faces.quem_esta_a_ver()


def conheces() -> list[str]:
    """A lista de pessoas que o robô já sabe reconhecer."""
    return faces.pessoas_conhecidas()


def esquecer(nome: str) -> bool:
    """Direito a ser esquecido. Um comando, e desaparece."""
    return faces.apagar_pessoa(nome)


def guardar_face(nome: str, aviso=None, fotos: int | None = None,
                 pausa_s: float = 2.5) -> bool:
    """Aprende a cara de alguém. Devolve True se ficou aprendida.

    `aviso` é a função que dá as instruções à pessoa — passa-lhe o `dizer` e o
    robô fala; não passes nada e ele escreve no terminal. É esse o truque que
    deixa a mesma biblioteca servir para uma conversa por voz e para um teste
    no teclado:

        from lylla import ver, voz
        ver.guardar_face("Lara", aviso=voz.dizer)

    Porque é que são oito fotos e não uma: uma só assinatura fica presa à luz e
    ao ângulo daquele instante. A média de várias poses é muito mais estável —
    e é por isso que ele pede para virar a cara e mudar de expressão.
    """
    falar = aviso or (lambda texto: print(f"  🗣️  {texto}"))
    quantas = int(fotos or config.obter("faces.fotos_por_pessoa", 8))

    falar(PRIVACIDADE)

    if config.a_simular():
        for i in range(quantas):
            falar(POSES[i % len(POSES)])
        falar(f"Pronto. Em simulação não há câmara, portanto não guardei nada, "
              f"mas a conversa toda funcionou, {nome}.")
        return False

    if not camera.disponivel():
        falar("A minha câmara não está a funcionar. Não consigo aprender caras assim.")
        return False

    boas = []
    for i in range(quantas):
        falar(POSES[i % len(POSES)])
        time.sleep(pausa_s)

        imagem = camera.tirar_foto()
        if imagem is None:
            falar("Não consegui tirar a fotografia. Vamos tentar outra vez.")
            continue

        caras = faces.detetar(imagem)
        if not caras:
            falar("Não vi nenhuma cara. Chega-te mais perto de mim.")
            continue
        if len(caras) > 1:
            falar("Estou a ver mais do que uma pessoa. Fica só tu à minha frente.")
            continue

        vetor = faces.assinatura(imagem, caras[0])
        if vetor is None:
            falar("Essa não ficou boa. Outra vez.")
            continue

        boas.append(vetor)
        falar(f"Boa! Já tenho {len(boas)}.")

    if len(boas) < MINIMO_DE_FOTOS_BOAS:
        falar("Só consegui algumas fotografias boas, e preciso de mais. "
              "Vamos tentar noutro sítio, com mais luz.")
        return False

    faces.guardar_pessoa(nome, boas)
    falar(f"Já te conheço, {nome}.")
    return True
