
set -euo pipefail

export LC_ALL=C

branch=$(git rev-parse --abbrev-ref HEAD)

pattern='^(main|develop)$|^(feature|fix|hotfix|docs|refactor|chore|test|ci|cd|release|bump)/(pd-[1-9][0-9]*(-[a-z0-9-]+)?|pd-0+-[a-z0-9-]+)$'

if [[ "$branch" =~ $pattern ]]; then
  echo "OK: $branch"
  exit 0
fi

cat <<EOF >&2
FAIL: branch '$branch' does not follow the unified naming convention.

Required format:
  <type>/pd-<N>[-<slug>]

Examples (accepted):
  feature/pd-142
  fix/pd-89-race-condition
  chore/pd-00-cleanup-imports
  main
  develop

Rejected:
  feat/foo                 (old short prefix — use 'feature/')
  feature/foo              (missing pd-<N>)
  feature/pd-              (missing number)
  feature/PD-142           (uppercase)
  feature/pd-00            (pd-00 without slug — always add a slug for non-business work)
  random-branch            (missing type prefix)

Allowed types:
  feature, fix, hotfix, docs, refactor, chore, test, ci, cd, release, bump

pd-<N> conventions:
  pd-<positive integer>  = Jira ticket PD-<N>
  pd-00-<slug>           = non-business / technical / tooling work (slug required)
EOF
exit 1
