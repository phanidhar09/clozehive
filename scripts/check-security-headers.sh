#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-}"
if [[ -z "${BASE_URL}" ]]; then
  echo "Usage: $0 <base-url>"
  exit 1
fi

headers="$(curl -sSI "${BASE_URL}")"
missing=0

check_header() {
  local name="$1"
  local expected="${2:-}"
  if echo "${headers}" | grep -iq "^${name}:"; then
    local value
    value="$(echo "${headers}" | awk -v header="${name}" 'BEGIN{IGNORECASE=1} $0 ~ "^" header ":" {sub(/^[^:]+:[[:space:]]*/, ""); print; exit}' | tr -d '\r')"
    if [[ -n "${expected}" && "${value}" != *"${expected}"* ]]; then
      echo "✗ ${name}: expected ${expected}, got ${value}"
      missing=1
    else
      echo "✓ ${name}${expected:+: ${expected}}"
    fi
  else
    echo "✗ MISSING: ${name}"
    missing=1
  fi
}

check_optional_header() {
  local name="$1"
  local note="$2"
  if echo "${headers}" | grep -iq "^${name}:"; then
    echo "✓ ${name} present"
  else
    echo "✗ MISSING: ${name} (${note})"
  fi
}

check_header "X-Content-Type-Options" "nosniff"
check_header "X-Frame-Options" "DENY"
check_header "X-XSS-Protection" "1; mode=block"
check_header "Referrer-Policy" "strict-origin-when-cross-origin"
check_header "Permissions-Policy"
check_header "Content-Security-Policy"
check_optional_header "Strict-Transport-Security" "expected in production only"

exit "${missing}"
