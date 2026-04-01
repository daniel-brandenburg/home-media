#!/usr/bin/env bash
set -euo pipefail

require() {
  command -v "$1" &>/dev/null || { echo "Error: missing required tool: $1"; exit 1; }
}
require rsync
require envsubst

# Parse flags
FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

RSYNC_OPTS="-avz"
if [[ "$FORCE" -eq 1 ]]; then
  RSYNC_OPTS="${RSYNC_OPTS} --ignore-times"
  echo "Force mode: all files will be re-transferred regardless of timestamp."
fi

# Load configuration from .env (must live alongside this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: ${ENV_FILE} not found."
  echo "Copy .env.example to .env and fill in your values first."
  exit 1
fi
# shellcheck source=.env.example
set -a
source "$ENV_FILE"
set +a

echo "Deploying to ${REMOTE}:${REMOTE_DIR} ..."

# 1. Sync files to their specific service directories
# 2. Removed --relative to maintain control over the destination paths
# shellcheck disable=SC2086
rsync $RSYNC_OPTS caddy/Caddyfile "${REMOTE}:${REMOTE_DIR}/caddy/Caddyfile"

# conf.yml uses ${SERVER_IP} placeholders — expand them before deploying
envsubst '${SERVER_IP}' < dashy/conf.yml | \
  ssh "$REMOTE" "cat > ${REMOTE_DIR}/dashy/conf.yml"

# shellcheck disable=SC2086
rsync $RSYNC_OPTS compose.yaml "${REMOTE}:${REMOTE_DIR}/compose.yaml"

# Deploy .env so Podman Compose can resolve ${PUID}, ${PGID}, ${TZ}, etc. at runtime
# shellcheck disable=SC2086
rsync $RSYNC_OPTS .env "${REMOTE}:${REMOTE_DIR}/.env"

# 3. Specifically fix the qBittorrent init script path
# This matches the volume mapping in your compose.yaml
# shellcheck disable=SC2086
rsync $RSYNC_OPTS qbittorrent/custom-cont-init.d/ "${REMOTE}:${REMOTE_DIR}/qbittorrent/custom-cont-init.d/"
# shellcheck disable=SC2086
rsync $RSYNC_OPTS setup-firewall.sh "${REMOTE}:${REMOTE_DIR}/setup-firewall.sh"

echo "Done. To start the stack on the server, run:"
echo "  ssh ${REMOTE} 'podman compose -f ${REMOTE_DIR}/compose.yaml up -d'"
