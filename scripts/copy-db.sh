#!/usr/bin/env bash
# Copies the locally-seeded app.db (with your edits) into the running pod's PVC,
# then restarts the deployment so Streamlit re-opens the file cleanly.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f app.db ]; then
  echo "app.db not found in repo root" >&2
  exit 1
fi

POD="$(sudo kubectl -n quali-fit get pod -l app=quali-fit -o jsonpath='{.items[0].metadata.name}')"
echo "Copying app.db into pod $POD ..."
sudo kubectl -n quali-fit cp app.db "$POD:/data/app.db"

sudo kubectl -n quali-fit rollout restart deployment/quali-fit
sudo kubectl -n quali-fit rollout status deployment/quali-fit --timeout=60s
echo "Done."
