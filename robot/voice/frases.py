"""AS FRASES FIXAS DO ROBÔ — sempre em INGLÊS, num sítio só.

O que o robô diz sem passar pelo LLM (erros, avisos, o registo da cara, os
«hmm»). Antes vivia espalhado pelo main.py.

⚠️ SÓ INGLÊS, DE PROPÓSITO. A voz é a GLaDOS, um Piper com fonemizador
   `en-us`: texto português passado por ela sai estropiado. Tudo o que o robô
   DIZ tem de estar em inglês — aqui, nas ferramentas (tools.py), na navegação
   e nas bibliotecas da Lara. O que ele OUVE pode vir nas duas línguas (o
   Parakeet deteta sozinho), por isso as listas de «sim» aceitam as duas.

    frases.dizer("nao_percebi")             → "I didn't get that. …"
    frases.dizer("bateria_fraca", pct=18)   → "… I have 18% left."

⚠️ Frases FIXAS: ficam na cache de voz depois da primeira vez, e a partir daí
   saem mesmo com o mini desligado.
"""

from __future__ import annotations

FRASES: dict[str, str] = {
    "ola": "Hello! My name is {nome}.",
    "nao_percebi": "I didn't get that. Can you say that again?",
    "nao_ouvi": "I didn't hear you. Can you say that again?",
    "baralhei": "Oops, I got confused. Can you repeat?",
    "sem_cerebro": "My big brain is asleep. I can still see you, but I can't understand new words.",
    "perdi_te": "I can't see you anymore!",
    "bateria_critica": "I'm almost out of battery, I'm going to sleep for a bit. See you soon!",
    "bateria_fraca": "I'm getting low on battery, I have {pct}% left.",

    # -- o registo da cara (robot/perception/registo.py) ---------------------
    "registo_qual_nome": "Sure! What's your name?",
    "registo_nome_outra_vez": "Sorry, I didn't catch your name. What's your name?",
    "registo_sem_nome": "Let's try again later. Just ask me to learn your face.",
    "registo_privacidade": ("I'll learn your face, {nome}. I only keep numbers, not photos, "
                            "and you can ask me to forget them any time. Is that okay?"),
    "registo_sem_licenca": "Okay, I won't save your face.",
    "registo_comecar": "Great! Look at my camera. Green light means I got the photo.",
    "registo_boa": "Got it!",
    "registo_nao_vejo": "I can't see your face. Come a bit closer.",
    "registo_muitos": "I see more than one face. Just you, please!",
    "registo_falhou": ("I only got {boas} good photos and I need {minimo}. "
                       "Let's try again with more light."),
    "registo_feito": "Yay! Now I know you, {nome}!",
    "registo_sem_camara": "I can't learn faces right now, my camera isn't working.",
    "registo_simulacao": "In simulation there's no camera, so I didn't save anyone.",
}

# As poses do registo, ditas uma a uma. Curtas: quem posa está de frente para
# a câmara e não decora uma frase comprida.
POSES = ("Look straight at me.", "Smile!", "Turn a little to your left.",
         "Turn a little to your right.", "Lift your chin.", "Lower your chin.",
         "Make a serious face.", "Come a bit closer.")

# Os «hmm» — ver robot/voice/enchimentos.py.
ENCHIMENTOS = {
    "curtos": ("Hmm...", "Uh...", "I see.", "Ooh!", "Okay...", "Hmm, hmm.", "Right...",
               "Let me check.", "Beep boop.", "Aha!"),
    "longos": ("Ooh, good question! Let me think.", "Hmm, let me think about that.",
               "Wait, my brain is spinning!", "Thinking, thinking..."),
}

# O que ela RESPONDE pode vir em português: aceitam-se as duas línguas.
SIM = ("yes", "yeah", "yep", "sure", "okay", "ok", "of course", "yes please",
       "sim", "pode", "pode ser", "claro", "esta bem")


def lingua() -> str:
    """A língua da VOZ. Sempre inglês — ver o topo do ficheiro."""
    return "en"


def dizer(chave: str, **valores) -> str:
    """A frase `chave`, com os {valores} preenchidos."""
    texto = FRASES[chave]
    return texto.format(**valores) if valores else texto


def poses() -> tuple[str, ...]:
    return POSES


def enchimentos(tipo: str = "curtos") -> tuple[str, ...]:
    return ENCHIMENTOS[tipo]


def e_um_sim(resposta: str) -> bool:
    """«Yes!», «sim, pode», «okay» → True. Na dúvida, NÃO: guardar uma cara
    exige consentimento claro (AGENTS.md)."""
    from robot.brain.comandos_diretos import _simplificar

    limpo = _simplificar(resposta or "")
    if not limpo or any(p in limpo.split() for p in ("no", "nao", "nope")):
        return False
    return any(f" {s} " in f" {limpo} " for s in (_simplificar(x) for x in SIM))
