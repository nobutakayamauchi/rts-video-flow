#!/usr/bin/env bash
set -euo pipefail

PUBLIC_HOST="${1:-}"
SSH_PORT="${2:-22}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEY_FILE="${HOME}/.ssh/rts_github_actions_ed25519"
AUTHORIZED_KEYS="${HOME}/.ssh/authorized_keys"

if [[ -z "${PUBLIC_HOST}" ]]; then
  echo "Usage: bash scripts/oracle_prepare_github_actions.sh <public-host-or-ip> [ssh-port]" >&2
  exit 2
fi
if [[ ! "${SSH_PORT}" =~ ^[0-9]{1,5}$ ]]; then
  echo "[error] Invalid SSH port" >&2
  exit 2
fi

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"
touch "${AUTHORIZED_KEYS}"
chmod 600 "${AUTHORIZED_KEYS}"

if [[ ! -f "${KEY_FILE}" ]]; then
  ssh-keygen -t ed25519 -N "" -C "rts-video-flow-github-actions" -f "${KEY_FILE}"
fi
chmod 600 "${KEY_FILE}"
chmod 644 "${KEY_FILE}.pub"

PUBLIC_KEY="$(cat "${KEY_FILE}.pub")"
if ! grep -Fqx "${PUBLIC_KEY}" "${AUTHORIZED_KEYS}"; then
  printf '%s\n' "${PUBLIC_KEY}" >> "${AUTHORIZED_KEYS}"
fi

KNOWN_HOSTS="$(ssh-keyscan -p "${SSH_PORT}" -H "${PUBLIC_HOST}" 2>/dev/null)"
if [[ -z "${KNOWN_HOSTS}" ]]; then
  echo "[error] Could not obtain SSH host key for ${PUBLIC_HOST}:${SSH_PORT}" >&2
  exit 1
fi

cat <<EOF

[ok] Oracle side is ready.

Create these GitHub repository Actions secrets:

ORACLE_HOST
${PUBLIC_HOST}

ORACLE_PORT
${SSH_PORT}

ORACLE_USER
${USER}

ORACLE_REPO_DIR
${ROOT_DIR}

ORACLE_KNOWN_HOSTS
${KNOWN_HOSTS}

ORACLE_SSH_KEY
$(cat "${KEY_FILE}")

After ORACLE_SSH_KEY has been saved in GitHub, the local private-key copy may be removed with:
rm -f '${KEY_FILE}'

Do not remove '${KEY_FILE}.pub' from authorized_keys until the GitHub Actions connection is retired.
EOF
