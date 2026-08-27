#!/usr/bin/env bash
# ============================================================================
# PÔR NO MINI O QUE ESTÁ AQUI
#
#     ./scripts/deploy_mini.sh                    git pull + deps + reiniciar
#     ./scripts/deploy_mini.sh --so-reiniciar     só reiniciar (mudei o YAML)
#     ./scripts/deploy_mini.sh --daqui            envia ESTA cópia (sem git)
#
# Corre-se no portátil e fala com o mini por SSH. Sem contentores, sem
# registos de imagens: o mini tem o mesmo repositório e um venv.
#
# O endereço do mini vem do MINI_SSH, ou do config/robot.yaml.
# ============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
RAIZ_LOCAL="$(pwd)"

MINI="${MINI_SSH:-}"
if [[ -z "$MINI" ]]; then
  HOST="$(python3 -c "
import re,sys
t=open('config/robot.yaml',encoding='utf-8').read()
m=re.search(r'cerebro:.*?url:\s*\"https?://([^:/\"]+)', t, re.S)
print(m.group(1) if m else '')
" 2>/dev/null || true)"
  [[ -n "$HOST" ]] && MINI="$USER@$HOST"
fi
[[ -z "$MINI" ]] && { echo "❌ não sei onde é o mini. Usa:  MINI_SSH=user@mini.local $0"; exit 1; }

REMOTO="${MINI_DIR:-~/my-robot}"
MODO="${1:-}"

echo "🧠 mini: $MINI   pasta: $REMOTO"

if [[ "$MODO" == "--daqui" ]]; then
  echo "→ a enviar esta cópia (sem .git, sem venvs, sem data)"
  rsync -az --delete \
    --exclude '.git' --exclude '.venv*' --exclude '__pycache__' \
    --exclude 'data/gravacoes' --exclude 'models/*.onnx' \
    "$RAIZ_LOCAL/" "$MINI:$REMOTO/"
elif [[ "$MODO" != "--so-reiniciar" ]]; then
  echo "→ git pull no mini"
  ssh "$MINI" "cd $REMOTO && git pull --ff-only"
  echo "→ dependências"
  ssh "$MINI" "cd $REMOTO && (command -v uv >/dev/null && uv pip install --python .venv-cerebro/bin/python -r requirements-cerebro.txt || .venv-cerebro/bin/python -m pip install -q -r requirements-cerebro.txt)"
fi

echo "→ reiniciar"
# Se estiver como serviço, o launchd volta a levantá-lo sozinho (KeepAlive).
ssh "$MINI" "launchctl kickstart -k gui/\$(id -u)/casa.lylla.cerebro 2>/dev/null || echo '   (não está como serviço — arranca à mão: python -m cerebro.servidor)'"

echo "→ à espera que responda…"
URL="http://$(echo "$MINI" | cut -d@ -f2):8420/v1/saude"
for _ in $(seq 1 30); do
  if curl -fs --max-time 2 "$URL" >/dev/null 2>&1; then
    echo "   ✅ de pé:"
    curl -s "$URL" | python3 -m json.tool 2>/dev/null || curl -s "$URL"
    exit 0
  fi
  sleep 1
done
echo "⚠️  não respondeu em 30 s. Ver:  ssh $MINI 'tail -30 ~/Library/Logs/lylla-cerebro.log'"
exit 1
