#!/bin/zsh
# Double-click to start Hookscope. Close this window (or press Ctrl+C) to stop it.
cd "${0:A:h}" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
if [ ! -x .venv/bin/python ]; then
  echo "Setting up Hookscope for the first time (one minute)..."
  uv sync || { echo "Setup failed. Is uv installed? (brew install uv)"; read -k1; exit 1; }
fi
exec .venv/bin/python -m hookscope
