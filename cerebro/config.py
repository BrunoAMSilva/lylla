"""A configuração do cérebro — config/cerebro.yaml (+ cerebro.local.yaml).

Mesma ideia do robot/config.py: um ficheiro no Git com os valores normais, e um
`.local.yaml` opcional, fora do Git, para experiências nesta máquina.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_DIR = RAIZ / "config"
MODELS_DIR = RAIZ / "models"

OMISSAO: dict[str, Any] = {
    "nome": "Cérebro da Lylla",
    "host": "0.0.0.0",
    "porta": 8420,
    "ouvir": {
        "motor": "mlx",
        "modelo": "mlx-community/whisper-small-mlx",
        "modelo_faster": "small",
        "lingua": "auto",
    },
    "pensar": {
        "motor": "ollama",
        "url": "http://127.0.0.1:11434",
        "modelo": "gemma4:e4b",
        "temperatura": 0.7,
        "max_tokens": 300,
        "max_historico": 12,
        "timeout_s": 60,
        "keep_alive": -1,
        "extra": {},
    },
    "falar": {
        "motor": "piper",
        "voz": "glados",
        "velocidade": 1.0,
        "cache": "~/.cache/lylla-voz",
    },
}


def _fundir(base: dict, extra: dict) -> dict:
    resultado = dict(base)
    for chave, valor in (extra or {}).items():
        if isinstance(valor, dict) and isinstance(resultado.get(chave), dict):
            resultado[chave] = _fundir(resultado[chave], valor)
        else:
            resultado[chave] = valor
    return resultado


@lru_cache(maxsize=1)
def carregar() -> dict[str, Any]:
    cfg = dict(OMISSAO)
    for nome in ("cerebro.yaml", "cerebro.local.yaml"):
        ficheiro = CONFIG_DIR / nome
        if ficheiro.exists():
            cfg = _fundir(cfg, yaml.safe_load(ficheiro.read_text(encoding="utf-8")) or {})
    return cfg


def obter(caminho: str, omissao: Any = None) -> Any:
    """`obter("pensar.modelo")` — notação de pontos, como no robô."""
    no: Any = carregar()
    for parte in caminho.split("."):
        if not isinstance(no, dict) or parte not in no:
            return omissao
        no = no[parte]
    return no


def recarregar() -> None:
    carregar.cache_clear()
