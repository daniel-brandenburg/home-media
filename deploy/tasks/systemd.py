"""
tasks/systemd.py — install systemd units and activate the stack

Uploads:
  - systemd/home-media.target   → /etc/systemd/system/home-media.target
  - systemd/srv-media.mount     → /etc/systemd/system/srv-media.mount
      (MEDIA_UUID placeholder is expanded in Python before upload)
  - systemd/srv-media.automount → /etc/systemd/system/srv-media.automount

Then:
  - Runs systemctl daemon-reload so systemd picks up the quadlets and units
  - Enables and starts all container services and the home-media.target
"""

import io
import os

from pyinfra.operations import files, systemd

_repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
_systemd_src = os.path.join(_repo_root, "systemd")
_systemd_dest = "/etc/systemd/system"

MEDIA_UUID = os.environ.get("MEDIA_UUID", "")

# ── Upload systemd unit files ──────────────────────────────────────────────────
for _filename in sorted(os.listdir(_systemd_src)):
    _src = os.path.join(_systemd_src, _filename)
    if not os.path.isfile(_src):
        continue

    with open(_src) as _f:
        _content = _f.read()

    # Substitute MEDIA_UUID into the mount unit
    if _filename == "srv-media.mount" and MEDIA_UUID:
        _content = _content.replace("${MEDIA_UUID}", MEDIA_UUID)

    files.put(
        name=f"Upload systemd unit: {_filename}",
        src=io.StringIO(_content),
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

# ── Bring up the grouping target ──────────────────────────────────────────────
# Container services from quadlets are *generated* units (placed in
# /run/systemd/generator/ by podman-quadlet) and cannot be enabled via
# `systemctl enable`.  Instead, each quadlet declares WantedBy=home-media.target
# in its [Install] section, so starting the target is sufficient to bring up
# all containers.
systemd.service(
    name="Enable and start home-media.target",
    service="home-media.target",
    enabled=True,
    running=True,
)
