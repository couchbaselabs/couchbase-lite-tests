#!/usr/bin/env bash
set -euo pipefail

commit_msg_file="$1"
commit_msg=$(head -1 "$commit_msg_file")

# Allow merge commits
if echo "$commit_msg" | grep -qE '^Merge '; then
  exit 0
fi

# Allow revert commits
if echo "$commit_msg" | grep -qE '^Revert '; then
  exit 0
fi

# Conventional Commits: <type>[optional scope][!]: <description>
pattern='^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-zA-Z0-9_./-]+\))?(!)?: .+'

if ! echo "$commit_msg" | grep -qE "$pattern"; then
  echo "ERROR: Commit message does not follow Conventional Commits format."
  echo ""
  echo "  Expected: <type>[optional scope]: <description>"
  echo ""
  echo "  Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert"
  echo ""
  echo "  Examples:"
  echo "    feat: add login page"
  echo "    fix(auth): resolve token expiry issue"
  echo "    docs: update README"
  echo "    feat!: breaking change to API"
  echo ""
  echo "  Your message: $commit_msg"
  exit 1
fi
