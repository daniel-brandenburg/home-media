"""
tasks/quadlets.py — sync Podman quadlet unit files to the server

Uploads every file from the repo's quadlets/ directory to
/etc/containers/systemd/ on the server.  Quadlets placed there are
auto-discovered by systemd's generator on the next daemon-reload.

Requires sudo on the remote side (configured in inventory.py via _sudo=True).
"""

import os

from pyinfra.operations import files

_repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
_quadlets_dir = os.path.join(_repo_root, "quadlets")
_remote_quadlets = "/etc/containers/systemd"

for _filename in sorted(os.listdir(_quadlets_dir)):
    _src = os.path.join(_quadlets_dir, _filename)
    if not os.path.isfile(_src):
        continue

    files.put(
        name=f"Upload quadlet: {_filename}",
        src=_src,
        dest=f"{_remote_quadlets}/{_filename}",
        mode="644",
    )
