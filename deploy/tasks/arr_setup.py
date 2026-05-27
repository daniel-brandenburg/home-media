"""
tasks/arr_setup.py — one-time API wiring for *arr services + qBittorrent

Configures qBittorrent, Sonarr, Radarr, Prowlarr, and Listenarr to work
together.  Run this once after the stack is up for the first time.
All operations are idempotent — safe to re-run.

Usage
-----
    pyinfra deploy/inventory.py deploy/tasks/arr_setup.py

Environment variables (from .env or real env)
---------------------------------------------
Required:
    REMOTE       LAN IP of the media server
    REMOTE_DIR      Remote config path (default: /srv/containers)

qBittorrent:
    QBIT_USER       WebUI username
    QBIT_PASS       WebUI password

*arr API keys (auto-fetched from server if blank):
    SONARR_API
    RADARR_API
    PROWLARR_API
    LISTENARR_API
"""

import os
import sys

# Load .env from the repo root if python-dotenv is available
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
except ImportError:
    pass

from pyinfra.operations import server

# ── Validate required environment variables ────────────────────────────────────


def _require_env(*names: str) -> dict[str, str]:
    """Return a dict of env var values; abort with a clear message if any are missing."""
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        print(
            "ERROR: The following environment variables are required but not set:\n"
            + "\n".join(f"  {n}" for n in missing)
            + "\n\nSet them in your .env file or export them before running this task.",
            file=sys.stderr,
        )
        sys.exit(1)
    return {n: os.environ[n] for n in names}


_required = _require_env("REMOTE", "QBIT_USER", "QBIT_PASS")

REMOTE = _required["REMOTE"]
QBIT_USER = _required["QBIT_USER"]
QBIT_PASS = _required["QBIT_PASS"]
REMOTE_DIR = os.environ.get("REMOTE_DIR", "/srv/containers")

QBIT_URL = f"http://{REMOTE}:8080"
SONARR_URL = f"http://{REMOTE}:8989"
RADARR_URL = f"http://{REMOTE}:7878"
LISTENARR_URL = f"http://{REMOTE}:4545"

# API keys — if blank, auto-fetch via SSH from the app's config file on the server
SONARR_API = os.environ.get("SONARR_API", "")
RADARR_API = os.environ.get("RADARR_API", "")
PROWLARR_API = os.environ.get("PROWLARR_API", "")
LISTENARR_API = os.environ.get("LISTENARR_API", "")


def _fetch_xml_api_key(config_path: str) -> str:
    """Shell snippet that prints the ApiKey value from a *arr config.xml."""
    return f"grep -oP '(?<=<ApiKey>)[^<]+' '{config_path}' 2>/dev/null || true"


def _fetch_json_api_key(config_path: str) -> str:
    """Shell snippet that prints the ApiKey value from a JSON config file."""
    return f"jq -r '.ApiKey // empty' '{config_path}' 2>/dev/null || true"


# ── qBittorrent ────────────────────────────────────────────────────────────────

_qbit_cookie = "/tmp/qbit_arr_setup.cookie"

server.shell(
    name="qBittorrent: wait for WebUI to be ready, then log in",
    commands=[
        f"""
set -euo pipefail
QBIT_URL="{QBIT_URL}"
QBIT_USER="{QBIT_USER}"
QBIT_PASS="{QBIT_PASS}"
COOKIE="{_qbit_cookie}"

echo "Waiting for qBittorrent WebUI..."
for i in $(seq 1 30); do
  if curl -sf "$QBIT_URL/api/v2/app/version" > /dev/null 2>&1; then
    echo "  WebUI ready (attempt $i)"
    break
  fi
  if [[ $i -eq 30 ]]; then
    echo "ERROR: qBittorrent WebUI did not become ready after 30 attempts." >&2; exit 1
  fi
  sleep 2
done

body=$(curl -s -c "$COOKIE" --data "username=$QBIT_USER&password=$QBIT_PASS" \\
  -H "Referer: $QBIT_URL" "$QBIT_URL/api/v2/auth/login")
if [[ "$body" != *"Ok."* ]]; then
  echo "ERROR: qBittorrent login failed. Check QBIT_USER/QBIT_PASS in .env and re-run deploy first." >&2; exit 1
fi
echo "Logged in successfully."
""",
    ],
)

