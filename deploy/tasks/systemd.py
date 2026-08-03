"""
tasks/systemd.py — install systemd units and activate the stack

Uploads every file directly under systemd/ (non-recursive) to
/etc/systemd/system/, substituting any ${PLACEHOLDER} tokens found (see
_SUBSTITUTIONS below) before upload:
  - systemd/home-media.target   → /etc/systemd/system/home-media.target
  - systemd/srv-media.mount     → /etc/systemd/system/srv-media.mount
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
REMOTE_DIR = os.environ.get("REMOTE_DIR", "/srv/containers")

# Applied to every uploaded unit's content, not just one filename — so new
# units referencing ${REMOTE_DIR} don't need a new filename-specific case.
_SUBSTITUTIONS = {
    "${MEDIA_UUID}": MEDIA_UUID,
    "${REMOTE_DIR}": REMOTE_DIR,
}

# ── Upload systemd unit files ──────────────────────────────────────────────────
_timer_units = []
for _filename in sorted(os.listdir(_systemd_src)):
    _src = os.path.join(_systemd_src, _filename)
    if not os.path.isfile(_src):
        continue

    with open(_src) as _f:
        _content = _f.read()

    for _placeholder, _value in _SUBSTITUTIONS.items():
        if _value:
            _content = _content.replace(_placeholder, _value)

    files.put(
        name=f"Upload systemd unit: {_filename}",
        src=io.StringIO(_content),
        dest=f"{_systemd_dest}/{_filename}",
        mode="644",
    )

    if _filename.endswith(".timer"):
        _timer_units.append(_filename)

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

# ── Enable every scheduled-prompt timer ────────────────────────────────────────
# `running=True` here starts (arms) the timer unit itself, which just makes
# systemd wait for its next OnCalendar= match — it does not fire the paired
# .service immediately, unlike running=True on a .service.
for _unit in sorted(_timer_units):
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
