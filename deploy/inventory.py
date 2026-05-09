"""
inventory.py — pyinfra inventory for home-media

Reads connection details from the environment (or a root-level .env file if
python-dotenv is installed).  All required variables must be set before running
any deploy or task:

    cp .env.example .env
    $EDITOR .env
    pyinfra inventory.py deploy/deploy.py

Required env vars
-----------------
REMOTE      SSH target, e.g. "user@mediaserver" or "user@192.168.1.10"

Optional env vars (override defaults)
--------------------------------------
SSH_USER    Overrides the username portion of REMOTE (default: parsed from REMOTE)
SSH_HOST    Overrides the hostname portion of REMOTE (default: parsed from REMOTE)
"""

import os
import sys

# Load .env from the repo root if python-dotenv is available
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass  # python-dotenv is optional; rely on real environment variables

# ── Resolve connection target ──────────────────────────────────────────────────

REMOTE = os.environ.get("REMOTE", "")
if not REMOTE:
    print(
        "ERROR: REMOTE is not set.\n"
        "Set it in your .env file or export it before running pyinfra.\n"
        "Example: REMOTE=user@mediaserver",
        file=sys.stderr,
    )
    sys.exit(1)

# Parse user@host — allow SSH_USER / SSH_HOST to override individually
if "@" in REMOTE:
    _default_user, _default_host = REMOTE.split("@", 1)
else:
    _default_user, _default_host = None, REMOTE

ssh_user = os.environ.get("SSH_USER", _default_user)
ssh_host = os.environ.get("SSH_HOST", _default_host)

# ── Inventory ──────────────────────────────────────────────────────────────────

# A single host — the media server.
# `_sudo=True` because deploying quadlets and systemd units requires root.
hosts = [
    (
        ssh_host,
        {
            "ssh_user": ssh_user,
            "_sudo": True,
        },
    )
]