server.shell(
    name="qBittorrent: set default save path and temp path",
    commands=[
        f"""
curl -s -b "{_qbit_cookie}" \\
  --data-urlencode 'json={{"save_path":"/downloads","temp_path_enabled":true,"temp_path":"/downloads/incomplete"}}' \\
  "{QBIT_URL}/api/v2/app/setPreferences" > /dev/null
echo "save_path=/downloads"
""",
    ],
)

for _cat, _path in [
    ("tv", "/downloads/tv"),
    ("movies", "/downloads/movies"),
    ("audiobooks", "/downloads/audiobooks"),
]:
    server.shell(
        name=f"qBittorrent: ensure category '{_cat}'",
        commands=[
            f"""
curl -s -b "{_qbit_cookie}" --data-urlencode "category={_cat}" --data-urlencode "savePath={_path}" \\
  "{QBIT_URL}/api/v2/torrents/createCategory" > /dev/null || true
curl -s -b "{_qbit_cookie}" --data-urlencode "category={_cat}" --data-urlencode "savePath={_path}" \\
  "{QBIT_URL}/api/v2/torrents/editCategory" > /dev/null || true
echo "Category '{_cat}' -> {_path}"
""",
        ],
    )

# ── API key resolution ────────────────────────────────────────────────────────
# Each key is resolved from the env; if missing, it is fetched from the server.


def _api_key_shell_var(var: str, current_val: str, fetch_cmd: str) -> str:
    """
    Returns a shell fragment that sets VAR either from the provided value
    or by running fetch_cmd on the server.  Aborts if neither works.
    """
    if current_val:
        return f'{var}="{current_val}"'
    return f"""
{var}=$({fetch_cmd})
if [[ -z "${{{var}}}" ]]; then
  echo "ERROR: {var} could not be resolved. Start the stack and re-run, or set {var} in .env." >&2
  exit 1
fi
echo "Auto-fetched {var}: ${{{var}}}"
"""


_sonarr_key_block = _api_key_shell_var(
    "SONARR_API",
    SONARR_API,
    _fetch_xml_api_key(f"{REMOTE_DIR}/sonarr/config.xml"),
)
_radarr_key_block = _api_key_shell_var(
    "RADARR_API",
    RADARR_API,
    _fetch_xml_api_key(f"{REMOTE_DIR}/radarr/config.xml"),
)
_prowlarr_key_block = _api_key_shell_var(
    "PROWLARR_API",
    PROWLARR_API,
    _fetch_xml_api_key(f"{REMOTE_DIR}/prowlarr/config.xml"),
)
_listenarr_key_block = _api_key_shell_var(
    "LISTENARR_API",
    LISTENARR_API,
    _fetch_json_api_key(f"{REMOTE_DIR}/listenarr/config.json"),
)

# ── Sonarr ────────────────────────────────────────────────────────────────────

server.shell(
    name="Sonarr: configure media management (hardlinks + rename)",
    commands=[
        f"""
set -euo pipefail
{_sonarr_key_block}
BASE="{SONARR_URL}/api/v3"
CURRENT=$(curl -sf -H "X-Api-Key: $SONARR_API" "$BASE/config/mediamanagement")
UPDATED=$(echo "$CURRENT" | jq '
  .copyUsingHardlinks = true |
  .importExtraFiles = false |
  .renameSeries = true |
  .replaceIllegalCharacters = true |
  .deleteEmptyFolders = true
')
curl -sf -X PUT -H "X-Api-Key: $SONARR_API" -H "Content-Type: application/json" \\
  -d "$UPDATED" "$BASE/config/mediamanagement" | jq -r '"  hardLinks: \\(.copyUsingHardlinks), rename: \\(.renameSeries)"'
""",
    ],
)

