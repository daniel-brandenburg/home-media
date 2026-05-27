"""
tasks/tailscale.py — install and configure Tailscale on the media server

Steps:
  1. Add the Tailscale zypper repository (openSUSE MicroOS / Leap / Tumbleweed).
  2. Install the `tailscale` package via zypper.
  3. Enable and start the `tailscaled` daemon.
  4. If TAILSCALE_AUTH_KEY is set in the environment, run `tailscale up`
     non-interactively using the pre-auth key.
     Otherwise, print a reminder to run `tailscale up` manually.

Pre-auth keys can be generated at: https://login.tailscale.com/admin/settings/keys
Set TAILSCALE_AUTH_KEY in your .env (it is single-use and short-lived by default).

Run standalone:
    pyinfra deploy/inventory.py deploy/tasks/tailscale.py
"""

import os

from pyinfra.operations import server, systemd, zypper

TAILSCALE_AUTH_KEY = os.environ.get("TAILSCALE_AUTH_KEY", "")

# ── Add Tailscale zypper repository ───────────────────────────────────────────
# The stable repo covers openSUSE Tumbleweed and MicroOS.
server.shell(
    name="zypper: add Tailscale repository",
    commands=[
        "set -euo pipefail",
        (
            "zypper --non-interactive addrepo --refresh --check "
            "https://pkgs.tailscale.com/stable/opensuse/tumbleweed/tailscale.repo "
            "|| true"  # no-op if already added
        ),
        "zypper --non-interactive --gpg-auto-import-keys refresh tailscale",
    ],
)

# ── Install tailscale package ──────────────────────────────────────────────────
zypper.packages(
    name="zypper: install tailscale",
    packages=["tailscale"],
    present=True,
)

# ── Enable and start tailscaled ───────────────────────────────────────────────
systemd.service(
    name="systemd: enable and start tailscaled",
    service="tailscaled",
    enabled=True,
    running=True,
)

# ── Bring up the Tailscale interface ─────────────────────────────────────────
if TAILSCALE_AUTH_KEY:
    server.shell(
        name="tailscale: authenticate with pre-auth key",
        commands=[
            "set -euo pipefail",
            f"tailscale up --authkey={TAILSCALE_AUTH_KEY} --ssh",
        ],
    )
else:
    server.shell(
        name="tailscale: check current status (manual auth required if not yet up)",
        commands=[
            "set -euo pipefail",
            # Print status so the operator can see whether auth is needed.
            "tailscale status || echo '[tailscale] Not yet authenticated — run: sudo tailscale up --ssh'",
        ],
    )
