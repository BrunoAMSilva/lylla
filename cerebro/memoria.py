"""A MEMÓRIA — o que a Lylla sabe de cada pessoa, guardado no mac mini.

Duas coisas diferentes, que não se misturam:

  · o HISTÓRICO da conversa (em pensar.py) — as últimas frases, por pessoa,
    e que se deita fora ao fim de 15 minutos de silêncio;
  · a MEMÓRIA (aqui) — factos que duram: «a Lara anda no 5.º ano», «gosta de
    gatos». Sobrevive a reinícios e começa cada conversa nova.

O ficheiro (data/memoria.json, fora do Git) tem esta forma e edita-se à mão:

    {
      "partilhado": ["O Bruno é o pai da Lara."],
      "pessoas": {
        "Lara":  ["Anda no 5.º ano.", "Adora robôs e gatos."],
        "Bruno": ["Trabalha em acessibilidade."]
      }
    }

⚠️ A REGRA QUE JUSTIFICA ISTO SER POR PESSOA: o que o Bruno conta não aparece
   quando é a Lara a falar. Só vai para o prompt a secção `partilhado` e a da
   pessoa que está à frente do robô. Quem não é reconhecido não tem secção —
   e nada do que diz fica guardado.

O modelo escreve aqui através do campo `lembrar` da resposta (ver pensar.py).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from cerebro import config

MAX_POR_PESSOA = 40      # os mais antigos saem primeiro
MAX_CARACTERES = 140     # um facto é uma frase, não um parágrafo


def _caminho_omissao() -> Path:
    return config.RAIZ / "data" / "memoria.json"


def _normalizar(texto: str) -> str:
    return " ".join(str(texto).lower().strip(" .!").split())


class Memoria:
    def __init__(self, caminho: str | Path | None = None) -> None:
        caminho = caminho or config.obter("memoria.ficheiro") or _caminho_omissao()
        self.caminho = Path(caminho).expanduser()
        if not self.caminho.is_absolute():
            self.caminho = config.RAIZ / self.caminho
        self._lock = threading.Lock()
        self._dados = self._ler()

    # -- disco --------------------------------------------------------------

    def _ler(self) -> dict:
        vazio = {"partilhado": [], "pessoas": {}}
        if not self.caminho.exists():
            exemplo = config.CONFIG_DIR / "memoria.exemplo.json"
            if not exemplo.exists():
                return vazio
            origem = exemplo
        else:
            origem = self.caminho
        try:
            dados = json.loads(origem.read_text(encoding="utf-8"))
        except (OSError, ValueError) as erro:
            # Um ficheiro estragado à mão não pode calar o robô.
            print(f"⚠️  Memória ilegível em {origem} ({erro}). Começo sem memória.")
            return vazio
        if not isinstance(dados, dict):
            return vazio
        partilhado = [str(f) for f in dados.get("partilhado") or [] if str(f).strip()]
        pessoas = {
            str(nome): [str(f) for f in (factos or []) if str(f).strip()]
            for nome, factos in (dados.get("pessoas") or {}).items()
            if isinstance(factos, list)
        }
        return {"partilhado": partilhado, "pessoas": pessoas}

    def _gravar(self) -> None:
        # Escrever ao lado e mudar o nome: um ficheiro a meio é memória perdida.
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        descritor, temporario = tempfile.mkstemp(dir=self.caminho.parent, suffix=".parcial")
        with os.fdopen(descritor, "w", encoding="utf-8") as f:
            json.dump(self._dados, f, ensure_ascii=False, indent=2)
        os.replace(temporario, self.caminho)

    def recarregar(self) -> None:
        with self._lock:
            self._dados = self._ler()

    # -- ler ----------------------------------------------------------------

    def _chave(self, pessoa: str | None) -> str | None:
        """O nome como está no ficheiro, sem ligar a maiúsculas."""
        if not pessoa:
            return None
        for nome in self._dados["pessoas"]:
            if nome.lower() == pessoa.lower():
                return nome
        return pessoa

    def factos(self, pessoa: str | None) -> list[str]:
        with self._lock:
            chave = self._chave(pessoa)
            return list(self._dados["pessoas"].get(chave, [])) if chave else []

    def tudo(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._dados))

    def para_prompt(self, pessoa: str | None, lingua: str = "pt") -> str:
        """O bloco que vai no system prompt. Vazio se não houver nada a dizer."""
        en = lingua == "en"
        with self._lock:
            partilhado = list(self._dados["partilhado"])
            chave = self._chave(pessoa)
            pessoais = list(self._dados["pessoas"].get(chave, [])) if chave else []
        linhas: list[str] = []
        if partilhado:
            linhas.append("WHAT YOU KNOW ABOUT THE FAMILY:" if en else "O QUE SABES DA FAMÍLIA:")
            linhas += [f"- {f}" for f in partilhado]
        if pessoa and pessoais:
            linhas.append(f"WHAT YOU KNOW ABOUT {pessoa.upper()} (the person talking to you):" if en
                          else f"O QUE SABES SOBRE {pessoa.upper()} (quem está a falar contigo):")
            linhas += [f"- {f}" for f in pessoais]
        if not linhas:
            return ""
        linhas.append(
            "Use this naturally, only when it helps. Never mention what other people told you."
            if en else
            "Usa isto com naturalidade, só quando ajuda. Nunca contes o que outras pessoas te disseram."
        )
        return "\n\n" + "\n".join(linhas)

    # -- escrever -----------------------------------------------------------

    def lembrar(self, pessoa: str | None, factos) -> list[str]:
        """Guarda factos novos sobre `pessoa`. Devolve os que eram mesmo novos.

        Sem pessoa reconhecida não se guarda nada: não há a quem pertencer.
        """
        if not pessoa or not isinstance(factos, list):
            return []
        novos: list[str] = []
        with self._lock:
            chave = self._chave(pessoa)
            lista = self._dados["pessoas"].setdefault(chave, [])
            conhecidos = {_normalizar(f) for f in lista}
            for facto in factos:
                if not isinstance(facto, str):
                    continue
                facto = " ".join(facto.split())[:MAX_CARACTERES].strip()
                if len(facto) < 4 or _normalizar(facto) in conhecidos:
                    continue
                lista.append(facto)
                conhecidos.add(_normalizar(facto))
                novos.append(facto)
            del lista[:-MAX_POR_PESSOA]
            if novos:
                try:
                    self._gravar()
                except OSError as erro:
                    print(f"⚠️  Não consegui gravar a memória ({erro}).")
        return novos

    def esquecer(self, pessoa: str | None = None) -> None:
        """Apaga o que sabe de uma pessoa (o `partilhado` só se edita à mão)."""
        with self._lock:
            chave = self._chave(pessoa)
            if chave is None:
                return
            self._dados["pessoas"].pop(chave, None)
            self._gravar()
