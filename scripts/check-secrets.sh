#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-$(pwd)}"

PATTERNS=(
  '(?i)(api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|refresh[_-]?token|password|secret|cookie)\s*[:=]\s*[A-Za-z0-9._/\-+=]{8,}'
  '(?i)Bearer\s+[A-Za-z0-9._\-]{20,}'
  '-----BEGIN[[:space:]]+PRIVATE[[:space:]]+KEY-----'
  '(?i)gh[pousr]_[A-Za-z0-9]{20,}'
  '(?i)xox[baprs]-[A-Za-z0-9-]{10,}'
)

echo "Scanning: ${ROOT_DIR}"

matches=0
for pattern in "${PATTERNS[@]}"; do
  while IFS= read -r hit; do
    [[ -n "$hit" ]] || continue
    echo "$hit"
    matches=1
  done < <(
    rg -n -P --hidden --glob '!**/.git/**' --glob '!**/node_modules/**' \
      --glob '!**/dist/**' --glob '!**/build/**' --glob '!scripts/check-secrets.sh' \
      -- "$pattern" "$ROOT_DIR" || true
  )
done

if [[ "$matches" -eq 1 ]]; then
  echo
  echo "Potential sensitive strings found."
  echo "Review the matches above and redact any real secrets before sharing."
  exit 1
fi

echo "No obvious secret patterns found."
