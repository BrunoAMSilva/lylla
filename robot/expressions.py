"""AS CARAS DO ROBÔ — carregadas do config/expressoes.yaml.

╔══════════════════════════════════════════════════════════════════════════╗
║  ONDE ESTÁ CADA COISA, E PORQUÊ                                          ║
║                                                                          ║
║  Painel: HUB75 RGB de 64×32, comandado por um ESP32.                     ║
║                                                                          ║
║    · O ESP32 DESENHA. Recebe uma descrição de forma e renderiza a        ║
║      60 imagens por segundo, com transição suave entre expressões,       ║
║      piscar automático e respiração. Tem tempo de sobra para isso.       ║
║                                                                          ║
║    · O Raspberry Pi só DIZ O NOME. `expressao("feliz")` são 40 bytes     ║
║      pela porta série. Custo para o Pi: praticamente zero — o que        ║
║      liberta o CPU todo para o Whisper e o OpenCV.                       ║
║                                                                          ║
║  É esta divisão que permite ter animação fluida sem roubar nada ao       ║
║  reconhecimento de voz.                                                  ║
╚══════════════════════════════════════════════════════════════════════════╝

As expressões são PARAMÉTRICAS, não desenhadas pixel a pixel: descrevem-se
com números (largura, altura, abertura, arco, rotação) e o ESP32 calcula a
forma. É por isso que o morph entre duas caras sai de graça — basta
interpolar os números.

Os nomes dos parâmetros são os mesmos do `bot-face` no browser, de propósito:
abre-se o demo, mexe-se nos sliders, e copiam-se os números para o YAML.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from robot import config

# Valores por omissão de uma expressão. Tudo o que o YAML não disser fica assim.
OMISSAO: dict[str, Any] = {
    "rx": 3.2,
    "ry": 4.2,
    "abertura": 1.0,
    "redondeza": 0.55,
    "rotacao": 0.0,
    "arco": 0.0,
    "cheio": 1.0,
    "olhar_x": 0.0,
    "olhar_y": 0.0,
    "forma": "olhos",
}

# Estas têm de existir — o resto do código conta com elas.
ESSENCIAIS = (
    "neutro", "feliz", "triste", "surpreso", "zangado",
    "a_pensar", "a_dormir", "a_piscar",
)


def _ficheiro():
    return config.CONFIG_DIR / "expressoes.yaml"


@lru_cache(maxsize=1)
def _carregar() -> dict:
    caminho = _ficheiro()
    if not caminho.exists():
        raise FileNotFoundError(
            f"Falta o ficheiro {caminho}.\n"
            f"É lá que vivem as caras do robô."
        )
    return yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}


def cor_base() -> str:
    return str(_carregar().get("cor_base", "36E0FF")).lstrip("#").upper()


def morph_ms() -> int:
    return int(_carregar().get("morph_ms", 180))


@lru_cache(maxsize=1)
def _expressoes() -> dict[str, dict]:
    """Cada expressão, já com os valores por omissão preenchidos."""
    cruas = _carregar().get("expressoes", {}) or {}
    saida = {}
    for nome, params in cruas.items():
        completa = dict(OMISSAO)
        completa["cor"] = cor_base()
        completa.update(params or {})
        # abertura por olho: se não for dita, usa a geral
        completa.setdefault("abertura_esq", completa["abertura"])
        completa.setdefault("abertura_dir", completa["abertura"])
        completa["cor"] = str(completa["cor"]).lstrip("#").upper()
        saida[nome] = completa
    return saida


# ---------------------------------------------------------------------------
# A API que o resto do programa usa
# ---------------------------------------------------------------------------

class _Expressoes(dict):
    """Comporta-se como um dicionário, mas carrega o YAML só quando preciso."""

    def _dados(self) -> dict:
        return _expressoes()

    def __getitem__(self, k):
        return self._dados()[k]

    def __contains__(self, k):
        return k in self._dados()

    def __iter__(self):
        return iter(self._dados())

    def __len__(self):
        return len(self._dados())

    def keys(self):
        return self._dados().keys()

    def items(self):
        return self._dados().items()

    def values(self):
        return self._dados().values()

    def get(self, k, omissao=None):
        return self._dados().get(k, omissao)


EXPRESSOES = _Expressoes()


@lru_cache(maxsize=1)
def _animacoes() -> dict[str, list]:
    cruas = _carregar().get("animacoes", {}) or {}
    return {
        nome: [(passo[0], float(passo[1])) for passo in passos]
        for nome, passos in cruas.items()
    }


class _Animacoes(_Expressoes):
    def _dados(self) -> dict:
        return _animacoes()


ANIMACOES = _Animacoes()


def parametros(nome: str) -> dict:
    """Os números de uma expressão, prontos a enviar ao ESP32."""
    caras = _expressoes()
    if nome not in caras:
        raise ValueError(
            f"Não existe a cara '{nome}'.\n"
            f"As que existem são: {', '.join(sorted(caras))}\n"
            f"(Podes criar novas em config/expressoes.yaml)"
        )
    return dict(caras[nome])


def validar_todas() -> None:
    """Confirma que o YAML faz sentido. Chamado pelos testes e pelo check_health.

    Se a Lara escrever um número impossível ou um nome errado, é melhor
    dizer-lhe já e com clareza do que deixar o robô mostrar uma coisa
    estranha e ninguém perceber porquê.
    """
    caras = _expressoes()
    if not caras:
        raise ValueError("Não há nenhuma expressão em config/expressoes.yaml")

    limites = {
        "rx": (0.5, 12.0), "ry": (0.5, 14.0),
        "abertura": (0.0, 1.0), "abertura_esq": (0.0, 1.0), "abertura_dir": (0.0, 1.0),
        "redondeza": (0.0, 1.0), "rotacao": (-1.5, 1.5), "arco": (-1.0, 1.0),
        "cheio": (0.0, 1.0), "olhar_x": (-1.0, 1.0), "olhar_y": (-1.0, 1.0),
    }
    formas = {"olhos", "coracao", "arranque"}

    for nome, p in caras.items():
        if p["forma"] not in formas:
            raise ValueError(
                f"A cara '{nome}' pede a forma '{p['forma']}', que o ESP32 não sabe "
                f"desenhar. As que existem são: {', '.join(sorted(formas))}"
            )
        for chave, (minimo, maximo) in limites.items():
            valor = p.get(chave)
            if valor is None:
                continue
            try:
                valor = float(valor)
            except (TypeError, ValueError):
                raise ValueError(
                    f"A cara '{nome}' tem '{chave}: {valor}', que não é um número."
                ) from None
            if not minimo <= valor <= maximo:
                raise ValueError(
                    f"A cara '{nome}' tem '{chave}: {valor}', fora do intervalo "
                    f"[{minimo}, {maximo}]."
                )
        cor = p["cor"]
        if len(cor) != 6 or any(c not in "0123456789ABCDEF" for c in cor):
            raise ValueError(
                f"A cara '{nome}' tem a cor '{cor}', que não é um hexadecimal de "
                f"6 dígitos. Exemplo válido: FF3B5C"
            )

    for anim, passos in _animacoes().items():
        for expressao, _pausa in passos:
            if expressao not in caras:
                raise ValueError(
                    f"A animação '{anim}' usa a cara '{expressao}', que não existe.\n"
                    f"As que existem são: {', '.join(sorted(caras))}"
                )

    em_falta = [e for e in ESSENCIAIS if e not in caras]
    if em_falta:
        raise ValueError(
            f"Faltam caras que o resto do código precisa: {', '.join(em_falta)}"
        )


def recarregar() -> None:
    """Volta a ler o YAML — para a Lara ver a mudança sem reiniciar o robô."""
    _carregar.cache_clear()
    _expressoes.cache_clear()
    _animacoes.cache_clear()


if __name__ == "__main__":
    validar_todas()
    caras = _expressoes()
    print(f"{len(caras)} caras e {len(_animacoes())} animações, todas válidas.\n")
    for nome, p in sorted(caras.items()):
        extra = "" if p["forma"] == "olhos" else f"  [{p['forma']}]"
        print(f"  {nome:16} rx={p['rx']:<5} ry={p['ry']:<5} "
              f"arco={p['arco']:<6} #{p['cor']}{extra}")