server.shell(
    name="Sonarr: ensure root folder /data/TV",
    commands=[
        f"""
set -euo pipefail
{_sonarr_key_block}
BASE="{SONARR_URL}/api/v3"
ROOTS=$(curl -sf -H "X-Api-Key: $SONARR_API" "$BASE/rootfolder")
if echo "$ROOTS" | jq -e '.[] | select(.path == "/data/TV")' > /dev/null; then
  echo "  Root folder /data/TV already exists"
else
  curl -sf -X POST -H "X-Api-Key: $SONARR_API" -H "Content-Type: application/json" \\
    -d '{{"path":"/data/TV"}}' "$BASE/rootfolder" | jq -r '"  Added: " + .path'
fi
""",
    ],
)

server.shell(
    name="Sonarr: ensure remote path mapping (qBittorrent /downloads -> /data/downloads)",
    commands=[
        f"""
set -euo pipefail
{_sonarr_key_block}
BASE="{SONARR_URL}/api/v3"
HOST="{REMOTE}"
RPMS=$(curl -sf -H "X-Api-Key: $SONARR_API" "$BASE/remotepathmapping")
if echo "$RPMS" | jq -e --arg h "$HOST" '.[] | select(.host == $h)' > /dev/null; then
  echo "  Remote path mapping for $HOST already exists"
else
  curl -sf -X POST -H "X-Api-Key: $SONARR_API" -H "Content-Type: application/json" \\
    -d "{{\\"host\\":\\"$HOST\\",\\"remotePath\\":\\"/downloads/\\",\\"localPath\\":\\"/data/downloads/\\"}}" \\
    "$BASE/remotepathmapping" | jq -r '"  Mapped: " + .remotePath + " -> " + .localPath'
fi
""",
    ],
)

server.shell(
    name="Sonarr: ensure qBittorrent download client",
    commands=[
        f"""
set -euo pipefail
{_sonarr_key_block}
BASE="{SONARR_URL}/api/v3"
HOST="{REMOTE}"
DCS=$(curl -sf -H "X-Api-Key: $SONARR_API" "$BASE/downloadclient")
if echo "$DCS" | jq -e '.[] | select(.name == "qBittorrent")' > /dev/null; then
  echo "  qBittorrent download client already configured in Sonarr"
else
  RESULT=$(curl -sf -X POST -H "X-Api-Key: $SONARR_API" -H "Content-Type: application/json" \\
    -d "{{
      \\"name\\": \\"qBittorrent\\",
      \\"enable\\": true,
      \\"protocol\\": \\"torrent\\",
      \\"priority\\": 1,
      \\"implementation\\": \\"QBittorrent\\",
      \\"configContract\\": \\"QBittorrentSettings\\",
      \\"fields\\": [
        {{\\"name\\": \\"host\\",           \\"value\\": \\"$HOST\\"}},
        {{\\"name\\": \\"port\\",           \\"value\\": 8080}},
        {{\\"name\\": \\"username\\",       \\"value\\": \\"{QBIT_USER}\\"}},
        {{\\"name\\": \\"password\\",       \\"value\\": \\"{QBIT_PASS}\\"}},
        {{\\"name\\": \\"tvCategory\\",     \\"value\\": \\"tv\\"}},
        {{\\"name\\": \\"initialState\\",   \\"value\\": 0}},
        {{\\"name\\": \\"sequentialOrder\\",\\"value\\": false}},
        {{\\"name\\": \\"firstAndLast\\",   \\"value\\": false}}
      ]
    }}" "$BASE/downloadclient")
  echo "$RESULT" | jq -e '.id' > /dev/null || {{ echo "ERROR: $RESULT" >&2; exit 1; }}
  echo "$RESULT" | jq -r '"  Added: " + .name'
fi
""",
    ],
)

# ── Radarr ────────────────────────────────────────────────────────────────────

