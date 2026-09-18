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
# (Em inglês: a voz do robô é inglesa e lê mal português.)
POSES = (
    "look at me",
    "smile",
    "turn your head a little to the left",
    "turn your head a little to the right",
    "lift your chin a little",
    "lower your chin a little",
    "make a serious face",
    "come a bit closer",
)

PRIVACIDADE = (
    "I'm going to learn your face. I don't keep photos: I keep one hundred and "
    "twenty eight numbers that help me know it's you. They stay inside me, and "
    "you can ask me to forget them any time."
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
        falar(f"Done. In simulation there's no camera, so I didn't save anything, "
              f"but the whole conversation worked, {nome}.")
        return False

    if not camera.disponivel():
        falar("My camera isn't working. I can't learn faces like this.")
        return False

    boas = []
    for i in range(quantas):
        falar(POSES[i % len(POSES)])
        time.sleep(pausa_s)

        imagem = camera.tirar_foto()
        if imagem is None:
            falar("I couldn't take the photo. Let's try again.")
            continue

        caras = faces.detetar(imagem)
        if not caras:
            falar("I didn't see a face. Come closer to me.")
            continue
        if len(caras) > 1:
            falar("I can see more than one person. Just you in front of me, please.")
            continue

        vetor = faces.assinatura(imagem, caras[0])
        if vetor is None:
            falar("That one wasn't good. Again.")
            continue

        boas.append(vetor)
        falar(f"Nice! I have {len(boas)}.")

    if len(boas) < MINIMO_DE_FOTOS_BOAS:
        falar("I only got a few good photos, and I need more. "
              "Let's try somewhere else, with more light.")
        return False

    faces.guardar_pessoa(nome, boas)
    falar(f"Now I know you, {nome}.")
    return True
