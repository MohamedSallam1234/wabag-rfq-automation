#!/usr/bin/env bash
set -euo pipefail

branch=$(git rev-parse --abbrev-ref HEAD)
pattern="^(main|develop|feature|fix|hotfix|docs|refactor|chore|test|ci|release|bump)\/.+$|^(main|develop)$"

if ! echo "$branch" | grep -qE "$pattern"; then
  echo "ERROR: Branch name \"$branch\" does not follow the convention."
  echo ""
  echo "Allowed patterns:"
  echo "  feature/<description>    - new functionality"
  echo "  fix/<description>        - bug fixes"
  echo "  hotfix/<description>     - urgent production fixes"
  echo "  docs/<description>       - documentation changes"
  echo "  refactor/<description>   - code restructuring"
  echo "  chore/<description>      - maintenance tasks"
  echo "  test/<description>       - test additions/changes"
  echo "  ci/<description>         - CI/CD pipeline changes"
  echo "  release/<description>    - release preparation"
  echo "  bump/<description>       - version bumps"
  echo "  main, develop            - protected branches"
  exit 1
fi

echo "Branch name OK: $branch"
