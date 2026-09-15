from __future__ import annotations

from lylla import comando, mover, ver, voz

@comando("Bom dia", "olá")
def bom_dia() -> None:
    voz.dizer("me to !")



bom_dia()
