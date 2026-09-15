#!/usr/bin/env bash
# ============================================================================
# INSTALAR O CÉREBRO NO MAC MINI
#
#     ./cerebro/instalar.sh              instala e testa
#     ./cerebro/instalar.sh --servico    + arranca sozinho quando o Mac liga
#
# Faz um venv próprio (.venv-cerebro) com o uv, que resolve as dependências
# em segundos em vez de minutos.
#
# ⚠️ PORQUE É QUE NÃO HÁ DOCKER AQUI: um contentor no macOS corre dentro de
#    uma VM Linux, e uma VM não tem acesso ao Metal. Perder-se-ia o MLX e o
#    Neural Engine — que é exatamente a razão de o cérebro viver no mini.
#    O que o Docker dava (ambiente reproduzível) dá-o o venv com versões
#    fixas; o que ele tirava não se recupera. Ver docs/AI-config.md.
# ============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
RAIZ="$(pwd)"
VENV="$RAIZ/.venv-cerebro"
PY="$VENV/bin/python"

echo "🧠 A instalar o cérebro da Lylla em $RAIZ"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "⚠️  Isto não é um Mac. Vai instalar à mesma, mas sem MLX:"
  echo '    põe  ouvir.motor: "faster"  no config/cerebro.yaml.'
fi

# --- uv ---------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "→ a instalar o uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# --- venv -------------------------------------------------------------------
# Caminho absoluto de propósito: neste Mac o `pip` e o `python3` são
# interpretadores DIFERENTES, e isso já custou meia hora três vezes.
echo "→ venv em $VENV"
uv venv "$VENV" --python 3.12 2>/dev/null || uv venv "$VENV"
uv pip install --python "$PY" -r requirements-cerebro.txt

# --- modelos ----------------------------------------------------------------
# O Parakeet desce sozinho do Hugging Face na primeira transcrição (~2,5 GB).
# Fazê-lo AGORA e não à primeira frase da Lara: ninguém quer estrear o robô a
# ver uma barra de download.
echo "→ o Parakeet (o modelo de ouvir; ~2,5 GB na primeira vez)"
"$PY" -c "
from cerebro import ouvir
try:
    o = ouvir.Ouvido('parakeet'); o.aquecer()
    print('   ✅', o.motor.modelo)
except Exception as erro:
    print(f'   ⚠️  não consegui: {erro}')
    print('      (normal fora de Apple Silicon — põe ouvir.motor: \'faster\')')
" || true

echo "→ modelos de voz"
"$PY" scripts/download_models.py --cerebro || echo "⚠️  falhou; corre à mão depois"

# --- Ollama -----------------------------------------------------------------
MODELO="$("$PY" -c 'from cerebro import config; print(config.obter("pensar.modelo"))' 2>/dev/null || echo gemma4:12b)"
if command -v ollama >/dev/null 2>&1; then
  echo "→ Ollama: a preparar o $MODELO"
  # Visível na rede E o modelo sempre em RAM: sem isto, a primeira frase
  # depois de uns minutos de silêncio paga o carregamento todo.
  launchctl setenv OLLAMA_HOST "0.0.0.0:11434"
  launchctl setenv OLLAMA_KEEP_ALIVE "-1"

  # ⚠️ O `ollama pull` é um CLIENTE. Sem servidor de pé dá
  #    "could not connect to ollama server" e o modelo nunca chega.
  # ⚠️ E o `launchctl setenv` só apanha processos lançados DEPOIS: se a app do
  #    Ollama já estava aberta, ficou sem OLLAMA_HOST e o Pi não lhe chega.
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "   ⚠️  o Ollama já estava a correr — fecha-o e volta a abrir, senão fica sem OLLAMA_HOST"
  else
    echo "   a arrancar o ollama serve…"
    OLLAMA_HOST="0.0.0.0:11434" OLLAMA_KEEP_ALIVE="-1" ollama serve >/dev/null 2>&1 &
    for _ in $(seq 1 30); do
      curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
      sleep 1
    done
  fi

  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    ollama pull "$MODELO" || echo "⚠️  não consegui descarregar o $MODELO"
  else
    echo "⚠️  o Ollama não atende em 127.0.0.1:11434"
    echo "    corre:  ollama serve &   e depois:  ollama pull $MODELO"
  fi
else
  echo "⚠️  não há Ollama. Instala em https://ollama.com  e depois:  ollama pull $MODELO"
fi

# --- serviço ----------------------------------------------------------------
if [[ "${1:-}" == "--servico" ]]; then
  PLIST="$HOME/Library/LaunchAgents/casa.lylla.cerebro.plist"
  echo "→ serviço em $PLIST"
  mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
  cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>casa.lylla.cerebro</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string><string>-m</string><string>cerebro.servidor</string>
  </array>
  <key>WorkingDirectory</key><string>$RAIZ</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/lylla-cerebro.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/lylla-cerebro.log</string>
</dict>
</plist>
PLIST_EOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "   ✅ o cérebro arranca sozinho. Ver o que faz:"
  echo "      tail -f ~/Library/Logs/lylla-cerebro.log"
fi

# --- confirmar --------------------------------------------------------------
echo
echo "→ a testar sem modelos (motores de mentira)…"
"$PY" -c "
from fastapi.testclient import TestClient
from cerebro import servidor, ouvir, pensar, falar
import tempfile
c = TestClient(servidor.criar_app(ouvir.Ouvido('teste'), pensar.Cerebro('teste'),
                                  falar.Voz('teste', cache=tempfile.mkdtemp())))
assert c.get('/v1/saude').json()['ok']
assert c.post('/v1/pensar', json={'texto': 'olá'}).json()['fala']
print('   ✅ a API responde')
"

NOME="$(scutil --get LocalHostName 2>/dev/null || hostname)"
cat <<FIM

✅ Pronto.

   Arrancar:   $PY -m cerebro.servidor
   Testar:     curl http://localhost:8420/v1/saude
   Medir:      $PY -m cerebro.medir

   No robô, no config/robot.yaml:
     cerebro:
       url: "http://$NOME.local:8420"

FIM
