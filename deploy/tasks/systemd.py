"""
tasks/systemd.py — install systemd units and activate the stack

Uploads:
  - systemd/home-media.target   → /etc/systemd/system/home-media.target
  - systemd/srv-media.mount     → /etc/systemd/system/srv-media.mount
  - systemd/srv-media.automount → /etc/systemd/system/srv-media.automount

Then:
  - Runs systemctl daemon-reload so systemd picks up the quadlets and units
  - Enables and starts all container services and the home-media.target
"""

import os

from pyinfra.operations import files, systemd

_repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
_systemd_src = os.path.join(_repo_root, "systemd")
_systemd_dest = "/etc/systemd/system"

# ── Upload systemd unit files ──────────────────────────────────────────────────
for _filename in sorted(os.listdir(_systemd_src)):
    _src = os.path.join(_systemd_src, _filename)
    if not os.path.isfile(_src):
        continue

    files.put(
        name=f"Upload systemd unit: {_filename}",
        src=_src,
        dest=f"{_systemd_dest}/{_filename}",
        mode="644",
    )

# ── Reload systemd so the generator picks up the new quadlets ─────────────────
systemd.daemon_reload(
    name="systemd daemon-reload (pick up quadlets and new units)",
)

# ── Enable and start the mount units ──────────────────────────────────────────
for _unit in ("srv-media.automount",):
    systemd.service(
        name=f"Enable and start {_unit}",
        service=_unit,
        enabled=True,
        running=True,
    )

# ── Enable and start all container services ───────────────────────────────────
_container_services = [
    "caddy.service",
    "dashy.service",
    "prowlarr.service",
    "flaresolverr.service",
    "audiobookshelf.service",
    "calibre-web-automated.service",
    "shelfmark.service",
    "ebook-handoff.service",
    "jellyfin.service",
    "qbittorrent.service",
    "sonarr.service",
    "radarr.service",
]

for _svc in _container_services:
    systemd.service(
        name=f"Enable and start {_svc}",
        service=_svc,
        enabled=True,
        running=True,
    )

# ── Bring up the grouping target ──────────────────────────────────────────────
systemd.service(
    name="Enable home-media.target",
    service="home-media.target",
    enabled=True,
    running=True,
)
