"""
tasks/devcontainers.py — install devpod CLI and sync devcontainer templates

Installs the devpod CLI (static Go binary, pinned version + sha256 — see
AGENTS.md "Coding Agent Sandbox") to /usr/local/bin, then uploads every file
under the repo's devcontainers/ directory (recursively) to
REMOTE_DIR/devcontainers/ on the server, preserving the directory structure.
Each template's devcontainer.json, Dockerfile, and any supporting files stay
colocated.

Also retires the former Squid egress proxy: the sandboxes now have direct
outbound access, so the rootless Squid user service, its quadlets and its
config directory are removed from the server if present (idempotent).

These are not project repos — they're reusable templates referenced via
devpod's --devcontainer-path flag against whichever repo under /srv/repos
you're working on (see AGENTS.md).
"""

import os

from pyinfra.operations import files, server

# ── devpod CLI ───────────────────────────────────────────────────────────────
# Static binary, no Node/npm/zypper package needed — installed straight to
# /usr/local (a separate rw btrfs subvolume on the transactional-server host,
# unlike / which is read-only). Version pinned; bump deliberately and re-pin
# the sha256 from https://github.com/loft-sh/devpod/releases/<version>.
DEVPOD_VERSION = "v0.6.15"
DEVPOD_SHA256 = "cc50bce09229d5a6d448ac1d4494327f4b8f7a20321e5fcee3bfec1aef0d20c5"

files.download(
    name=f"Install devpod CLI {DEVPOD_VERSION}",
    src=f"https://github.com/loft-sh/devpod/releases/download/{DEVPOD_VERSION}/devpod-linux-amd64",
    dest="/usr/local/bin/devpod",
    mode="755",
    sha256sum=DEVPOD_SHA256,
)

_repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
_devcontainers_dir = os.path.join(_repo_root, "devcontainers")

REMOTE_DIR = os.environ.get("REMOTE_DIR", "/srv/containers")
_remote_devcontainers = f"{REMOTE_DIR}/devcontainers"

# The user that runs devpod / rootless Podman on the server. This matches the
# SSH_USER used by pyinfra (see deploy/inventory.py), defaulting to 'db'.
_devcontainer_user = os.environ.get("SSH_USER", "db")
_home_dir = f"/home/{_devcontainer_user}"
_user_systemd_containers = f"{_home_dir}/.config/containers/systemd"

for _dirpath, _dirnames, _filenames in os.walk(_devcontainers_dir):
    for _filename in sorted(_filenames):
        _src = os.path.join(_dirpath, _filename)
        _rel = os.path.relpath(_src, _devcontainers_dir)

        files.put(
            name=f"Upload devcontainer template file: {_rel}",
            src=_src,
            dest=f"{_remote_devcontainers}/{_rel}",
            mode="644",
        )

# ── Retire the Squid egress proxy ──────────────────────────────────────────────
# Squid used to run here as a rootless user quadlet, with devcontainers joining
# its devcontainer-egress bridge network. It has been removed; everything it
# left on disk is cleaned up below. Podman objects (the systemd-devcontainer-egress
# network and the squid image) are not files — remove those by hand, see
# devcontainers/thirdplacepages/README.md.
#
# Stop the service first (the unit may not exist on a fresh host), then remove
# the quadlets so the next daemon-reload drops the generated units.
server.shell(
    name="Stop the retired Squid user service",
    commands=[
        f"systemctl --user --machine={_devcontainer_user}@.host stop squid.service || true",
    ],
)

files.file(
    name="Remove retired Squid quadlet",
    path=f"{_user_systemd_containers}/squid.container",
    present=False,
)

files.file(
    name="Remove retired devcontainer egress network quadlet",
    path=f"{_user_systemd_containers}/devcontainer-egress.network",
    present=False,
)

files.directory(
    name="Remove retired Squid config directory",
    path=f"{REMOTE_DIR}/squid",
    present=False,
)

# Hand-made symlink left behind by even earlier versions of the Squid task.
files.link(
    name="Remove legacy hand-made squid.service symlink",
    path=f"{_home_dir}/.config/systemd/user/default.target.wants/squid.service",
    present=False,
)

# Keep the devcontainer user's rootless Podman containers (and any tmux
# sessions inside them) alive after logout.
server.shell(
    name=f"Enable linger for {_devcontainer_user}",
    commands=[f"loginctl enable-linger {_devcontainer_user}"],
)

server.shell(
    name="Reload user systemd",
    commands=[f"systemctl --user --machine={_devcontainer_user}@.host daemon-reload"],
)
