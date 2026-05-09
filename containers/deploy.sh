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
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
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

# conf.yml uses ${SERVER_IP} placeholders — expand them before deploying
envsubst '${SERVER_IP}' < dashy/conf.yml | \
  ssh "$REMOTE" "cat > ${REMOTE_DIR}/dashy/conf.yml"

# 2. Deploy .env so quadlet EnvironmentFile= can resolve PUID, PGID, TZ, etc. at runtime
# shellcheck disable=SC2086
rsync $RSYNC_OPTS .env "${REMOTE}:${REMOTE_DIR}/.env"

# 4. Sync firewall setup script
# shellcheck disable=SC2086
rsync $RSYNC_OPTS setup-firewall.sh "${REMOTE}:${REMOTE_DIR}/setup-firewall.sh"

# 5. Sync quadlet unit files to /etc/containers/systemd/ on the server
#    Quadlets placed here are auto-discovered by systemd-generator on next daemon-reload.
#    Requires sudo on the remote side — ensure NOPASSWD sudo for rsync is configured,
#    or that your user has sudo rights.
# shellcheck disable=SC2086
rsync $RSYNC_OPTS --rsync-path="sudo rsync" "${REPO_DIR}/quadlets/" "${REMOTE}:/etc/containers/systemd/"

# 6. Sync the home-media.target grouping unit
# shellcheck disable=SC2086
rsync $RSYNC_OPTS --rsync-path="sudo rsync" "${REPO_DIR}/systemd/home-media.target" "${REMOTE}:/etc/systemd/system/home-media.target"

# 3. Sync qBittorrent init script
# shellcheck disable=SC2086
echo "QBittirrent copy disabled, edit this file to enable"
# Uncomment the following line to copy qbit config
# rsync $RSYNC_OPTS qbittorrent/custom-cont-init.d/ "${REMOTE}:${REMOTE_DIR}/qbittorrent/custom-cont-init.d/"

echo ""
echo "Done. To activate the quadlets on the server, run:"
echo "  ssh ${REMOTE} 'systemctl daemon-reload'"
echo ""
echo "Then start the stack:"
echo "  ssh ${REMOTE} 'systemctl start caddy.service'"
echo ""
echo "Or enable all containers to start at boot (they already have WantedBy=default.target):"
echo "  ssh ${REMOTE} 'systemctl enable --now caddy.service jellyfin.service sonarr.service radarr.service prowlarr.service audiobookshelf.service qbittorrent.service bitmagnet.service dashy.service calibre-web-automated.service shelfmark.service'"
