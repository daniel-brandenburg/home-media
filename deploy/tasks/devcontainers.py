"""
tasks/devcontainers.py — install devpod CLI and sync devcontainer templates

Installs the devpod CLI (static Go binary, pinned version + sha256 — see
AGENTS.md "Coding Agent Sandbox") to /usr/local/bin, then uploads every file
under the repo's devcontainers/ directory (recursively) to
REMOTE_DIR/devcontainers/ on the server, preserving the directory structure.
Each template's devcontainer.json, Dockerfile, and any supporting files stay
colocated.

Also installs the rootless Squid egress-proxy quadlet into the devcontainer
user's ~/.config/containers/systemd/ and enables it as a user service, so
Squid runs in the same Podman store as the devpod-managed sandboxes.

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

# ── Rootless Squid egress proxy quadlet ────────────────────────────────────────
# devpod runs rootless Podman as _devcontainer_user. The Squid container must
# live in that user's Podman store so devcontainers can reach it as a peer on
# the shared devcontainer-egress bridge network (see config/squid/squid.container
# for why this uses a shared network rather than --network=container:squid).
files.directory(
    name=f"Ensure rootless quadlet dir exists for {_devcontainer_user}",
    path=_user_systemd_containers,
    present=True,
    user=_devcontainer_user,
    group=_devcontainer_user,
    mode="700",
)

files.put(
    name="Upload rootless Squid egress proxy quadlet",
    src=os.path.join(_repo_root, "config", "squid", "squid.container"),
    dest=f"{_user_systemd_containers}/squid.container",
    mode="644",
    user=_devcontainer_user,
    group=_devcontainer_user,
)

files.put(
    name="Upload rootless devcontainer egress network quadlet",
    src=os.path.join(_repo_root, "config", "squid", "devcontainer-egress.network"),
    dest=f"{_user_systemd_containers}/devcontainer-egress.network",
    mode="644",
    user=_devcontainer_user,
    group=_devcontainer_user,
)

# Allow the user service to survive logout / start at boot.
server.shell(
    name=f"Enable linger for {_devcontainer_user}",
    commands=[f"loginctl enable-linger {_devcontainer_user}"],
)

# The quadlet file's [Install] WantedBy=default.target is honored by the
# quadlet generator itself — it creates the default.target.wants symlink in
# its generator output at daemon-reload time. Do NOT hand-create that symlink
# pointing at the .container file: the .container file is not a valid service
# unit, and if it ever shadows the generated unit, `start` fails.
# Remove the hand-made symlink left behind by earlier versions of this task.
files.link(
    name="Remove legacy hand-made squid.service symlink",
    path=f"{_home_dir}/.config/systemd/user/default.target.wants/squid.service",
    present=False,
)
server.shell(
    name="Reload user systemd and (re)start Squid",
    commands=[
        f"systemctl --user --machine={_devcontainer_user}@.host daemon-reload",
        # restart (not start) so redeploys pick up quadlet/config changes;
        # on an inactive unit, restart behaves like start.
        f"systemctl --user --machine={_devcontainer_user}@.host restart squid.service",
    ],
)
