#!/usr/bin/env bash
# One-time (and re-run-safe) host preparation for rootless Podman on SELinux hosts.
# Creates the data directory, chowns it (recursively) to the container's subuid
# mapping (100000 + 8686 - 1 = 108685), and applies the container SELinux label.
#
# Re-run this any time after (re-)cloning/updating the EXT_STRATEGIES checkout
# out-of-band (e.g. `git clone ... ${BASE_DIR}/ext-strategies` as your own host
# user) — otherwise its files (owned by that host user, not the subuid mapping)
# cause "Permission denied" writing .git/FETCH_HEAD when the app runs `git pull`.
#
# Usage: sudo bash docker/prepare.sh [BASE_DIR]
set -euo pipefail

BASE_DIR="${1:-/container/lucid}"
SUBUID=108685  # 100000 + 8686 - 1

echo "Preparing ${BASE_DIR} ..."
mkdir -p "${BASE_DIR}/data" "${BASE_DIR}/ext-strategies"
chown -R "${SUBUID}:${SUBUID}" "${BASE_DIR}"

if command -v chcon >/dev/null 2>&1; then
    echo "Applying SELinux container_file_t label ..."
    chcon -Rt container_file_t "${BASE_DIR}" || true
fi

echo "Done. Mount ${BASE_DIR}/data at /data, ${BASE_DIR}/ext-strategies at /ext_strategies."
echo "(STRATEGIES_ROOT itself is a tmpfs path — no host directory needed for it.)"
