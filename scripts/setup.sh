#!/usr/bin/env bash
set -euo pipefail

echo "🚀 RFQ Auto Setup"

# UV
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Backend
cd backend
uv sync
[ -f .env ] || cp .env.example .env

# Hooks
cd ..
pip install pre-commit -q
pre-commit install --install-hooks

echo "✅ Ready"
echo ""
echo "Workflow:"
echo "  git checkout -b feature/thing"
echo "  make dev     # start server"
echo "  make test    # run tests"
echo "  git push     # CI handles the rest"