server.shell(
    name="Radarr: configure media management (hardlinks + rename)",
    commands=[
        f"""
set -euo pipefail
{_radarr_key_block}
BASE="{RADARR_URL}/api/v3"
CURRENT=$(curl -sf -H "X-Api-Key: $RADARR_API" "$BASE/config/mediamanagement")
UPDATED=$(echo "$CURRENT" | jq '
  .copyUsingHardlinks = true |
  .importExtraFiles = false |
  .renameMovies = true |
  .replaceIllegalCharacters = true |
  .deleteEmptyFolders = true
')
curl -sf -X PUT -H "X-Api-Key: $RADARR_API" -H "Content-Type: application/json" \\
  -d "$UPDATED" "$BASE/config/mediamanagement" | jq -r '"  hardLinks: \\(.copyUsingHardlinks), rename: \\(.renameMovies)"'
""",
    ],
)

server.shell(
    name="Radarr: ensure root folder /data/Movies",
    commands=[
        f"""
set -euo pipefail
{_radarr_key_block}
BASE="{RADARR_URL}/api/v3"
ROOTS=$(curl -sf -H "X-Api-Key: $RADARR_API" "$BASE/rootfolder")
if echo "$ROOTS" | jq -e '.[] | select(.path == "/data/Movies")' > /dev/null; then
  echo "  Root folder /data/Movies already exists"
else
  curl -sf -X POST -H "X-Api-Key: $RADARR_API" -H "Content-Type: application/json" \\
    -d '{{"path":"/data/Movies"}}' "$BASE/rootfolder" | jq -r '"  Added: " + .path'
fi
""",
    ],
)

server.shell(
    name="Radarr: ensure remote path mapping (qBittorrent /downloads -> /data/downloads)",
    commands=[
        f"""
set -euo pipefail
{_radarr_key_block}
BASE="{RADARR_URL}/api/v3"
HOST="{REMOTE}"
RPMS=$(curl -sf -H "X-Api-Key: $RADARR_API" "$BASE/remotepathmapping")
if echo "$RPMS" | jq -e --arg h "$HOST" '.[] | select(.host == $h)' > /dev/null; then
  echo "  Remote path mapping for $HOST already exists"
else
  curl -sf -X POST -H "X-Api-Key: $RADARR_API" -H "Content-Type: application/json" \\
    -d "{{\\"host\\":\\"$HOST\\",\\"remotePath\\":\\"/downloads/\\",\\"localPath\\":\\"/data/downloads/\\"}}" \\
    "$BASE/remotepathmapping" | jq -r '"  Mapped: " + .remotePath + " -> " + .localPath'
fi
""",
    ],
)

server.shell(
    name="Radarr: ensure qBittorrent download client",
    commands=[
        f"""
set -euo pipefail
{_radarr_key_block}
BASE="{RADARR_URL}/api/v3"
HOST="{REMOTE}"
DCS=$(curl -sf -H "X-Api-Key: $RADARR_API" "$BASE/downloadclient")
if echo "$DCS" | jq -e '.[] | select(.name == "qBittorrent")' > /dev/null; then
  echo "  qBittorrent download client already configured in Radarr"
else
  RESULT=$(curl -sf -X POST -H "X-Api-Key: $RADARR_API" -H "Content-Type: application/json" \\
    -d "{{
      \\"name\\": \\"qBittorrent\\",
      \\"enable\\": true,
      \\"protocol\\": \\"torrent\\",
      \\"priority\\": 1,
      \\"implementation\\": \\"QBittorrent\\",
      \\"configContract\\": \\"QBittorrentSettings\\",
      \\"fields\\": [
        {{\\"name\\": \\"host\\",            \\"value\\": \\"$HOST\\"}},
        {{\\"name\\": \\"port\\",            \\"value\\": 8080}},
        {{\\"name\\": \\"username\\",        \\"value\\": \\"{QBIT_USER}\\"}},
        {{\\"name\\": \\"password\\",        \\"value\\": \\"{QBIT_PASS}\\"}},
        {{\\"name\\": \\"movieCategory\\",   \\"value\\": \\"movies\\"}},
        {{\\"name\\": \\"initialState\\",    \\"value\\": 0}},
        {{\\"name\\": \\"sequentialOrder\\", \\"value\\": false}},
        {{\\"name\\": \\"firstAndLast\\",    \\"value\\": false}}
      ]
    }}" "$BASE/downloadclient")
  echo "$RESULT" | jq -e '.id' > /dev/null || {{ echo "ERROR: $RESULT" >&2; exit 1; }}
  echo "$RESULT" | jq -r '"  Added: " + .name'
fi
""",
    ],
)

