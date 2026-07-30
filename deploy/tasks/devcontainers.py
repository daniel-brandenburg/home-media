"""
tasks/devcontainers.py — install devpod CLI and sync devcontainer templates

Installs the devpod CLI (static Go binary, pinned version + sha256 — see
AGENTS.md "Coding Agent Sandbox") to /usr/local/bin, then uploads every file
under the repo's devcontainers/ directory (recursively) to
REMOTE_DIR/devcontainers/ on the server, preserving the directory structure —
each template's devcontainer.json, Dockerfile, and init-firewall.sh must stay
colocated since the Dockerfile COPYs init-firewall.sh from its own directory.

These are not project repos — they're reusable templates referenced via
devpod's --devcontainer-path flag against whichever repo under /srv/repos
you're working on (see AGENTS.md).
"""

import os

from pyinfra.operations import files

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
