#!/usr/bin/env bash
# One-time host preparation for rootless Podman on SELinux hosts.
# Creates the data directory, chowns it to the container's subuid mapping
# (100000 + 8686 - 1 = 108685), and applies the container SELinux label.
#
# Usage: sudo bash docker/prepare.sh [BASE_DIR]
set -euo pipefail

BASE_DIR="${1:-/container/lucid}"
SUBUID=108685  # 100000 + 8686 - 1

echo "Preparing ${BASE_DIR} ..."
mkdir -p "${BASE_DIR}/data"
chown -R "${SUBUID}:${SUBUID}" "${BASE_DIR}"

if command -v chcon >/dev/null 2>&1; then
    echo "Applying SELinux container_file_t label ..."
    chcon -Rt container_file_t "${BASE_DIR}" || true
fi

echo "Done. Mount ${BASE_DIR}/data at /data."
