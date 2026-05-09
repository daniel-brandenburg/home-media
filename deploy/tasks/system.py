"""
tasks/system.py — host package installation and directory scaffolding

Ensures the server has the required packages installed and that all
/srv/containers/<service> config directories exist with the right ownership.
"""

import os

from pyinfra import host
from pyinfra.operations import files, server, zypper

# ── Required host packages ──────────────────────────────────────────────────────
# Read from packages.txt at the repo root (one package per line, # comments ok)
_packages_txt = os.path.join(os.path.dirname(__file__), "..", "..", "packages.txt")
with open(_packages_txt) as _f:
    PACKAGES = [
        line.strip()
        for line in _f
        if line.strip() and not line.strip().startswith("#")
    ]

zypper.packages(
    name="Install required host packages",
    packages=PACKAGES,
    present=True,
)

# ── Directory structure on the server ──────────────────────────────────────────
# /srv/containers/<service>  — quadlet EnvironmentFile and per-service config
# /srv/media                 — external exFAT drive (mount managed by systemd unit)

REMOTE_DIR = os.environ.get("REMOTE_DIR", "/srv/containers")
PUID = int(os.environ.get("PUID", 1000))
PGID = int(os.environ.get("PGID", 1000))

_config_dirs = [
    REMOTE_DIR,
    f"{REMOTE_DIR}/caddy/data",
    f"{REMOTE_DIR}/caddy/config",
    f"{REMOTE_DIR}/dashy",
    f"{REMOTE_DIR}/qbittorrent/custom-cont-init.d",
    f"{REMOTE_DIR}/prowlarr",
    f"{REMOTE_DIR}/sonarr",
    f"{REMOTE_DIR}/radarr",
    f"{REMOTE_DIR}/audiobookshelf/config",
    f"{REMOTE_DIR}/audiobookshelf/metadata",
    f"{REMOTE_DIR}/calibre-web-automated",
    f"{REMOTE_DIR}/shelfmark",
    f"{REMOTE_DIR}/bitmagnet/postgres",
    f"{REMOTE_DIR}/bitmagnet/config",
    f"{REMOTE_DIR}/jellyfin",
]

for _dir in _config_dirs:
    files.directory(
        name=f"Ensure directory exists: {_dir}",
        path=_dir,
        present=True,
        user=PUID,
        group=PGID,
        mode="750",
    )
