#!/usr/bin/env bash
set -euo pipefail

branch=$(git rev-parse --abbrev-ref HEAD)
pattern="^(main|develop|feature|fix|hotfix|docs|refactor|chore|test|ci|cd|release|bump)/.+|^(main|develop)$"

if ! [[ "$branch" =~ $pattern ]]; then
  echo "❌ Invalid branch: $branch"
  echo "Use: feature/x, fix/x, hotfix/x, docs/x, cd/x, ci/x, release/x, bump/x, etc."
  exit 1
fi

echo "✓ $branch"
