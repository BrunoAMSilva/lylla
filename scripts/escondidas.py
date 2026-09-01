#!/usr/bin/env python3
"""JOGAR ÀS ESCONDIDAS COM A LYLLA — sem esperar por nada.

    # no computador, sem robô nenhum: a Lara escolhe onde se esconde
    ROBO_SIMULAR=1 python scripts/escondidas.py --onde "quarto da Lara"

    # no robô a seguir, com a câmara a valer
    python scripts/escondidas.py

O que se vê no ecrã é a ordem por que ele decidiu procurar — e essa ordem
muda de jogo para jogo, porque ele vai guardando onde já te encontrou
(data/esconderijos.json). Ao terceiro jogo no mesmo sítio, vai lá primeiro.

    python scripts/escondidas.py --esquecer      # limpa a memória toda
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robot import config                      # noqa: E402
from robot.navigation import ir_para, procurar  # noqa: E402


class CaraFingida:
    """A câmara, quando não há câmara.

    Só «vê» a pessoa se o robô estiver mesmo na divisão onde ela se escondeu,
    e nem sempre à primeira — uma cara atrás de uma porta não aparece no
    primeiro fotograma. É o mínimo de honestidade para o ensaio não mentir.
    """

    def __init__(self, quem: str, onde: str) -> None:
        self.quem, self.onde = quem, onde
        self.presente = False
        self.nome = None
        self.vistas = 0

    def atualizar(self) -> "CaraFingida":
        aqui = procurar._divisao_atual()
        na_divisao = aqui is not None and aqui.lower() == self.onde.lower()
        a_espreitar = procurar._fase == "a_espreitar"
        self.vistas = self.vistas + 1 if (na_divisao and a_espreitar) else 0
        self.presente = self.vistas > 12          # ~1,2 s a olhar para ela
        self.nome = self.quem if self.presente else None
        return self


def main() -> int:
    p = argparse.ArgumentParser(description="Jogar às escondidas com a Lylla.")
    p.add_argument("--quem", default="Lara", help="quem é que ele procura")
    p.add_argument("--onde", default=None, help="onde ela se escondeu (só em simulação)")
    p.add_argument("--esquecer", action="store_true", help="apagar a memória de esconderijos")
    args = p.parse_args()

    if args.esquecer:
        procurar.esquecer()
        print("Esconderijos esquecidos. O próximo jogo é do zero.")
        return 0

    erro = ir_para.carregar()
    if erro:
        print(f"❌ {erro}")
        return 1

    mem = procurar.memoria().get(args.quem.lower(), {})
    print(f"\n🙈  À procura d{'a' if args.quem[-1] in 'aA' else 'o'} {args.quem}")
    print(f"    memória: {mem or 'nenhuma — é o primeiro jogo'}")

    estado, mensagem = procurar.comecar(args.quem)
    print(f"    {mensagem}\n")
    if estado != "a_procurar":
        return 1

    ordem = [ir_para._casa.divisoes[k].nome for k in procurar._por_visitar]
    print(f"    ordem de procura: {' → '.join([procurar._alvo_nome] + ordem)}\n")

    olhos = CaraFingida(args.quem, args.onde) if args.onde else None
    if olhos is None and config.a_simular():
        print("⚠️  Em simulação sem --onde, ele nunca encontra ninguém. É de propósito.")
    ultima = ""
    inicio = time.monotonic()
    while procurar.a_procurar() and time.monotonic() - inicio < 300:
        if olhos is not None:
            obs = olhos.atualizar()
        else:
            from robot.brain import companion
            obs = companion.tick(None)
        jogada = procurar.um_passo(obs)
        if jogada.razao != ultima:
            ultima = jogada.razao
            print(f"    · {jogada.razao}")
        if jogada.razao == "onde estou":
            # Perdeu-se a contar os passos. Numa casa a sério, quem responde
            # é a Lara — é o momento mais engraçado do jogo. Aqui responde-se
            # sozinho, para o ensaio poder correr até ao fim.
            aqui = procurar._divisao_atual() or ir_para._casa.divisoes[0].nome
            print(f"    🤖 «perdi-me — em que divisão estou?»   →   «{aqui}»")
            estado, mensagem = procurar.responder(aqui)
            print(f"    · {mensagem}")
            if estado == "recusa":
                return 1
            continue

        if jogada.terminou:
            if jogada.encontrou:
                print(f"\n🎉  Encontrou-te {ir_para.com_artigo(jogada.onde or '?', 'em')}!")
                print(f"    memória agora: {procurar.memoria().get(args.quem.lower(), {})}\n")
            else:
                print(f"\n🤷  {jogada.razao}\n")
            return 0
        if config.a_simular():
            time.sleep(0.01)          # sem hardware, não vale a pena esperar
    procurar.parar()
    print("\n⏱️  Acabou o tempo.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
