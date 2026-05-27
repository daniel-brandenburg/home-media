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

    _env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(_env_path)
except Exception as e:
    print(f"Warning: failed to load .env: {e}", file=sys.stderr)

# ── Resolve connection target ──────────────────────────────────────────────────

ssh_user = os.environ.get("SSH_USER", "db")
ssh_host = os.environ.get("REMOTE", "192.168.0.50")

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
