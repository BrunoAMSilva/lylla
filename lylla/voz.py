"""VOZ — falar e ouvir.

    from lylla import voz
    voz.dizer("olá Lara")
    nome = voz.ouvir()

🔒 O áudio nunca vai para o disco: é transcrito em memória e deitado fora.
"""

from __future__ import annotations

import time

from robot import config


def dizer(texto: str = "olá!") -> None:
    """A Lylla diz uma frase em voz alta."""
    if config.a_simular():
        print(f"  🗣️  (simulado) {texto}")
        return
    try:
        from robot.voice import speak

        speak.falar(texto)
    except Exception:  # noqa: BLE001
        print(f"  🔇 (sem voz agora) {texto}")
        return
    print(f"  🗣️  {texto}")


def ouvir(segundos: float = 8.0) -> str:
    """Ouve uma frase e devolve o texto. Devolve "" se não percebeu.

    Em simulação (ou sem microfone) pergunta pelo teclado — assim dá para
    escrever e testar a conversa toda no Mac, antes de o robô existir.
    """
    try:
        from robot.voice import listen

        texto = listen.ouvir(segundos)
    except Exception:  # noqa: BLE001
        try:
            texto = input("  🎤 (escreve o que dirias) ")
        except Exception:  # noqa: BLE001
            # ⚠️ Sem terminal — a correr como serviço, ou dentro dos testes —
            # o input() levanta OSError, não EOFError. Um robô que morre por
            # não ter teclado é um robô que não arranca sozinho.
            return ""
    texto = (texto or "").strip()
    if texto:
        print(f"  👂 ouvi: {texto}")
    return texto


def esperar(segundos: float = 1) -> None:
    """Não faz nada durante uns segundos."""
    time.sleep(max(0.0, min(60.0, float(segundos))))
