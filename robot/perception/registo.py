"""REGISTAR UMA CARA SÓ COM A VOZ — sem teclado, sem ecrã.

O `scripts/enrol_face.py` faz o mesmo no terminal, com Enter entre poses. Isto
é a versão que a Lara usa a falar com o robô:

    «Learn my face!»
      → «Sure! What's your name?»          (se ainda não souber)
      → «I'll learn your face, Lara. I only keep numbers… Is that okay?»
      → «Great! Look at my camera…»
      → uma pose de cada vez, dita em voz alta:
            luz BRANCA a piscar  = prepara-te, vou tirar
            luz VERDE + ding     = esta ficou boa
            luz VERMELHA + frase = esta não deu, e porquê («chega-te mais perto»)
      → arco-íris + «Yay! Now I know you, Lara!»

⚠️ Porque é que não há contagem «3, 2, 1» num ecrã: quem posa está virado para
   a CÂMARA. A instrução falada e a luz são as únicas que lhe chegam.

⚠️ As fotos boas só levam um ding, não uma frase. Oito «Got it!» seguidos
   tornavam o registo o dobro do tempo. As más levam frase, porque dizem o que
   mudar — e é isso que o torna reparável por uma criança sozinha.

🔒 Guardam-se 128 números por pessoa, não fotografias. E pergunta-se primeiro:
   sem um «sim» claro não se guarda nada (AGENTS.md).
"""

from __future__ import annotations

import re
import time

from robot import config, rotinas
from robot.voice import frases

MINIMO_BOAS = 3

# Compatibilidade: quem ainda importava as poses daqui.
POSES = frases.POSES

_PADROES_NOME = re.compile(
    r"(?:my name is|my name's|i am|i'm|im|it's|its|call me|this is"
    r"|chamo-me|chamo me|o meu nome é|o meu nome e|eu sou a|eu sou o|sou a|sou o|sou|é a|é o)"
    r"\s+([A-Za-zÀ-ÿ][\w'-]*)",
    re.IGNORECASE,
)
_NAO_SAO_NOMES = {"yes", "no", "sim", "nao", "não", "okay", "ok", "hello", "hi", "ola", "olá",
                  "the", "a", "o", "um", "uma", "robot", "robô", "lylla"}


def extrair_nome(resposta: str) -> str | None:
    """«My name is Lara» · «I'm Lara» · «Lara!» · «chamo-me Lara» → "Lara"."""
    texto = (resposta or "").strip()
    if not texto:
        return None
    m = _PADROES_NOME.search(texto)
    if m:
        candidato = m.group(1)
    else:
        palavras = re.findall(r"[A-Za-zÀ-ÿ][\w'-]*", texto)
        if not 1 <= len(palavras) <= 2:
            return None     # uma frase comprida não é um nome
        candidato = palavras[-1]
    candidato = candidato.strip("'-")
    if len(candidato) < 2 or candidato.lower() in _NAO_SAO_NOMES:
        return None
    return candidato[:1].upper() + candidato[1:]


def _segundos_para_posar() -> float:
    return float(config.obter("faces.segundos_por_pose", 2.0))


def _perguntar(pergunta: str, dizer, ouvir) -> str:
    """Diz, acende o verde, ouve a resposta, e confirma que ouviu."""
    dizer(pergunta)
    rotinas.correr("acordar")
    try:
        resposta = ouvir() or ""
    finally:
        rotinas.correr("ouvi")
    return resposta


def registar_pela_voz(nome: str, dizer, ouvir=None, fotos: int | None = None) -> str:
    """Guia a pessoa pelo registo inteiro, falando. Devolve a última frase dita.

    `dizer(texto)` fala e ESPERA que acabe (cada pose tem de ser ouvida antes
    de a foto sair). `ouvir()` grava uma resposta e devolve o texto; sem ele
    (um script, um teste) não se pergunta nada — o nome tem de vir dado.

    Tudo o que interessa já foi DITO quando isto volta: quem chama não precisa
    de repetir o resultado.
    """
    from robot.perception import camera, faces

    def _acabar(frase: str, rotina: str | None = None) -> str:
        if rotina:
            rotinas.correr(rotina)
        dizer(frase)
        rotinas.correr("acabei")
        return frase

    # 1. O NOME — perguntado, se não vier.
    nome = extrair_nome(nome) if nome else None
    if not nome and ouvir is not None:
        for chave in ("registo_qual_nome", "registo_nome_outra_vez"):
            nome = extrair_nome(_perguntar(frases.dizer(chave), dizer, ouvir))
            if nome:
                break
    if not nome:
        return _acabar(frases.dizer("registo_sem_nome"), "nao_ouvi")

    if config.a_simular():
        return _acabar(frases.dizer("registo_simulacao"))
    if not camera.disponivel():
        return _acabar(frases.dizer("registo_sem_camara"), "sem_cerebro")

    # 2. O CONSENTIMENTO — o que fica guardado, e um «sim» claro.
    privacidade = frases.dizer("registo_privacidade", nome=nome)
    if ouvir is not None:
        if not frases.e_um_sim(_perguntar(privacidade, dizer, ouvir)):
            return _acabar(frases.dizer("registo_sem_licenca"))
    else:
        dizer(privacidade)

    # 3. AS POSES — até ter as fotos que se pediram, com algumas de reserva.
    quantas = int(fotos or config.obter("faces.fotos_por_pessoa", 8))
    poses = frases.poses()
    dizer(frases.dizer("registo_comecar"))
    vetores = []
    tentativas = 0
    while len(vetores) < quantas and tentativas < quantas + 4:
        pose = poses[tentativas % len(poses)]
        tentativas += 1
        rotinas.correr("foto_preparar")
        dizer(pose)
        time.sleep(_segundos_para_posar())

        imagem = camera.tirar_foto()
        caras = faces.detetar(imagem) if imagem is not None else []
        if len(caras) != 1:
            rotinas.correr("foto_ma")
            dizer(frases.dizer("registo_muitos" if len(caras) > 1 else "registo_nao_vejo"))
            continue
        vetor = faces.assinatura(imagem, caras[0])
        if vetor is None:
            rotinas.correr("foto_ma")
            dizer(frases.dizer("registo_nao_vejo"))
            continue
        vetores.append(vetor)
        rotinas.correr("foto_boa")

    if len(vetores) < MINIMO_BOAS:
        # ⚠️ Dizer o número é o que torna isto reparável: «não consegui» manda
        #    a criança tentar outra vez ao acaso; «só 2 de 3» diz-lhe o que falta.
        return _acabar(frases.dizer("registo_falhou", boas=len(vetores), minimo=MINIMO_BOAS),
                       "nao_ouvi")

    faces.guardar_pessoa(nome, vetores)
    faces.carregar_conhecidos()
    return _acabar(frases.dizer("registo_feito", nome=nome), "registo_feito")
