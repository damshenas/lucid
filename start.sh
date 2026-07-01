#!/bin/bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker/compose.yml}"
ACTION="${1:-}"

usage() {
    echo "Usage: $0 <action>"
    echo ""
    echo "Actions:"
    echo "  up       Start container (force-recreate)"
    echo "  down     Stop and remove container"
    echo "  build    Build image"
    echo "  recycle  git pull → build → up"
    echo ""
    echo "Environment:"
    echo "  COMPOSE_FILE  Compose file to use (default: docker/compose.yml)"
    exit 1
}

if [[ -z "$ACTION" ]]; then
    usage
fi

# Use podman-compose with the selected compose file and action
case "$ACTION" in
  up)
    podman-compose -f "$COMPOSE_FILE" up -d --force-recreate
    ;;
  down)
    podman-compose -f "$COMPOSE_FILE" down
    ;;
  build)
    podman-compose -f "$COMPOSE_FILE" --podman-build-args='--format docker' build
    ;;
  recycle)
    git pull
    podman-compose -f "$COMPOSE_FILE" --podman-build-args='--format docker' build
    podman-compose -f "$COMPOSE_FILE" up -d --force-recreate
    ;;
  *)
    echo "Error: Unknown action '$ACTION'."
    usage
    ;;
esac
