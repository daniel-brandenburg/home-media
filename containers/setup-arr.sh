#!/usr/bin/env bash
# setup-arr.sh
# Configures qBittorrent, Sonarr, and Radarr to work together.
# Run this once after the stack is up for the first time.
# Safe to re-run — most API calls are idempotent.
set -euo pipefail

# Load configuration from .env (must live alongside this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: ${ENV_FILE} not found."
  echo "Copy .env.example to .env and fill in your values first."
  exit 1
fi
# shellcheck source=.env.example
source "$ENV_FILE"

# ─── Derived service URLs ──────────────────────────────────────────────────
QBIT_URL="http://${SERVER_IP}:8080"
SONARR_URL="http://${SERVER_IP}:8989"
RADARR_URL="http://${SERVER_IP}:7878"
PROWLARR_URL="http://${SERVER_IP}:9696"
LISTENARR_URL="http://${SERVER_IP}:4545"

# ─── Helpers ───────────────────────────────────────────────────────────────
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
blue()  { printf '\033[34m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }
step()  { echo; blue "==> $*"; }

require() {
  command -v "$1" &>/dev/null || { red "Missing required tool: $1"; exit 1; }
}
require curl
require ssh
require jq

# ─── API key auto-fetch ────────────────────────────────────────────────────
# If an API key is missing from .env, try to read it from the app's config
# file on the server. Sonarr/Radarr/Prowlarr store the key in config.xml;
# Listenarr stores it in appsettings/appsettings.json.
# The variable name, container config path, and grep command are passed in.
fetch_api_key_xml() {
  local var_name="$1" config_path="$2"
  local key
  key=$(ssh "$REMOTE" "grep -oP '(?<=<ApiKey>)[^<]+' '${config_path}' 2>/dev/null" || true)
  if [[ -n "$key" ]]; then
    green "  Auto-fetched ${var_name} from server: ${key}"
    printf '%s="%s"\n' "$var_name" "$key" >> "$ENV_FILE"
    eval "${var_name}=${key}"
  else
    yellow "  ${var_name} is empty and could not be read from ${config_path}."
    yellow "  Make sure the stack is running, then run:"
    yellow "    ssh ${REMOTE} \"grep -oP '(?<=<ApiKey>)[^<]+' ${config_path}\""
    yellow "  Then set ${var_name} in your .env and re-run this script."
  fi
}

fetch_api_key_json() {
  local var_name="$1" config_path="$2"
  local key
  key=$(ssh "$REMOTE" "jq -r '.ApiKey // empty' '${config_path}' 2>/dev/null" || true)
  if [[ -n "$key" ]]; then
    green "  Auto-fetched ${var_name} from server: ${key}"
    printf '%s="%s"\n' "$var_name" "$key" >> "$ENV_FILE"
    eval "${var_name}=${key}"
  else
    yellow "  ${var_name} is empty and could not be read from ${config_path}."
    yellow "  Make sure the stack is running, then run:"
    yellow "    ssh ${REMOTE} \"jq -r '.ApiKey' ${config_path}\""
    yellow "  Then set ${var_name} in your .env and re-run this script."
  fi
}

REMOTE_DIR="${REMOTE_DIR:-/srv/containers}"
KEYS_MISSING=0

step "Checking API keys"
[[ -n "$SONARR_API" ]]   || { fetch_api_key_xml  SONARR_API   "${REMOTE_DIR}/sonarr/config.xml";   [[ -n "$SONARR_API" ]]   || KEYS_MISSING=1; }
[[ -n "$RADARR_API" ]]   || { fetch_api_key_xml  RADARR_API   "${REMOTE_DIR}/radarr/config.xml";   [[ -n "$RADARR_API" ]]   || KEYS_MISSING=1; }
[[ -n "$PROWLARR_API" ]] || { fetch_api_key_xml  PROWLARR_API "${REMOTE_DIR}/prowlarr/config.xml"; [[ -n "$PROWLARR_API" ]] || KEYS_MISSING=1; }
[[ -n "$LISTENARR_API" ]] || { fetch_api_key_json LISTENARR_API "${REMOTE_DIR}/listenarr/appsettings/appsettings.json"; [[ -n "$LISTENARR_API" ]] || KEYS_MISSING=1; }

if [[ "$KEYS_MISSING" -eq 1 ]]; then
  red "One or more API keys could not be resolved. Fill them in .env and re-run."
  exit 1
fi
green "  All API keys present"

QBIT_COOKIE=$(mktemp)
trap 'rm -f "$QBIT_COOKIE"' EXIT

# ─── qBittorrent ───────────────────────────────────────────────────────────
step "qBittorrent: logging in"

qbit_login() {
  local pass="$1"
  local body
  body=$(curl -s -c "$QBIT_COOKIE" -o /tmp/qbit_login_body \
      -H "Referer: ${QBIT_URL}" \
      --data "username=${QBIT_USER}&password=${pass}" \
      "${QBIT_URL}/api/v2/auth/login" && cat /tmp/qbit_login_body)
    [[ "$body" == *"Ok."* ]] # Changed to wildcard match for safety]
}

step "qBittorrent: setting default save path and preferences"
curl -s -b "$QBIT_COOKIE" -c "$QBIT_COOKIE" \
  -H "Referer: ${QBIT_URL}" \
  --data-urlencode 'json={"save_path":"/downloads","temp_path_enabled":true,"temp_path":"/downloads/incomplete"}' \
  "${QBIT_URL}/api/v2/app/setPreferences" > /dev/null

if qbit_login "$QBIT_PASS"; then
  green "  Logged in with password: ${QBIT_PASS}"
else
  # New qBittorrent versions generate a random temp password each session
  # when no persistent password is configured — grab it from the container logs
  echo "  Trying temp password from container logs..."
  TEMP_PASS=$(ssh "$REMOTE" 'podman logs qbittorrent 2>&1' | \
    grep -oP 'A temporary password is provided for this session: \K\S+' | tail -1)
  if [[ -z "$TEMP_PASS" ]]; then
    red "Could not determine qBittorrent password. Check QBIT_PASS at top of script."
    exit 1
  fi
  echo "  Found temp password: ${TEMP_PASS}"
  if ! qbit_login "$TEMP_PASS"; then
    red "Login with temp password failed too. The IP may be banned — restart qbittorrent container and try again."
    exit 1
  fi
  green "  Logged in with temp password"
  # Set a permanent password immediately
  curl -s -b "$QBIT_COOKIE" -c "$QBIT_COOKIE" \
    --data-urlencode "json={\"web_ui_password\":\"${QBIT_PASS}\"}" \
    "${QBIT_URL}/api/v2/app/setPreferences" > /dev/null
  green "  Permanent password set to: ${QBIT_PASS}"
fi

step "qBittorrent: setting default save path and preferences"
curl -s -b "$QBIT_COOKIE" -c "$QBIT_COOKIE" \
  --data-urlencode 'json={"save_path":"/downloads","temp_path_enabled":true,"temp_path":"/downloads/incomplete"}' \
  "${QBIT_URL}/api/v2/app/setPreferences" > /dev/null
green "  save_path=/downloads"

step "qBittorrent: creating category 'tv'"
curl -s -b "$QBIT_COOKIE" -c "$QBIT_COOKIE" \
  --data-urlencode "category=tv" \
  --data-urlencode "savePath=/downloads/tv" \
  "${QBIT_URL}/api/v2/torrents/createCategory" > /dev/null
# Also try editCategory in case it already exists
curl -s -b "$QBIT_COOKIE" -c "$QBIT_COOKIE" \
  --data-urlencode "category=tv" \
  --data-urlencode "savePath=/downloads/tv" \
  "${QBIT_URL}/api/v2/torrents/editCategory" > /dev/null
green "  Category 'tv' -> /downloads/tv"

step "qBittorrent: creating category 'movies'"
curl -s -b "$QBIT_COOKIE" -c "$QBIT_COOKIE" \
  --data-urlencode "category=movies" \
  --data-urlencode "savePath=/downloads/movies" \
  "${QBIT_URL}/api/v2/torrents/createCategory" > /dev/null
curl -s -b "$QBIT_COOKIE" -c "$QBIT_COOKIE" \
  --data-urlencode "category=movies" \
  --data-urlencode "savePath=/downloads/movies" \
  "${QBIT_URL}/api/v2/torrents/editCategory" > /dev/null
green "  Category 'movies' -> /downloads/movies"

step "qBittorrent: creating category 'audiobooks'"
curl -s -b "$QBIT_COOKIE" -c "$QBIT_COOKIE" \
  --data-urlencode "category=audiobooks" \
  --data-urlencode "savePath=/downloads/audiobooks" \
  "${QBIT_URL}/api/v2/torrents/createCategory" > /dev/null
curl -s -b "$QBIT_COOKIE" -c "$QBIT_COOKIE" \
  --data-urlencode "category=audiobooks" \
  --data-urlencode "savePath=/downloads/audiobooks" \
  "${QBIT_URL}/api/v2/torrents/editCategory" > /dev/null
green "  Category 'audiobooks' -> /downloads/audiobooks"

# ─── Sonarr ────────────────────────────────────────────────────────────────
sonarr() {
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -sf -X "$method" \
      -H "X-Api-Key: ${SONARR_API}" \
      -H "Content-Type: application/json" \
      -d "$body" \
      "${SONARR_URL}/api/v3/${path}"
  else
    curl -sf -X "$method" \
      -H "X-Api-Key: ${SONARR_API}" \
      "${SONARR_URL}/api/v3/${path}"
  fi
}

step "Sonarr: checking connectivity"
sonarr GET "system/status" | jq -r '"  Version: " + .version'

step "Sonarr: configuring media management (hardlinks + rename)"
sonarr PUT "config/mediamanagement" "$(sonarr GET config/mediamanagement | jq '
  .copyUsingHardlinks = true |
  .importExtraFiles = false |
  .renameSeries = true |
  .replaceIllegalCharacters = true |
  .deleteEmptyFolders = true
')" | jq -r '"  hardLinks: \(.copyUsingHardlinks), rename: \(.renameSeries)"'

step "Sonarr: adding root folder /data/TV"
EXISTING_ROOTS=$(sonarr GET "rootfolder")
if echo "$EXISTING_ROOTS" | jq -e '.[] | select(.path == "/data/TV")' &>/dev/null; then
  green "  Root folder /data/TV already exists"
else
  sonarr POST "rootfolder" '{"path":"/data/TV"}' | jq -r '"  Added root folder: " + .path'
fi

step "Sonarr: adding remote path mapping (qBittorrent /downloads -> /data/downloads)"
EXISTING_RPM=$(sonarr GET "remotepathmapping")
if echo "$EXISTING_RPM" | jq -e '.[] | select(.host == "qbittorrent")' &>/dev/null; then
  green "  Remote path mapping already exists"
else
  sonarr POST "remotepathmapping" '{"host":"qbittorrent","remotePath":"/downloads/","localPath":"/data/downloads/"}' \
    | jq -r '"  Mapped: " + .remotePath + " -> " + .localPath'
fi

step "Sonarr: adding qBittorrent as download client"
EXISTING_DC=$(sonarr GET "downloadclient")
if echo "$EXISTING_DC" | jq -e '.[] | select(.name == "qBittorrent")' &>/dev/null; then
  green "  Download client qBittorrent already exists"
else
  RESULT=$(sonarr POST "downloadclient" "{
    \"name\": \"qBittorrent\",
    \"enable\": true,
    \"protocol\": \"torrent\",
    \"priority\": 1,
    \"implementation\": \"QBittorrent\",
    \"configContract\": \"QBittorrentSettings\",
    \"fields\": [
      {\"name\": \"host\",     \"value\": \"qbittorrent\"},
      {\"name\": \"port\",     \"value\": 8080},
      {\"name\": \"username\", \"value\": \"${QBIT_USER}\"},
      {\"name\": \"password\", \"value\": \"${QBIT_PASS}\"},
      {\"name\": \"tvCategory\",        \"value\": \"tv\"},
      {\"name\": \"recentTvPriority\",  \"value\": 0},
      {\"name\": \"olderTvPriority\",   \"value\": 0},
      {\"name\": \"initialState\",      \"value\": 0},
      {\"name\": \"sequentialOrder\",   \"value\": false},
      {\"name\": \"firstAndLast\",      \"value\": false}
    ]
  }")
  if echo "$RESULT" | jq -e '.id' &>/dev/null; then
    echo "$RESULT" | jq -r '"  Added download client: " + .name'
  else
    red "  Failed to add Sonarr download client:"
    echo "$RESULT" | jq -r '.[] | "  [" + .severity + "] " + .errorMessage' 2>/dev/null || echo "$RESULT"
    exit 1
  fi
fi

# ─── Radarr ────────────────────────────────────────────────────────────────
radarr() {
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -sf -X "$method" \
      -H "X-Api-Key: ${RADARR_API}" \
      -H "Content-Type: application/json" \
      -d "$body" \
      "${RADARR_URL}/api/v3/${path}"
  else
    curl -sf -X "$method" \
      -H "X-Api-Key: ${RADARR_API}" \
      "${RADARR_URL}/api/v3/${path}"
  fi
}

step "Radarr: checking connectivity"
radarr GET "system/status" | jq -r '"  Version: " + .version'

step "Radarr: configuring media management (hardlinks + rename)"
radarr PUT "config/mediamanagement" "$(radarr GET config/mediamanagement | jq '
  .copyUsingHardlinks = true |
  .importExtraFiles = false |
  .renameMovies = true |
  .replaceIllegalCharacters = true |
  .deleteEmptyFolders = true
')" | jq -r '"  hardLinks: \(.copyUsingHardlinks), rename: \(.renameMovies)"'

step "Radarr: adding root folder /data/Movies"
EXISTING_ROOTS=$(radarr GET "rootfolder")
if echo "$EXISTING_ROOTS" | jq -e '.[] | select(.path == "/data/Movies")' &>/dev/null; then
  green "  Root folder /data/Movies already exists"
else
  radarr POST "rootfolder" '{"path":"/data/Movies"}' | jq -r '"  Added root folder: " + .path'
fi

step "Radarr: adding remote path mapping (qBittorrent /downloads -> /data/downloads)"
EXISTING_RPM=$(radarr GET "remotepathmapping")
if echo "$EXISTING_RPM" | jq -e '.[] | select(.host == "qbittorrent")' &>/dev/null; then
  green "  Remote path mapping already exists"
else
  radarr POST "remotepathmapping" '{"host":"qbittorrent","remotePath":"/downloads/","localPath":"/data/downloads/"}' \
    | jq -r '"  Mapped: " + .remotePath + " -> " + .localPath'
fi

step "Radarr: adding qBittorrent as download client"
EXISTING_DC=$(radarr GET "downloadclient")
if echo "$EXISTING_DC" | jq -e '.[] | select(.name == "qBittorrent")' &>/dev/null; then
  green "  Download client qBittorrent already exists"
else
  RESULT=$(radarr POST "downloadclient" "{
    \"name\": \"qBittorrent\",
    \"enable\": true,
    \"protocol\": \"torrent\",
    \"priority\": 1,
    \"implementation\": \"QBittorrent\",
    \"configContract\": \"QBittorrentSettings\",
    \"fields\": [
      {\"name\": \"host\",     \"value\": \"qbittorrent\"},
      {\"name\": \"port\",     \"value\": 8080},
      {\"name\": \"username\", \"value\": \"${QBIT_USER}\"},
      {\"name\": \"password\", \"value\": \"${QBIT_PASS}\"},
      {\"name\": \"movieCategory\",       \"value\": \"movies\"},
      {\"name\": \"recentMoviePriority\", \"value\": 0},
      {\"name\": \"olderMoviePriority\",  \"value\": 0},
      {\"name\": \"initialState\",        \"value\": 0},
      {\"name\": \"sequentialOrder\",     \"value\": false},
      {\"name\": \"firstAndLast\",        \"value\": false}
    ]
  }")
  if echo "$RESULT" | jq -e '.id' &>/dev/null; then
    echo "$RESULT" | jq -r '"  Added download client: " + .name'
  else
    red "  Failed to add Radarr download client:"
    echo "$RESULT" | jq -r '.[] | "  [" + .severity + "] " + .errorMessage' 2>/dev/null || echo "$RESULT"
    exit 1
  fi
fi

# ─── Prowlarr ──────────────────────────────────────────────────────────────
# Prowlarr's port (9696) may be firewalled on the server.
# We run these API calls via SSH to avoid the firewall entirely.
prowlarr_ssh() {
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    # Use printf %q to safely escape the body for the remote shell
    ssh "$REMOTE" "curl -sf -X '${method}' \
      -H 'X-Api-Key: ${PROWLARR_API}' \
      -H 'Content-Type: application/json' \
      -d $(printf %q "$body") \
      http://localhost:9696/api/v1/${path}"
  else
    ssh "$REMOTE" "curl -sf -X '${method}' \
      -H 'X-Api-Key: ${PROWLARR_API}' \
      http://localhost:9696/api/v1/${path}"
  fi
}

step "Prowlarr: checking connectivity"
prowlarr_ssh GET "system/status" | jq -r '"  Version: " + .version'

step "Prowlarr: registering Sonarr as an application"
EXISTING_APPS=$(prowlarr_ssh GET "applications")
if echo "$EXISTING_APPS" | jq -e '.[] | select(.name == "Sonarr")' &>/dev/null; then
  green "  Sonarr already registered"
else
  RESULT=$(prowlarr_ssh POST "applications" \
    "{\"name\":\"Sonarr\",\"syncLevel\":\"fullSync\",\"implementation\":\"Sonarr\",\"configContract\":\"SonarrSettings\",\"fields\":[{\"name\":\"prowlarrUrl\",\"value\":\"http://prowlarr:9696\"},{\"name\":\"baseUrl\",\"value\":\"http://sonarr:8989\"},{\"name\":\"apiKey\",\"value\":\"${SONARR_API}\"},{\"name\":\"syncCategories\",\"value\":[5000,5010,5020,5030,5040,5045,5050,5090]}]}")
  if echo "$RESULT" | jq -e '.id' &>/dev/null; then
    echo "$RESULT" | jq -r '"  Registered: " + .name + " (id: \(.id))"'
  else
    red "  Failed to register Sonarr in Prowlarr:"
    echo "$RESULT"
    exit 1
  fi
fi

step "Prowlarr: registering Radarr as an application"
EXISTING_APPS=$(prowlarr_ssh GET "applications")
if echo "$EXISTING_APPS" | jq -e '.[] | select(.name == "Radarr")' &>/dev/null; then
  green "  Radarr already registered"
else
  RESULT=$(prowlarr_ssh POST "applications" \
    "{\"name\":\"Radarr\",\"syncLevel\":\"fullSync\",\"implementation\":\"Radarr\",\"configContract\":\"RadarrSettings\",\"fields\":[{\"name\":\"prowlarrUrl\",\"value\":\"http://prowlarr:9696\"},{\"name\":\"baseUrl\",\"value\":\"http://radarr:7878\"},{\"name\":\"apiKey\",\"value\":\"${RADARR_API}\"},{\"name\":\"syncCategories\",\"value\":[2000,2010,2020,2030,2040,2045,2050,2060,2070,2080,2090]}]}")
  if echo "$RESULT" | jq -e '.id' &>/dev/null; then
    echo "$RESULT" | jq -r '"  Registered: " + .name + " (id: \(.id))"'
  else
    red "  Failed to register Radarr in Prowlarr:"
    echo "$RESULT"
    exit 1
  fi
fi

# ─── FlareSolverr → Prowlarr ───────────────────────────────────────────────
step "Prowlarr: registering FlareSolverr as an indexer proxy"
EXISTING_PROXIES=$(prowlarr_ssh GET "indexerproxy")
if echo "$EXISTING_PROXIES" | jq -e '.[] | select(.name == "FlareSolverr")' &>/dev/null; then
  green "  FlareSolverr proxy already registered"
else
  RESULT=$(prowlarr_ssh POST "indexerproxy" \
    '{"name":"FlareSolverr","implementation":"FlareSolverr","configContract":"FlareSolverrSettings","tags":[],"fields":[{"name":"host","value":"http://flaresolverr:8191"},{"name":"requestTimeout","value":60}]}')
  if echo "$RESULT" | jq -e '.id' &>/dev/null; then
    echo "$RESULT" | jq -r '"  Registered: " + .name + " (id: \(.id))"'
  else
    red "  Failed to register FlareSolverr in Prowlarr:"
    echo "$RESULT"
    exit 1
  fi
fi

# ─── Bitmagnet → Prowlarr ───────────────────────────────────────────────────
step "SKIPPED: Prowlarr: registering Bitmagnet as a Torznab indexer"
# EXISTING_INDEXERS=$(prowlarr_ssh GET "indexer")
# if echo "$EXISTING_INDEXERS" | jq -e '.[] | select(.name == "Bitmagnet")' &>/dev/null; then
#   green "  Bitmagnet indexer already registered"
# else
#   RESULT=$(prowlarr_ssh POST "indexer" \
#     '{"name":"Bitmagnet","enable":true,"implementation":"Torznab","configContract":"TorznabSettings","priority":25,"fields":[{"name":"baseUrl","value":"http://bitmagnet:3333/torznab"},{"name":"apiPath","value":"/api"},{"name":"categories","value":[]}]}')
#   if echo "$RESULT" | jq -e '.id' &>/dev/null; then
#     echo "$RESULT" | jq -r '"  Registered: " + .name + " (id: \(.id))"'
#   else
#     red "  Failed to register Bitmagnet in Prowlarr:"
#     echo "$RESULT"
#     exit 1
#   fi
# fi

# ─── Listenarr ─────────────────────────────────────────────────────────────
listenarr() {
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -sf -X "$method" \
      -H "X-Api-Key: ${LISTENARR_API}" \
      -H "Content-Type: application/json" \
      -d "$body" \
      "${LISTENARR_URL}/api/v1/${path}"
  else
    curl -sf -X "$method" \
      -H "X-Api-Key: ${LISTENARR_API}" \
      "${LISTENARR_URL}/api/v1/${path}"
  fi
}

step "Listenarr: checking connectivity"
listenarr GET "system/info" | jq -r '"  Version: " + .version'

step "Listenarr: adding qBittorrent as download client"
EXISTING_LISTENARR_DC=$(listenarr GET "configuration/download-clients")
if echo "$EXISTING_LISTENARR_DC" | jq -e '.[] | select(.name == "qBittorrent")' &>/dev/null; then
  green "  Download client qBittorrent already exists"
else
  RESULT=$(listenarr POST "configuration/download-clients" "{
    \"name\": \"qBittorrent\",
    \"type\": \"qbittorrent\",
    \"host\": \"qbittorrent\",
    \"port\": 8080,
    \"username\": \"${QBIT_USER}\",
    \"password\": \"${QBIT_PASS}\",
    \"downloadPath\": \"/downloads\",
    \"isEnabled\": true,
    \"removeCompletedDownloads\": \"none\",
    \"settings\": {\"category\": \"audiobooks\"}
  }")
  if echo "$RESULT" | jq -e '.id' &>/dev/null; then
    echo "$RESULT" | jq -r '"  Added download client: " + .id'
  else
    red "  Failed to add Listenarr download client:"
    echo "$RESULT"
    exit 1
  fi
fi

step "Listenarr: adding root folder /audiobooks"
EXISTING_ROOTS=$(listenarr GET "rootfolders")
if echo "$EXISTING_ROOTS" | jq -e '.[] | select(.path == "/audiobooks")' &>/dev/null; then
  green "  Root folder /audiobooks already exists"
else
  RESULT=$(listenarr POST "rootfolders" '{"name":"Audiobooks","path":"/audiobooks","isDefault":true}')
  if echo "$RESULT" | jq -e '.id' &>/dev/null; then
    echo "$RESULT" | jq -r '"  Added root folder: " + .path'
  else
    red "  Failed to add root folder:"
    echo "$RESULT"
    exit 1
  fi
fi

# ─── Done ──────────────────────────────────────────────────────────────────
echo
green "All done! Services are configured:"
echo "  qBittorrent  http://qbit.home        user: ${QBIT_USER}  pass: ${QBIT_PASS}"
echo "  Sonarr       http://sonarr.home"
echo "  Radarr       http://radarr.home"
echo "  Prowlarr     http://prowlarr.home"
echo "  Listenarr    http://listenarr.home"
echo
echo "Next step: add indexers in Prowlarr"
echo "  http://prowlarr.home -> Indexers -> Add Indexer"
echo "  They will sync automatically to Sonarr and Radarr."
