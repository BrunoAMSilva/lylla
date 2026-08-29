#!/usr/bin/env python3
"""VER O QUE ELA VÊ — com as caixas, os nomes e os tempos, no browser.

    python scripts/ver_visao.py                  → http://<pi>.local:8001
    python scripts/ver_visao.py --porta 9000
    python scripts/ver_visao.py --trocar-cores    se as cores saírem trocadas

⚠️ Este NÃO é o ver_camera.py. São dois de propósito:

    ver_camera.py  · imagem crua, `/usr/bin/python3`, sem venv nem modelos.
                     É para responder «a câmara está viva?» no primeiro dia.
    ver_visao.py   · esta. Corre a deteção e o reconhecimento a cada imagem
                     e desenha por cima. Precisa do venv, do OpenCV e dos
                     modelos — ou seja, de tudo o que a visão precisa.

O QUE ISTO RESOLVE, ALÉM DE MOSTRAR A IMAGEM
Registar uma cara pelo terminal não funciona: as instruções («vira-te para a
esquerda», «levanta o queixo») passam a correr enquanto a pessoa está a olhar
para a câmara — de costas para o ecrã. Aqui a instrução aparece ao lado do
vídeo, e é a pessoa que decide quando tirar a foto, com um botão. A Lara vê a
própria cara com a caixa à volta enquanto posa. Não há contagem decrescente
nenhuma.

🔒 PRIVACIDADE
   · A imagem vai para o browser e NÃO fica guardada em lado nenhum.
   · Do registo saem 128 números por pessoa, em data/faces/, nunca fotografias.
   · Em funcionamento normal o robô não transmite imagem nenhuma (§10.3 do
     PLANO.md). Isto é uma ferramenta de teste: liga-se, usa-se, Ctrl+C.
   · Não há senha. Quem estiver na rede de casa vê a imagem e pode registar
     alguém. Não deixar a correr sozinho, e nunca virado para fora de casa.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import unicodedata
from http import server
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robot import config  # noqa: E402
from robot.perception import camera, faces  # noqa: E402

POSES = [
    "Olha para a câmara",
    "Sorri",
    "Vira-te um bocadinho para a esquerda",
    "Vira-te um bocadinho para a direita",
    "Levanta um pouco o queixo",
    "Baixa um pouco o queixo",
    "Faz uma cara séria",
    "Chega-te mais perto",
]

# Nome de pessoa: vira um ficheiro em data/faces/, e isto vem de um POST.
# Sem esta validação, um nome com "../" escrevia fora da pasta.
NOME_VALIDO = re.compile(r"^[^\W\d_][\w \-']{0,30}$", re.UNICODE)

CIANO = (255, 224, 54)      # BGR de #36E0FF — conhecido
AMBAR = (32, 176, 255)      # BGR de #FFB020 — desconhecido
CINZA = (150, 150, 150)


def sem_acentos(texto: str) -> str:
    """O cv2.putText não sabe desenhar acentos — saem '?'. Só para as etiquetas."""
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


# ---------------------------------------------------------------------------
# O estado partilhado entre o ciclo da câmara e quem está a ver
# ---------------------------------------------------------------------------
class Estado:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.novo = threading.Condition()
        self.jpeg: bytes | None = None
        self.imagem = None          # a imagem CRUA, sem desenhos (para o registo)
        self.caras: list = []
        self.medidas = {"fps": 0.0, "ms_detetar": 0.0, "ms_reconhecer": 0.0,
                        "ms_total": 0.0, "caras": 0}
        self.vistos: list[dict] = []
        self.erro: str | None = None
        # registo
        self.reg_ativo = False
        self.reg_nome = ""
        self.reg_vetores: list = []
        self.reg_indice = 0
        self.reg_mensagem = ""

    def instantaneo(self) -> dict:
        with self.lock:
            return {
                "medidas": dict(self.medidas),
                "vistos": list(self.vistos),
                "erro": self.erro,
                "conhecidos": faces.pessoas_conhecidas(),
                "limiar": float(config.obter("faces.limiar", 0.45)),
                "registo": {
                    "ativo": self.reg_ativo,
                    "nome": self.reg_nome,
                    "guardadas": len(self.reg_vetores),
                    "total": int(config.obter("faces.fotos_por_pessoa", 8)),
                    "pose": (POSES[self.reg_indice % len(POSES)]
                             if self.reg_ativo else ""),
                    "numero": self.reg_indice + 1 if self.reg_ativo else 0,
                    "mensagem": self.reg_mensagem,
                    "pode_guardar": len(self.reg_vetores) >= 3,
                },
            }


ESTADO = Estado()


# ---------------------------------------------------------------------------
# O ciclo: tirar, detetar, reconhecer, desenhar
# ---------------------------------------------------------------------------
def desenhar(cv2, imagem, caras, etiquetas, medidas):
    for cara, (nome, semelhanca) in zip(caras, etiquetas):
        x, y, w, h = (int(v) for v in cara[:4])
        cor = CIANO if nome else AMBAR
        cv2.rectangle(imagem, (x, y), (x + w, y + h), cor, 2)

        # os 5 pontos que o YuNet devolve: olhos, nariz, cantos da boca.
        # Ver isto ajuda a perceber uma semelhança baixa — se os pontos
        # estiverem tortos, o SFace está a comparar uma cara mal endireitada.
        for i in range(4, 14, 2):
            cv2.circle(imagem, (int(cara[i]), int(cara[i + 1])), 2, cor, -1)

        texto = f"{sem_acentos(nome)} {semelhanca:.2f}" if nome else f"? {semelhanca:.2f}"
        base = y - 8 if y > 24 else y + h + 20
        cv2.putText(imagem, texto, (x, base),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
        cv2.putText(imagem, texto, (x, base),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, cor, 1)

    hud = (f"{medidas['fps']:.1f} fps  |  detetar {medidas['ms_detetar']:.1f} ms"
           f"  |  reconhecer {medidas['ms_reconhecer']:.1f} ms")
    cv2.putText(imagem, hud, (10, imagem.shape[0] - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
    cv2.putText(imagem, hud, (10, imagem.shape[0] - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, CINZA, 1)
    return imagem


def ciclo(parar: threading.Event, trocar_cores: bool) -> None:
    import cv2

    anterior = time.perf_counter()
    fps = 0.0
    while not parar.is_set():
        inicio = time.perf_counter()
        imagem = camera.tirar_foto()
        if imagem is None:
            with ESTADO.lock:
                ESTADO.erro = "sem imagem da câmara"
            time.sleep(1.0)
            continue
        if trocar_cores:
            imagem = cv2.cvtColor(imagem, cv2.COLOR_RGB2BGR)

        t = time.perf_counter()
        caras = faces.detetar(imagem)
        ms_detetar = (time.perf_counter() - t) * 1000

        etiquetas, ms_reconhecer = [], 0.0
        if caras:
            t = time.perf_counter()
            for cara in caras:
                etiquetas.append(faces.identificar(faces.assinatura(imagem, cara)))
            ms_reconhecer = (time.perf_counter() - t) * 1000

        agora = time.perf_counter()
        fps = 0.8 * fps + 0.2 * (1.0 / max(agora - anterior, 1e-6))
        anterior = agora
        medidas = {
            "fps": fps,
            "ms_detetar": ms_detetar,
            "ms_reconhecer": ms_reconhecer,
            "ms_total": (agora - inicio) * 1000,
            "caras": len(caras),
        }

        anotada = desenhar(cv2, imagem.copy(), caras, etiquetas, medidas)
        ok, buffer = cv2.imencode(".jpg", anotada, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            continue

        with ESTADO.lock:
            ESTADO.imagem = imagem          # a crua, para o registo
            ESTADO.caras = caras
            ESTADO.medidas = medidas
            ESTADO.erro = None
            ESTADO.vistos = [
                {"nome": n, "semelhanca": round(float(s), 3),
                 "area": round(float(c[2] * c[3]) / (imagem.shape[0] * imagem.shape[1]), 4),
                 "confianca": round(float(c[14]), 3) if len(c) > 14 else None}
                for c, (n, s) in zip(caras, etiquetas)
            ]
        with ESTADO.novo:
            ESTADO.jpeg = bytes(buffer)
            ESTADO.novo.notify_all()


# ---------------------------------------------------------------------------
# O registo, comandado pelo browser
# ---------------------------------------------------------------------------
def registo_iniciar(nome: str) -> dict:
    nome = (nome or "").strip()
    if not NOME_VALIDO.match(nome):
        return {"erro": "Nome inválido. Letras, espaços e hífenes; começa por letra."}
    with ESTADO.lock:
        ESTADO.reg_ativo = True
        ESTADO.reg_nome = nome
        ESTADO.reg_vetores = []
        ESTADO.reg_indice = 0
        ESTADO.reg_mensagem = f"Vamos lá. {POSES[0]}."
    return {"ok": True}


def registo_capturar() -> dict:
    with ESTADO.lock:
        if not ESTADO.reg_ativo:
            return {"erro": "não há registo a decorrer"}
        imagem, caras = ESTADO.imagem, list(ESTADO.caras)

    if imagem is None:
        return {"erro": "sem imagem"}
    if not caras:
        with ESTADO.lock:
            ESTADO.reg_mensagem = "Não vejo ninguém — chega-te mais perto."
        return {"ok": False}
    if len(caras) > 1:
        with ESTADO.lock:
            ESTADO.reg_mensagem = f"Vejo {len(caras)} caras — fica só uma pessoa à frente."
        return {"ok": False}

    vetor = faces.assinatura(imagem, caras[0])
    if vetor is None:
        with ESTADO.lock:
            ESTADO.reg_mensagem = "Não consegui ler essa cara. Outra vez."
        return {"ok": False}

    with ESTADO.lock:
        ESTADO.reg_vetores.append(vetor)
        ESTADO.reg_indice += 1
        n, total = len(ESTADO.reg_vetores), int(config.obter("faces.fotos_por_pessoa", 8))
        if n >= total:
            ESTADO.reg_mensagem = f"✅ {n} de {total}. Já chega — carrega em Guardar."
        else:
            ESTADO.reg_mensagem = (f"✅ {n} de {total} guardadas. "
                                   f"{POSES[ESTADO.reg_indice % len(POSES)]}.")
    return {"ok": True}


def registo_guardar() -> dict:
    with ESTADO.lock:
        nome, vetores = ESTADO.reg_nome, list(ESTADO.reg_vetores)
    if len(vetores) < 3:
        return {"erro": f"só tenho {len(vetores)} fotos boas — preciso de 3"}
    try:
        faces.guardar_pessoa(nome, vetores)
    except Exception as erro:  # noqa: BLE001
        return {"erro": str(erro)}
    with ESTADO.lock:
        ESTADO.reg_ativo = False
        ESTADO.reg_mensagem = f"🎉 A Lylla já conhece {nome} ({len(vetores)} fotos)."
        ESTADO.reg_vetores = []
    return {"ok": True}


def registo_cancelar() -> dict:
    with ESTADO.lock:
        ESTADO.reg_ativo = False
        ESTADO.reg_vetores = []
        ESTADO.reg_mensagem = ""
    return {"ok": True}


def apagar_pessoa(nome: str) -> dict:
    if not NOME_VALIDO.match((nome or "").strip()):
        return {"erro": "nome inválido"}
    return {"ok": faces.apagar_pessoa(nome.strip())}


# ---------------------------------------------------------------------------
# A página
# ---------------------------------------------------------------------------
PAGINA = """<!doctype html>
<html lang="pt"><head><meta charset="utf-8"><title>Lylla — o que ela vê</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--fundo:#161B22;--painel:#1C232C;--linha:#263040;--texto:#F4F6F8;
      --ciano:#36E0FF;--azul:#1E7FD4;--suave:#8A94A6;--ambar:#FFB020}