# ── Prowlarr ──────────────────────────────────────────────────────────────────
# Prowlarr's port (9696) may be firewalled externally.
# We call the Prowlarr API via localhost on the remote host using server.shell,
# which already runs over SSH — no extra SSH hop needed.

server.shell(
    name="Prowlarr: register Sonarr as an application",
    commands=[
        f"""
set -euo pipefail
{_prowlarr_key_block}
{_sonarr_key_block}
APPS=$(curl -sf -H "X-Api-Key: $PROWLARR_API" http://localhost:9696/api/v1/applications)
if echo "$APPS" | jq -e '.[] | select(.name == "Sonarr")' > /dev/null; then
  echo "  Sonarr already registered in Prowlarr"
else
  RESULT=$(curl -sf -X POST -H "X-Api-Key: $PROWLARR_API" -H "Content-Type: application/json" \\
    -d "{{
      \\"name\\":\\"Sonarr\\",\\"syncLevel\\":\\"fullSync\\",
      \\"implementation\\":\\"Sonarr\\",\\"configContract\\":\\"SonarrSettings\\",
      \\"fields\\":[
        {{\\"name\\":\\"prowlarrUrl\\",\\"value\\":\\"http://prowlarr:9696\\"}},
        {{\\"name\\":\\"baseUrl\\",\\"value\\":\\"http://sonarr:8989\\"}},
        {{\\"name\\":\\"apiKey\\",\\"value\\":\\"$SONARR_API\\"}},
        {{\\"name\\":\\"syncCategories\\",\\"value\\":[5000,5010,5020,5030,5040,5045,5050,5090]}}
      ]
    }}" http://localhost:9696/api/v1/applications)
  echo "$RESULT" | jq -e '.id' > /dev/null || {{ echo "ERROR: $RESULT" >&2; exit 1; }}
  echo "$RESULT" | jq -r '"  Registered: " + .name'
fi
""",
    ],
)

server.shell(
    name="Prowlarr: register Radarr as an application",
    commands=[
        f"""
set -euo pipefail
{_prowlarr_key_block}
{_radarr_key_block}
APPS=$(curl -sf -H "X-Api-Key: $PROWLARR_API" http://localhost:9696/api/v1/applications)
if echo "$APPS" | jq -e '.[] | select(.name == "Radarr")' > /dev/null; then
  echo "  Radarr already registered in Prowlarr"
else
  RESULT=$(curl -sf -X POST -H "X-Api-Key: $PROWLARR_API" -H "Content-Type: application/json" \\
    -d "{{
      \\"name\\":\\"Radarr\\",\\"syncLevel\\":\\"fullSync\\",
      \\"implementation\\":\\"Radarr\\",\\"configContract\\":\\"RadarrSettings\\",
      \\"fields\\":[
        {{\\"name\\":\\"prowlarrUrl\\",\\"value\\":\\"http://prowlarr:9696\\"}},
        {{\\"name\\":\\"baseUrl\\",\\"value\\":\\"http://radarr:7878\\"}},
        {{\\"name\\":\\"apiKey\\",\\"value\\":\\"$RADARR_API\\"}},
        {{\\"name\\":\\"syncCategories\\",\\"value\\":[2000,2010,2020,2030,2040,2045,2050,2060,2070,2080,2090]}}
      ]
    }}" http://localhost:9696/api/v1/applications)
  echo "$RESULT" | jq -e '.id' > /dev/null || {{ echo "ERROR: $RESULT" >&2; exit 1; }}
  echo "$RESULT" | jq -r '"  Registered: " + .name'
fi
""",
    ],
)

