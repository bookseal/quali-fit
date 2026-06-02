#!/usr/bin/env bash
# Generates k8s/secret-basicauth.yaml (gitignored).
# Default user/password are the demo values; override via env if needed.
set -euo pipefail

USER="${BASIC_AUTH_USER:-kiba}"
PASS="${BASIC_AUTH_PASS:-kiba1234}"

cd "$(dirname "$0")/.."

# bcrypt; Traefik basic-auth Secret expects htpasswd-format content in the `users` key.
HTPASSWD_LINE="$(htpasswd -nbB "$USER" "$PASS")"

cat > k8s/secret-basicauth.yaml <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: quali-fit-basicauth
  namespace: quali-fit
type: Opaque
stringData:
  users: |
    ${HTPASSWD_LINE}
EOF

echo "Wrote k8s/secret-basicauth.yaml (user=${USER})"
