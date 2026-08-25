"""Carrega a configuração e decide se estamos em modo simulação.

Modo simulação: se o hardware não estiver presente (por exemplo, a programar
no Mac antes de as peças chegarem), tudo continua a funcionar e escreve no
terminal o que faria. Força-se com:

    ROBO_SIMULAR=1 python -m robot.main
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_DIR = RAIZ / "config"
DATA_DIR = RAIZ / "data"
MODELS_DIR = RAIZ / "models"


@lru_cache(maxsize=1)
def carregar() -> dict[str, Any]:
    """Lê o config/robot.yaml (e o robot.local.yaml, se existir)."""
    cfg: dict[str, Any] = {}
    base = CONFIG_DIR / "robot.yaml"
    if base.exists():
        cfg = yaml.safe_load(base.read_text(encoding="utf-8")) or {}

    # Ficheiro local opcional, para experiências que não vão para o Git
    local = CONFIG_DIR / "robot.local.yaml"
    if local.exists():
        for chave, valor in (yaml.safe_load(local.read_text(encoding="utf-8")) or {}).items():
            if isinstance(valor, dict) and isinstance(cfg.get(chave), dict):
                cfg[chave].update(valor)
            else:
                cfg[chave] = valor
    return cfg


def obter(caminho: str, omissao: Any = None) -> Any:
    """Lê um valor da configuração com notação de pontos.

    >>> obter("motores.velocidade", 0.5)
    0.5
    """
    no: Any = carregar()
    for parte in caminho.split("."):
        if not isinstance(no, dict) or parte not in no:
            return omissao
        no = no[parte]
    return no


def nome_do_robo() -> str:
    return obter("nome", "Robô")


@lru_cache(maxsize=1)
def a_simular() -> bool:
    """True se não houver hardware de robô por baixo de nós.

    Detetamos o Raspberry Pi pelo /proc/device-tree/model, que é a forma
    fiável (o platform.machine() só diz 'aarch64', que um Mac M1 também diz).
    """
    if os.environ.get("ROBO_SIMULAR") == "1":
        return True
    if os.environ.get("ROBO_SIMULAR") == "0":
        return False
    try:
        modelo = Path("/proc/device-tree/model").read_bytes().decode(errors="ignore")
        return "Raspberry Pi" not in modelo
    except OSError:
        return True


def sim(mensagem: str) -> None:
    """Escreve uma linha de simulação, se estivermos em modo simulação."""
    if a_simular():
        print(f"[SIM] {mensagem}", flush=True)