server.shell(
    name="Prowlarr: register FlareSolverr as an indexer proxy",
    commands=[
        f"""
set -euo pipefail
{_prowlarr_key_block}
PROXIES=$(curl -sf -H "X-Api-Key: $PROWLARR_API" http://localhost:9696/api/v1/indexerproxy)
if echo "$PROXIES" | jq -e '.[] | select(.name == "FlareSolverr")' > /dev/null; then
  echo "  FlareSolverr proxy already registered"
else
  RESULT=$(curl -sf -X POST -H "X-Api-Key: $PROWLARR_API" -H "Content-Type: application/json" \\
    -d '{{"name":"FlareSolverr","implementation":"FlareSolverr","configContract":"FlareSolverrSettings","tags":[],"fields":[{{"name":"host","value":"http://flaresolverr:8191"}},{{"name":"requestTimeout","value":60}}]}}' \\
    http://localhost:9696/api/v1/indexerproxy)
  echo "$RESULT" | jq -e '.id' > /dev/null || {{ echo "ERROR: $RESULT" >&2; exit 1; }}
  echo "$RESULT" | jq -r '"  Registered: " + .name'
fi
""",
    ],
)

# ── Listenarr ─────────────────────────────────────────────────────────────────

server.shell(
    name="Listenarr: ensure qBittorrent download client",
    commands=[
        f"""
set -euo pipefail
{_listenarr_key_block}
BASE="{LISTENARR_URL}/api/v1"
HOST="{REMOTE}"
DCS=$(curl -sf -H "X-Api-Key: $LISTENARR_API" "$BASE/configuration/download-clients")
if echo "$DCS" | jq -e '.[] | select(.name == "qBittorrent")' > /dev/null; then
  echo "  qBittorrent download client already configured in Listenarr"
else
  RESULT=$(curl -sf -X POST -H "X-Api-Key: $LISTENARR_API" -H "Content-Type: application/json" \\
    -d "{{
      \\"name\\": \\"qBittorrent\\",
      \\"type\\": \\"qbittorrent\\",
      \\"host\\": \\"$HOST\\",
      \\"port\\": 8080,
      \\"username\\": \\"{QBIT_USER}\\",
      \\"password\\": \\"{QBIT_PASS}\\",
      \\"downloadPath\\": \\"/downloads\\",
      \\"isEnabled\\": true,
      \\"removeCompletedDownloads\\": \\"none\\",
      \\"settings\\": {{\\"category\\": \\"audiobooks\\"}}
    }}" "$BASE/configuration/download-clients")
  echo "$RESULT" | jq -e '.id' > /dev/null || {{ echo "ERROR: $RESULT" >&2; exit 1; }}
  echo "$RESULT" | jq -r '"  Added download client: " + .id'
fi
""",
    ],
)

server.shell(
    name="Listenarr: ensure root folder /audiobooks",
    commands=[
        f"""
set -euo pipefail
{_listenarr_key_block}
BASE="{LISTENARR_URL}/api/v1"
ROOTS=$(curl -sf -H "X-Api-Key: $LISTENARR_API" "$BASE/rootfolders")
if echo "$ROOTS" | jq -e '.[] | select(.path == "/audiobooks")' > /dev/null; then
  echo "  Root folder /audiobooks already exists"
else
  RESULT=$(curl -sf -X POST -H "X-Api-Key: $LISTENARR_API" -H "Content-Type: application/json" \\
    -d '{{"name":"Audiobooks","path":"/audiobooks","isDefault":true}}' "$BASE/rootfolders")
  echo "$RESULT" | jq -e '.id' > /dev/null || {{ echo "ERROR: $RESULT" >&2; exit 1; }}
  echo "$RESULT" | jq -r '"  Added root folder: " + .path'
fi
""",
    ],
)

# ── Done ──────────────────────────────────────────────────────────────────────

server.shell(
    name="arr_setup: print summary",
    commands=[
        f"""
echo ""
echo "All services configured:"
echo "  qBittorrent    http://{REMOTE}:8080   user: {QBIT_USER}"
echo "  Sonarr         http://{REMOTE}:8989"
echo "  Radarr         http://{REMOTE}:7878"
echo "  Prowlarr       http://{REMOTE}:9696"
echo "  Listenarr      http://{REMOTE}:4545"
echo ""
echo "Next: add indexers in Prowlarr -> Indexers -> Add Indexer"
""",
    ],
)
