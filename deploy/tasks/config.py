"""
tasks/config.py — upload app config files to the remote server

Uploads:
  - config/caddy/Caddyfile         → REMOTE_DIR/caddy/Caddyfile
  - config/dashy/conf.yml          → REMOTE_DIR/dashy/conf.yml
      (SERVER_IP placeholder is expanded in Python before upload)
  - config/qbittorrent/custom-cont-init.d/99-webui-proxy.sh
      → REMOTE_DIR/qbittorrent/custom-cont-init.d/99-webui-proxy.sh
  - .env (root)                    → REMOTE_DIR/.env
      (quadlet EnvironmentFile= reads this at container start)
"""

import io
import os

from pyinfra.operations import files

# ── Resolve paths ──────────────────────────────────────────────────────────────
_repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
_config_dir = os.path.join(_repo_root, "config")

REMOTE_DIR = os.environ.get("REMOTE_DIR", "/srv/containers")
SERVER_IP = os.environ.get("SERVER_IP", "")

# ── Caddyfile ──────────────────────────────────────────────────────────────────
files.put(
    name="Upload Caddyfile",
    src=os.path.join(_config_dir, "caddy", "Caddyfile"),
    dest=f"{REMOTE_DIR}/caddy/Caddyfile",
    mode="640",
)

# ── dashy conf.yml (SERVER_IP substitution done in Python) ────────────────────
_dashy_src = os.path.join(_config_dir, "dashy", "conf.yml")
with open(_dashy_src) as _f:
    _dashy_content = _f.read()

if SERVER_IP:
    _dashy_content = _dashy_content.replace("${SERVER_IP}", SERVER_IP)

files.put(
    name="Upload dashy conf.yml (SERVER_IP expanded)",
    src=io.StringIO(_dashy_content),
    dest=f"{REMOTE_DIR}/dashy/conf.yml",
    mode="640",
)

# ── qBittorrent WebUI proxy init script ───────────────────────────────────────
files.put(
    name="Upload qBittorrent WebUI proxy init script",
    src=os.path.join(_config_dir, "qbittorrent", "custom-cont-init.d", "99-webui-proxy.sh"),
    dest=f"{REMOTE_DIR}/qbittorrent/custom-cont-init.d/99-webui-proxy.sh",
    mode="755",
)

# ── .env (runtime environment for quadlet EnvironmentFile=) ───────────────────
_env_file = os.path.join(_repo_root, ".env")
if os.path.exists(_env_file):
    files.put(
        name="Upload .env (quadlet runtime environment)",
        src=_env_file,
        dest=f"{REMOTE_DIR}/.env",
        mode="600",
    )
else:
    print(
        f"WARNING: .env not found at {_env_file} — skipping upload.\n"
        "Quadlets will use whatever .env already exists on the server."
    )
