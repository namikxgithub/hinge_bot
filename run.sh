#!/usr/bin/env bash
# Usage: ./run.sh            (dry run: capture + draft, no taps)
#        ./run.sh --live     (real loop with review page)
cd "$(dirname "$0")"
BACKEND=$(python3 -c "from hinge_bot import config as C; print(C.BACKEND)")
if [ "$BACKEND" = "ollama" ]; then
  if ! curl -s http://127.0.0.1:11434/api/tags >/dev/null; then
    echo "starting local model server"
    (OLLAMA_MODELS="$HOME/.local/ollama/models" nohup "$HOME/.local/ollama/bin/ollama" serve >"$HOME/.local/ollama/serve.log" 2>&1 &)
    for i in $(seq 1 20); do curl -s http://127.0.0.1:11434/api/tags >/dev/null && break; sleep 1; done
  fi
else
  case "${ANTHROPIC_API_KEY:-}" in
    "")      echo "ANTHROPIC_API_KEY is not set. Export it, or set BACKEND = \"ollama\" in hinge_bot/config.py"; exit 1;;
    *"..."*) echo "ANTHROPIC_API_KEY looks like the placeholder. Export your real key."; exit 1;;
  esac
fi
if [ "$1" = "--live" ]; then shift; exec python3 -m hinge_bot.bot "$@"; fi
exec python3 -m hinge_bot.bot --dry-run "$@"