*{box-sizing:border-box}
body{margin:0;background:var(--fundo);color:var(--texto);
     font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:14px 18px;border-bottom:1px solid var(--linha);
       display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
h1{margin:0;font-size:17px;font-weight:600}
header span{color:var(--suave);font-size:13px}
main{display:grid;grid-template-columns:minmax(0,1fr) 350px;gap:18px;padding:18px;align-items:start}
@media(max-width:920px){main{grid-template-columns:1fr}}
.video{background:#000;border-radius:12px;overflow:hidden;line-height:0;
       border:1px solid var(--linha);min-height:240px;display:flex;
       align-items:center;justify-content:center}
.video img{width:100%;height:auto;display:block}
.video::after{content:"à espera de imagem…";color:var(--suave);font-size:13px;
              line-height:1.5;position:absolute;pointer-events:none;opacity:0;
              animation:aparecer 0s linear 2s forwards}
@keyframes aparecer{to{opacity:1}}
.video img{position:relative;z-index:1;background:#000}
/* durante o registo, a pose sobe para junto do vídeo — no telemóvel é a
   diferença entre ver a instrução e ter de fazer scroll com a cara na câmara */
.coluna{display:flex;flex-direction:column}
.coluna.a-registar #cartao-registo{order:-1}
.cartao{background:var(--painel);border:1px solid var(--linha);border-radius:12px;
        padding:14px 16px;margin-bottom:14px}
.cartao h2{margin:0 0 10px;font-size:12px;text-transform:uppercase;
           letter-spacing:.09em;color:var(--suave);font-weight:700}
dl{display:grid;grid-template-columns:1fr auto;gap:5px 12px;margin:0;
   font-variant-numeric:tabular-nums}
dt{color:var(--suave)} dd{margin:0;text-align:right;font-weight:600}
ul{list-style:none;margin:0;padding:0}
li{display:flex;justify-content:space-between;gap:10px;padding:5px 0;
   border-bottom:1px solid var(--linha);font-variant-numeric:tabular-nums}
li:last-child{border-bottom:0}
.conhecido{color:var(--ciano)} .estranho{color:var(--ambar)}
button{font:inherit;font-weight:600;border:0;border-radius:9px;padding:10px 14px;
       cursor:pointer;background:var(--azul);color:#fff}
button:disabled{opacity:.4;cursor:not-allowed}
button.grande{width:100%;padding:18px;font-size:19px;background:var(--ciano);color:#08131A}
button.discreto{background:transparent;color:var(--suave);border:1px solid var(--linha);padding:7px 11px}
button.apagar{background:transparent;color:var(--suave);border:0;padding:2px 6px;font-size:13px}
input[type=text]{font:inherit;width:100%;padding:10px;border-radius:9px;
                 border:1px solid var(--linha);background:#111820;color:var(--texto)}
label.consent{display:flex;gap:9px;align-items:flex-start;margin:12px 0;
              font-size:13px;color:var(--suave);cursor:pointer}
.privacidade{font-size:13px;color:var(--suave);background:#111820;
             border-left:3px solid var(--azul);padding:10px 12px;border-radius:0 8px 8px 0}
.pose{font-size:23px;font-weight:700;line-height:1.25;margin:6px 0 4px}
.contador{color:var(--suave);font-size:13px;letter-spacing:.06em;text-transform:uppercase}
.mensagem{min-height:44px;margin:12px 0;font-size:14px}
.dica{color:var(--suave);font-size:12px;margin-top:10px}
.barra{display:flex;gap:4px;margin:12px 0}
.barra i{flex:1;height:5px;border-radius:3px;background:var(--linha)}
.barra i.feito{background:var(--ciano)}
.erro{color:var(--ambar)}
</style></head><body>
<header>
  <h1>O que a Lylla vê</h1>
  <span id="cabecalho">a ligar…</span>
</header>
<main>
  <div class="video"><img src="/stream.mjpg" alt=""></div>
  <div class="coluna" id="coluna">
    <div class="cartao">
      <h2>Medidas</h2>
      <dl>
        <dt>imagens por segundo</dt><dd id="m-fps">—</dd>
        <dt>detetar (YuNet)</dt><dd id="m-det">—</dd>
        <dt>reconhecer (SFace)</dt><dd id="m-rec">—</dd>
        <dt>volta completa</dt><dd id="m-tot">—</dd>
      </dl>
      <p class="dica" id="dica-tempo"></p>
    </div>

    <div class="cartao">
      <h2>Quem vejo agora</h2>
      <ul id="vistos"><li><span>—</span></li></ul>
      <p class="dica">Limiar: <b id="limiar">—</b>. Acima disto tem nome; abaixo é «?».</p>
    </div>

    <div class="cartao" id="cartao-registo">
      <h2>Ensinar uma cara</h2>
      <div id="registo-parado">
        <div class="privacidade">
          Lê isto em voz alta à pessoa:<br><br>
          «Vou ensinar o robô a reconhecer-te. Ele <b>não</b> guarda
          fotografias — guarda 128 números que o ajudam a saber que és tu.
          Ficam só neste robô, nunca saem de casa, e podes pedir para os
          apagar quando quiseres.»
        </div>
        <label class="consent">
          <input type="checkbox" id="consentimento">
          <span>A pessoa ouviu e concorda.</span>
        </label>
        <input type="text" id="nome" placeholder="Nome (ex.: Lara)" autocomplete="off">
        <p></p>
        <button id="comecar" disabled>Começar</button>
        <p class="erro" id="erro-nome"></p>
      </div>

      <div id="registo-a-decorrer" hidden>
        <p class="contador" id="reg-contador"></p>
        <p class="pose" id="reg-pose"></p>
        <div class="barra" id="reg-barra"></div>
        <button class="grande" id="capturar">Capturar</button>
        <p class="dica">Ou carrega na barra de espaços.</p>
        <p class="mensagem" id="reg-mensagem"></p>
        <button class="discreto" id="guardar" disabled>Guardar</button>
        <button class="discreto" id="cancelar">Cancelar</button>
      </div>
    </div>

    <div class="cartao">
      <h2>Quem ela já conhece</h2>
      <ul id="conhecidos"><li><span>—</span></li></ul>
    </div>
  </div>
</main>
<script>
const $ = id => document.getElementById(id);
let aDecorrer = false;

async function api(caminho, corpo) {
  const r = await fetch(caminho, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(corpo || {})
  });
  return r.json();
}

function pinta(e) {
  const m = e.medidas;
  $('m-fps').textContent = m.fps.toFixed(1);
  $('m-det').textContent = m.ms_detetar.toFixed(1) + ' ms';
  $('m-rec').textContent = m.caras ? m.ms_reconhecer.toFixed(1) + ' ms' : '— (sem caras)';
  $('m-tot').textContent = m.ms_total.toFixed(0) + ' ms';
  $('dica-tempo').textContent = m.caras
    ? 'Reconhecer custa o mesmo em qualquer resolução: o SFace endireita a cara para 112×112 antes de olhar.'
    : 'Sem ninguém à frente, o SFace nem chega a correr — é essa a poupança toda.';
  $('cabecalho').textContent = e.erro ? '⚠️ ' + e.erro
    : m.caras + (m.caras === 1 ? ' cara' : ' caras') + ' · ' + m.fps.toFixed(0) + ' fps';
  $('limiar').textContent = e.limiar.toFixed(2);

  $('vistos').innerHTML = e.vistos.length ? e.vistos.map(v =>
    '<li><span class="' + (v.nome ? 'conhecido' : 'estranho') + '">' +
    (v.nome || 'não conheço') + '</span><span>' + v.semelhanca.toFixed(2) + '</span></li>'
  ).join('') : '<li><span style="color:var(--suave)">ninguém à frente</span></li>';

  $('conhecidos').innerHTML = e.conhecidos.length ? e.conhecidos.map(n =>
    '<li><span>' + n + '</span><button class="apagar" data-n="' + n + '">apagar</button></li>'
  ).join('') : '<li><span style="color:var(--suave)">ainda ninguém</span></li>';

  const r = e.registo;
  aDecorrer = r.ativo;
  $('coluna').classList.toggle('a-registar', r.ativo);
  $('registo-parado').hidden = r.ativo;
  $('registo-a-decorrer').hidden = !r.ativo;
  if (r.ativo) {
    $('reg-contador').textContent = 'A ensinar ' + r.nome + ' · foto ' + r.numero;
    $('reg-pose').textContent = r.pose;
    $('reg-barra').innerHTML = Array.from({length: r.total},
      (_, i) => '<i class="' + (i < r.guardadas ? 'feito' : '') + '"></i>').join('');
    $('guardar').disabled = !r.pode_guardar;
    $('guardar').textContent = 'Guardar (' + r.guardadas + ')';
  }
  $('reg-mensagem').textContent = r.mensagem;
}

async function actualiza() {
  try { pinta(await (await fetch('/api/estado')).json()); }
  catch (_) { $('cabecalho').textContent = '⚠️ sem ligação ao robô'; }
}

function podeComecar() {
  $('comecar').disabled = !($('consentimento').checked && $('nome').value.trim());
}
$('consentimento').addEventListener('change', podeComecar);
$('nome').addEventListener('input', podeComecar);

$('comecar').addEventListener('click', async () => {
  const r = await api('/api/registar/iniciar', {nome: $('nome').value});
  $('erro-nome').textContent = r.erro || '';
  actualiza();
});
$('capturar').addEventListener('click', async () => { await api('/api/registar/capturar'); actualiza(); });
$('guardar').addEventListener('click', async () => {
  const r = await api('/api/registar/guardar');
  if (r.erro) $('reg-mensagem').textContent = r.erro;
  actualiza();
});
$('cancelar').addEventListener('click', async () => { await api('/api/registar/cancelar'); actualiza(); });
$('conhecidos').addEventListener('click', async ev => {
  const n = ev.target.dataset && ev.target.dataset.n;
  if (n && confirm('Apagar ' + n + '? A Lylla deixa de o reconhecer.')) {
    await api('/api/apagar', {nome: n}); actualiza();
  }
});
document.addEventListener('keydown', ev => {
  if (ev.code === 'Space' && aDecorrer && ev.target.tagName !== 'INPUT') {
    ev.preventDefault(); $('capturar').click();
  }
});

actualiza();
setInterval(actualiza, 400);
</script></body></html>
"""


# ---------------------------------------------------------------------------
# O servidor
# ---------------------------------------------------------------------------
ROTAS = {
    "/api/registar/iniciar": lambda c: registo_iniciar(c.get("nome", "")),
    "/api/registar/capturar": lambda c: registo_capturar(),
    "/api/registar/guardar": lambda c: registo_guardar(),
    "/api/registar/cancelar": lambda c: registo_cancelar(),
    "/api/apagar": lambda c: apagar_pessoa(c.get("nome", "")),
}


class Pedido(server.BaseHTTPRequestHandler):
    def _json(self, dados, codigo: int = 200) -> None:
        corpo = json.dumps(dados).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            corpo = PAGINA.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
        elif self.path == "/api/estado":
            self._json(ESTADO.instantaneo())
        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    with ESTADO.novo:
                        ESTADO.novo.wait(timeout=5.0)
                        dados = ESTADO.jpeg
                    if not dados:
                        continue
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(dados)))
                    self.end_headers()
                    self.wfile.write(dados)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # fecharam a página — normal
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        accao = ROTAS.get(self.path)
        if accao is None:
            self.send_error(404)
            return
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(tamanho) or b"{}") if tamanho else {}
            if not isinstance(corpo, dict):
                raise ValueError("o corpo tem de ser um objeto")
        except Exception as erro:  # noqa: BLE001
            self._json({"erro": f"pedido inválido: {erro}"}, 400)
            return
        self._json(accao(corpo))

    def log_message(self, *args) -> None:  # silêncio no terminal
        pass


class Servidor(server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--porta", type=int, default=8001)
    p.add_argument("--trocar-cores", action="store_true",
                   help="se as cores saírem trocadas (azul por vermelho)")
    args = p.parse_args()

    if config.a_simular():
        print("\n  ❌ Modo simulação — não há câmara.")
        print("     Isto só corre no Pi, com o venv ativo.\n")
        return 1
    if not faces.disponivel():
        print("\n  ❌ A visão não arrancou (o erro está acima). Sem isso não há caixas.\n")
        return 1
    if camera.tirar_foto() is None:
        print("\n  ❌ Sem câmara. Vê o docs/FASE9-visao.md, passo 2.\n")
        return 1

    parar = threading.Event()
    threading.Thread(target=ciclo, args=(parar, args.trocar_cores), daemon=True).start()

    import socket
    nome = socket.gethostname()
    print(f"\n👁️  Abre no browser (Mac ou telemóvel):")
    print(f"    http://{nome}.local:{args.porta}\n")
    print("    Ciano = conhece · âmbar = não conhece.")
    print("    O registo faz-se na própria página — sem contagens decrescentes.")
    print("    Ctrl+C para parar.\n")

    servidor = Servidor(("0.0.0.0", args.porta), Pedido)  # noqa: S104
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n   parado.\n")
    finally:
        parar.set()
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
