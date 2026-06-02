#!/usr/bin/env bash
# Runs on the OCI server. Idempotent. Append-only — touches only `quali-fit` namespace
# and copies the existing wildcard TLS secret in.
set -euo pipefail

cd "$(dirname "$0")/.."

# Tag is the git commit SHA in CI (passed via IMAGE_TAG); falls back to `dev`
# for manual/local runs. A changing tag is what guarantees the rollout below
# actually picks up new code (a fixed tag + IfNotPresent would silently reuse
# the cached image).
IMAGE_TAG="${IMAGE_TAG:-dev}"
IMAGE="quali-fit:${IMAGE_TAG}"

# 1) Build the image locally on the server (ARM64).
sudo docker build -t "$IMAGE" .

# 2) Import into k3s's containerd so the kubelet can find it without a registry.
sudo docker save "$IMAGE" | sudo k3s ctr images import -

# 3) Create namespace + manifests (everything in `quali-fit`).
sudo kubectl apply -f k8s/00-namespace.yaml

# 4) Replicate the existing wildcard *.bit-habit.com TLS secret from `default`
#    into `quali-fit` (cert-manager continues to renew the source).
sudo kubectl get secret tls-secret -n default -o yaml \
  | sed -e 's/namespace: default/namespace: quali-fit/' \
        -e '/uid:/d' -e '/resourceVersion:/d' -e '/creationTimestamp:/d' \
        -e '/ownerReferences:/,/^  [^ ]/{ /^  [^ ]/!d }' \
        -e '/managedFields:/,/^[^ ]/{ /^[^ ]/!d }' \
  | sudo kubectl apply -f -

# 5) Apply app resources (PVC, Deployment, Service, Middleware, Secret, Ingress).
#    The Deployment carries an `__IMAGE_TAG__` token — render it to the real
#    per-commit tag on the fly (via stdin, no file mutation) so the rollout is a
#    single apply with the correct image. A changing tag is what guarantees the
#    rollout actually picks up new code.
for f in k8s/*.yaml; do
  case "$f" in
    */20-deployment.yaml)
      sed "s|__IMAGE_TAG__|${IMAGE_TAG}|g" "$f" | sudo kubectl apply -f - ;;
    *)
      sudo kubectl apply -f "$f" ;;
  esac
done

# 6) Wait for the pod to be ready (init_db runs at startup, schema only — no data).
sudo kubectl -n quali-fit rollout status deployment/quali-fit --timeout=180s

echo
echo "Pod is up with empty schema. Now load the real data:"
echo "  ./scripts/copy-db.sh"
