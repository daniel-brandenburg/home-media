"""
tasks/system.py — host package installation and directory scaffolding

Ensures the server has the required packages installed and that all
/srv/containers/<service> config directories exist with the right ownership.
"""

import os

from pyinfra import host
from pyinfra.facts.rpm import RpmPackages
from pyinfra.operations import files, server

# ── Remove stale Tailscale zypper repo (leftover from before Tailscale was
# dropped from this project) — its untrusted GPG key makes every zypper
# refresh fail, which blocks transactional-update package installs below.
server.shell(
    name="zypper: remove stale Tailscale repository",
    commands=[
        "zypper --non-interactive removerepo tailscale-stable || true",
    ],
)

# ── Required host packages ──────────────────────────────────────────────────────
# Read from packages.txt at the repo root (one package per line, # comments ok)
_packages_txt = os.path.join(os.path.dirname(__file__), "..", "..", "packages.txt")
with open(_packages_txt) as _f:
    PACKAGES = [
        line.strip() for line in _f if line.strip() and not line.strip().startswith("#")
    ]

# The host is an openSUSE transactional-server (MicroOS/Aeon): the root
# filesystem is read-only, so plain `zypper install` always fails with
# "please use transactional-update". Packages must be installed into a new
# btrfs snapshot via `transactional-update`, which only becomes active after
# a reboot.
_installed = host.get_fact(RpmPackages)
_missing_packages = [p for p in PACKAGES if p not in _installed]

if _missing_packages:
    server.shell(
        name=f"Install missing host packages via transactional-update: {', '.join(_missing_packages)}",
        commands=[
            f"transactional-update --non-interactive pkg install {' '.join(_missing_packages)}"
        ],
    )
    server.reboot(
        name="Reboot to activate new transactional-update snapshot",
        delay=60,
        reboot_timeout=600,
    )

# ── Directory structure on the server ──────────────────────────────────────────
# /srv/containers/<service>  — quadlet EnvironmentFile and per-service config
# /srv/media                 — external exFAT drive (mount managed by systemd unit)

REMOTE_DIR = os.environ.get("REMOTE_DIR", "/srv/containers")
PUID = int(os.environ.get("PUID", 1000))
PGID = int(os.environ.get("PGID", 1000))

_config_dirs = [
    REMOTE_DIR,
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
