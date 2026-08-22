#!/bin/sh
set -eu

REPOSITORY_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
PROJECT_NAME=${E2E_PROJECT_NAME:-rivexx-e2e}
COMPOSE_FILE="$REPOSITORY_ROOT/infra/compose.yaml"

export CONTROL_API_IMAGE="rivexx/control-api:e2e"
export CONTROL_PANEL_IMAGE="rivexx/control-panel:e2e"
export FAKE_WORKER_IMAGE="rivexx/fake-worker:e2e"
export E2E_IMAGE="rivexx/e2e:local"
export CONTROL_API_PORT=${E2E_CONTROL_API_PORT:-18000}
export CONTROL_PANEL_PORT=${E2E_CONTROL_PANEL_PORT:-14173}
export AGENT_NETWORK="${PROJECT_NAME}_agent_net"
export PUBLIC_BASE_URL="http://control-api:8000"
export VITE_CONTROL_API_URL="http://control-api:8000"

compose() {
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" "$@"
}

cleanup() {
  compose --profile manual --profile e2e down --volumes --remove-orphans >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM
cleanup

compose --profile manual --profile e2e build control-api control-panel fake-worker e2e
compose up -d --wait postgres control-api control-panel

docker run --rm \
  --network "$AGENT_NETWORK" \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 64 \
  --memory 128m \
  --cpus 0.5 \
  --user 10001:10001 \
  --entrypoint python \
  -e RUN_ID=11111111-1111-4111-8111-111111111111 \
  -e TASK_ID=22222222-2222-4222-8222-222222222222 \
  -e CONTROL_API_URL=http://control-api:8000 \
  -e TASK_TOKEN=e2e-isolation-probe \
  -v "$REPOSITORY_ROOT/tests/e2e/isolation_probe.py:/probe/isolation_probe.py:ro" \
  "$FAKE_WORKER_IMAGE" /probe/isolation_probe.py

compose --profile e2e run --rm e2e
