"""O PILOTO — as três redes treinadas, a correr no Pi.

╔══════════════════════════════════════════════════════════════════════════╗
║  Aqui não se aprende nada. Isto é só a conta.                            ║
║                                                                          ║
║  O treino aconteceu no browser (docs/escola-de-conducao.html), onde dá   ║
║  para ver centenas de robôs a tentar ao mesmo tempo. O que veio de lá é  ║
║  um ficheiro de números — o piloto.json — e este módulo faz com esses    ║
║  números exatamente a mesma multiplicação que o browser fazia.           ║
║                                                                          ║
║  «Exatamente» é a palavra importante, e não é uma questão de gosto: se   ║
║  a conta aqui for 1% diferente, o robô que se viu a passar na porta no   ║
║  ecrã bate na ombreira em casa. O piloto.json traz lá dentro seis casos  ║
║  de teste (entradas → saídas, calculados no browser) e o                 ║
║  tests/test_navegacao.py obriga este ficheiro a dar o mesmo até à nona   ║
║  casa decimal. É barato, e apanha logo o dia em que alguém mexer numa    ║
║  das duas metades e esquecer a outra.                                    ║
╚══════════════════════════════════════════════════════════════════════════╝

AS TRÊS REDES

    rumo     recebe: para onde é o próximo ponto da rota, e a que velocidade
             vai. NÃO recebe sensores nenhuns — não sabe que há obstáculos.
    evasao   recebe: o que os feixes veem, e a que ritmo isso está a mudar.
             NÃO sabe para onde vai.
    arbitro  recebe um resumo das duas situações e decide DE QUEM SE OUVE
             MAIS neste décimo de segundo, e até que velocidade deixa ir.

A decisão final é a mistura das duas primeiras, com o peso que a terceira
manda. É por isso que se consegue ver, na página, qual delas está a mandar
em cada momento: são três opiniões separadas, não uma papa só.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


def _sigmoide(v: float) -> float:
    return 1.0 / (1.0 + math.exp(-v))


ATIVACOES = {"tanh": math.tanh, "sigmoide": _sigmoide}


class Rede:
    """Uma camada escondida com tanh, e ativações à escolha na saída.

    A ordem dos pesos (W1, b1, W2, b2) é a mesma do browser. Não mexer sem
    mexer lá — e sem correr os testes.
    """

    def __init__(self, dados: dict) -> None:
        self.W1 = np.asarray(dados["W1"], dtype=float)   # (escondidas, entradas)
        self.b1 = np.asarray(dados["b1"], dtype=float)
        self.W2 = np.asarray(dados["W2"], dtype=float)   # (saidas, escondidas)
        self.b2 = np.asarray(dados["b2"], dtype=float)
        self.ativacoes = list(dados["ativacoes"])
        self.entradas = int(dados["entradas"])

    def correr(self, x) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        if x.shape != (self.entradas,):
            raise ValueError(f"esta rede quer {self.entradas} entradas, recebeu {x.shape}")
        escondida = np.tanh(self.W1 @ x + self.b1)
        bruto = self.W2 @ escondida + self.b2
        return np.array([ATIVACOES[a](v) for a, v in zip(self.ativacoes, bruto)])


@dataclass
class Decisao:
    """O que o piloto quer, ANTES de a segurança dar a última palavra."""

    esquerdo: float = 0.0        # -1 a 1, fração da velocidade máxima
    direito: float = 0.0
    viragem: float = 0.0         # -1 esquerda … +1 direita
    velocidade: float = 0.0      # 0 a 1
    peso_evasao: float = 0.0     # 0 = manda o rumo · 1 = manda a evasão
    teto: float = 0.0
    saidas: dict = field(default_factory=dict)


class Piloto:
    def __init__(self, dados: dict) -> None:
        if dados.get("formato") != "lylla-piloto-1":
            raise ValueError("Isto não é um piloto.json da Lylla (falta formato: lylla-piloto-1).")
        self.dados = dados
        self.modo = dados.get("modo", "hibrido")
        self.geracoes = dados.get("geracoes", 0)
        self.fisica = dados["fisica"]
        self.sensores = dados["sensores"]
        self.fusao = dados["fusao"]
        self.rumo = Rede(dados["redes"]["rumo"])
        self.evasao = Rede(dados["redes"]["evasao"])
        self.arbitro = Rede(dados["redes"]["arbitro"])
        self.n_feixes = int(self.sensores["raios"])
        # ⚠️ A MEMÓRIA. São números que a evasão escreve para si própria num
        #    passo e volta a ler no seguinte — é o que lhe permite manter uma
        #    manobra («estou a contornar isto pela direita») que não cabe em
        #    nenhuma leitura de sensor. Sem eles, duas posições que deem a
        #    mesma leitura têm obrigatoriamente a mesma resposta, e contornar
        #    uma parede sem mapa fica impossível por construção.
        #    Pilotos treinados antes de isto existir não trazem o campo:
        #    contam-se as saídas da evasão, que são duas mais uma por cada
        #    número de memória.
        self.n_memoria = int(self.sensores.get(
            "memoria", max(0, len(self.evasao.ativacoes) - 2)))
        self.angulos = [math.radians(a) for a in self.sensores["angulos_graus"]]
        self.alcance_cm = float(self.sensores["alcance_cm"])
        self.ganho_variacao = float(self.sensores.get("variacao_ganho", 20))
        self.v_max_cm_s = float(self.fisica["v_max_cm_s"])
        self.entre_eixos_cm = float(self.fisica["entre_eixos_cm"])
        self.raio_cm = float(self.fisica["raio_cm"])
        self.dt = float(self.fisica["dt"])
        self.lookahead_cm = float(self.fisica["lookahead_cm"])
        self.reiniciar()

    @classmethod
    def de_ficheiro(cls, caminho: str | Path) -> "Piloto":
        return cls(json.loads(Path(caminho).read_text(encoding="utf-8")))

    def reiniciar(self) -> None:
        """Esquecer a viagem anterior. A viragem é filtrada, e o filtro tem
        memória: começar uma viagem nova com a curva da anterior meia feita
        dá um arranque torto."""
        self.viragem = 0.0
        self.feixes_ant = [1.0] * self.n_feixes
        self.memoria = [0.0] * self.n_memoria

    # ------------------------------------------------------------------
    def decidir(self, feixes_cm, erro_rumo: float, dist_alvo_cm: float,
                v_cm_s: float, w_rad_s: float, sem_progresso: int = 0) -> Decisao:
        """Um décimo de segundo de condução.

        feixes_cm     o que cada sensor vê, em centímetros (999 = nada à vista)
        erro_rumo     ângulo entre o nariz do robô e o próximo ponto da rota
        dist_alvo_cm  a que distância está esse ponto
        v_cm_s        a que velocidade vai agora
        w_rad_s       a que velocidade está a rodar
        sem_progresso há quantos passos não se aproxima do destino
        """
        n = self.n_feixes
        d = [min(1.0, max(0.0, c / self.alcance_cm)) for c in feixes_cm[:n]]
        while len(d) < n:
            d.append(1.0)
        dd = [max(-1.0, min(1.0, (self.feixes_ant[i] - d[i]) * self.ganho_variacao)) for i in range(n)]
        self.feixes_ant = d

        v_norm = v_cm_s / self.v_max_cm_s
        w_max = 2 * self.v_max_cm_s / self.entre_eixos_cm
        w_norm = w_rad_s / w_max
        d_min = min(d)
        d_centro = d[n // 2]
        dd_max = max(dd)

        ent_rumo = [math.sin(erro_rumo), math.cos(erro_rumo),
                    min(1.0, max(0.0, dist_alvo_cm / 300.0)), v_norm, w_norm]
        ent_evasao = d + dd + [v_norm, w_norm] + self.memoria
        ent_arbitro = [d_min, d_centro, dd_max, abs(erro_rumo) / math.pi, v_norm,
                       min(1.0, max(0.0, sem_progresso / 100.0))] + self.memoria

        s_rumo = self.rumo.correr(ent_rumo)
        s_evasao = self.evasao.correr(ent_evasao)
        s_arbitro = self.arbitro.correr(ent_arbitro)
        # o que a evasão guardou para o passo seguinte (a seguir às duas
        # saídas de sempre: a viragem e o travão)
        if self.n_memoria:
            self.memoria = [float(v) for v in s_evasao[2:2 + self.n_memoria]]

        peso = float(s_arbitro[0])
        teto = self.fusao["teto_base"] + self.fusao["teto_amplitude"] * float(s_arbitro[1])
        alfa = self.fusao["alfa_base"] + self.fusao["alfa_amplitude"] * float(s_arbitro[2])

        viragem_alvo = (1 - peso) * float(s_rumo[0]) + peso * float(s_evasao[0])
        velocidade = min(float(s_rumo[1]), 1 - float(s_evasao[1])) * teto
        self.viragem += alfa * (viragem_alvo - self.viragem)

        k = self.fusao["viragem_rodas"]
        esq = max(-1.0, min(1.0, velocidade - self.viragem * k))
        dir_ = max(-1.0, min(1.0, velocidade + self.viragem * k))
        return Decisao(
            esquerdo=esq, direito=dir_, viragem=self.viragem, velocidade=velocidade,
            peso_evasao=peso, teto=teto,
            saidas={"rumo": s_rumo.tolist(), "evasao": s_evasao.tolist(), "arbitro": s_arbitro.tolist()},
        )

    # ------------------------------------------------------------------
    def verificar_contra_o_browser(self, tolerancia: float = 1e-9) -> list[str]:
        """Corre os casos de teste que vieram dentro do piloto.json.

        Devolve a lista de diferenças encontradas — vazia quer dizer que esta
        conta em Python dá o mesmo que a do browser.
        """
        problemas = []
        for k, caso in enumerate(self.dados.get("testes", [])):
            for nome, rede in (("rumo", self.rumo), ("evasao", self.evasao), ("arbitro", self.arbitro)):
                obtido = rede.correr(caso["entradas"][nome])
                esperado = np.asarray(caso["saidas"][nome], dtype=float)
                erro = float(np.max(np.abs(obtido - esperado)))
                if erro > tolerancia:
                    problemas.append(f"caso {k}, rede {nome}: diferença de {erro:.3e}")

        # ⚠️ E A MEMÓRIA, QUE É UMA CADEIA E NÃO UMA CONTA.
        # Os casos acima passariam na mesma se a memória entrasse nas casas
        # erradas, ou se se atualizasse ANTES de ser usada em vez de depois:
        # num passo único não se vê. Aqui reproduz-se a sequência inteira que
        # o browser gravou — se a ligação estiver trocada, o primeiro passo
        # bate certo e o segundo já não.
        sequencia = self.dados.get("testes_memoria", [])
        if sequencia:
            memoria = [0.0] * self.n_memoria
            for k, passo in enumerate(sequencia):
                esperada_ent = np.asarray(passo["memoria_a_entrada"], dtype=float)
                if np.max(np.abs(np.asarray(memoria) - esperada_ent)) > tolerancia:
                    problemas.append(
                        f"passo {k}: a memória à entrada não bate certo — "
                        f"o browser tinha {list(esperada_ent)}, aqui está {memoria}")
                    break
                s_evasao = self.evasao.correr(list(passo["evasao_sem_memoria"]) + memoria)
                s_arbitro = self.arbitro.correr(list(passo["arbitro_sem_memoria"]) + memoria)
                for nome, obtido, esperado in (
                        ("evasao", s_evasao, passo["saida_evasao"]),
                        ("arbitro", s_arbitro, passo["saida_arbitro"])):
                    erro = float(np.max(np.abs(obtido - np.asarray(esperado, dtype=float))))
                    if erro > tolerancia:
                        problemas.append(f"passo {k}, rede {nome}: diferença de {erro:.3e}")
                memoria = [float(v) for v in s_evasao[2:2 + self.n_memoria]]
        return problemas
