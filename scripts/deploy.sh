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

# Build stamp shown in the app's sidebar footer — confirms a deploy actually
# shipped and which build is live. Version comes from the VERSION file (rsynced
# in); the commit tag and build time change every deploy.
APP_VERSION="$(cat VERSION 2>/dev/null || echo dev)"
BUILD_TIME="$(date -u +'%Y-%m-%d %H:%M UTC')"

# 1) Build the image locally on the server (ARM64).
sudo docker build \
  --build-arg APP_VERSION="$APP_VERSION" \
  --build-arg GIT_SHA="$IMAGE_TAG" \
  --build-arg BUILD_TIME="$BUILD_TIME" \
  -t "$IMAGE" .

# 2) Import into k3s's containerd so the kubelet can find it without a registry,
#    then drop the docker-side copy. The pod runs from containerd, so keeping the
#    image in docker too just doubles disk use every deploy — that unbounded
#    growth is what tripped the node's disk-pressure eviction and blocked a
#    rollout. Removing it here keeps docker's store flat across deploys.
sudo docker save "$IMAGE" | sudo k3s ctr images import -
sudo docker image rm "$IMAGE" >/dev/null 2>&1 || true
sudo docker builder prune -f >/dev/null 2>&1 || true

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

# 7) Now that the new pod is live, drop superseded quali-fit images from
#    containerd (the old pod no longer needs them). Done last, never before the
#    rollout, so we don't pull the image out from under the running pod.
sudo k3s ctr images ls -q 2>/dev/null \
  | grep '/quali-fit:' | grep -v ":${IMAGE_TAG}$" \
  | xargs -r sudo k3s ctr images rm >/dev/null 2>&1 || true

echo
echo "Pod is up. Data persists on the PVC (init_db is schema-only). First-time"
echo "setup only — load the real data with:  ./scripts/copy-db.sh"
