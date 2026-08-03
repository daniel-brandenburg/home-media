"""
tasks/config.py — upload app config files to the remote server

Uploads:
  - config/dashy/conf.yml          → REMOTE_DIR/dashy/conf.yml
      (SERVER_IP placeholder is expanded in Python before upload)
  - config/qbittorrent/custom-cont-init.d/99-webui-proxy.sh
      → REMOTE_DIR/qbittorrent/custom-cont-init.d/99-webui-proxy.sh
  - config/qbittorrent/qBittorrent.conf
      → REMOTE_DIR/qbittorrent/qBittorrent/qBittorrent.conf
      WebUI username and PBKDF2 password hash are injected at deploy time
      from QBIT_USER / QBIT_PASS in .env (plaintext password never sent).
      qbittorrent.service is stopped before upload; systemd.py starts it
      after daemon-reload so the conf is not overwritten on shutdown.
  - config/squid/squid.conf          → REMOTE_DIR/squid/squid.conf
      (the matching rootless quadlet config/squid/squid.container is deployed
      by devcontainers.py into the devcontainer user's ~/.config/containers/systemd/)
  - .env (root)                    → REMOTE_DIR/.env
      (quadlet EnvironmentFile= reads this at container start)
"""

import hashlib
import base64
import io
import os

from pyinfra.operations import files, server, systemd


def _qbit_pbkdf2_hash(password: str) -> str:
    """
    Generate a qBittorrent-compatible PBKDF2-SHA512 password hash.

    qBittorrent stores passwords as:
        @ByteArray(<base64_salt>:<base64_dk>)
    using PBKDF2-HMAC-SHA512, 100 000 iterations, 16-byte salt, 64-byte key.
    The hash is computed locally so the plaintext password is never written
    to any file that is sent to the server.
    """
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, 100_000, dklen=64)
    encoded = f"{base64.b64encode(salt).decode()}:{base64.b64encode(dk).decode()}"
    return f"@ByteArray({encoded})"

# ── Resolve paths ──────────────────────────────────────────────────────────────
_repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
_config_dir = os.path.join(_repo_root, "config")

REMOTE_DIR = os.environ.get("REMOTE_DIR", "/srv/containers")
REMOTE = os.environ.get("REMOTE", "")

# ── dashy conf.yml (REMOTE substitution done in Python) ────────────────────
_dashy_src = os.path.join(_config_dir, "dashy", "conf.yml")
with open(_dashy_src) as _f:
    _dashy_content = _f.read()

if REMOTE:
    _dashy_content = _dashy_content.replace("${REMOTE}", REMOTE)

files.put(
    name="Upload dashy conf.yml (REMOTE expanded)",
    src=io.StringIO(_dashy_content),
    dest=f"{REMOTE_DIR}/dashy/conf.yml",
    mode="640",
)

# ── qBittorrent WebUI proxy init script ───────────────────────────────────────
files.put(
    name="Upload qBittorrent WebUI proxy init script",
    src=os.path.join(
        _config_dir, "qbittorrent", "custom-cont-init.d", "99-webui-proxy.sh"
    ),
    dest=f"{REMOTE_DIR}/qbittorrent/custom-cont-init.d/99-webui-proxy.sh",
    mode="755",
)

# ── Squid egress proxy config ──────────────────────────────────────────────────
files.put(
    name="Upload Squid egress proxy config",
    src=os.path.join(_config_dir, "squid", "squid.conf"),
    dest=f"{REMOTE_DIR}/squid/squid.conf",
    mode="644",
)

# SELinux is enforcing on this host. The Squid quadlet (deploy/tasks/devcontainers.py)
# runs rootless as the devcontainer user, which lacks CAP_MAC_ADMIN and so can't
# relabel this bind mount itself (that's why its Volume= line has no :Z — attempting
# it there fails with "lsetxattr ... operation not permitted"). Root has the
# capability, and this task already runs as root (_sudo=True in inventory.py), so
# label it here instead.
#
# Explicit "-l s0" (no MCS categories) matters: without :Z, Podman still hands
# the container process its own random per-run MCS category pair, but never
# touches the file's label to match it (that pairing-up is exactly what :Z
# would normally coordinate). A file labeled with SOME fixed category pair
# (e.g. left over from a prior manual chcon) will only satisfy MCS dominance
# if it happens to match that run's random pair — which it won't. A bare "s0"
# (empty category set) is trivially dominated by any category set, so any
# container_t process can read it regardless of its own random categories.
server.shell(
    name="Label Squid config container_file_t:s0 for SELinux (rootless quadlet can't self-relabel)",
    commands=[f"chcon -l s0 -t container_file_t {REMOTE_DIR}/squid/squid.conf"],
)

# ── qBittorrent main config ───────────────────────────────────────────────────
# qBittorrent writes its config on shutdown and will overwrite any changes made
# while it is running — stop it first, upload, then restart.
#
# The WebUI username and PBKDF2 password hash are injected here at deploy time
# from QBIT_USER / QBIT_PASS so the plaintext password is never written to any
# file uploaded to the server.
_qbit_user = os.environ.get("QBIT_USER", "")
_qbit_pass = os.environ.get("QBIT_PASS", "")

_qbit_conf_src = os.path.join(_config_dir, "qbittorrent", "qBittorrent.conf")
with open(_qbit_conf_src) as _f:
    _qbit_conf = _f.read()

if _qbit_user and _qbit_pass:
    _qbit_hash = _qbit_pbkdf2_hash(_qbit_pass)

    # Remove any existing Username / Password lines (however they were written)
    import re as _re
    _qbit_conf = _re.sub(r"^WebUI\\Username=.*\n?", "", _qbit_conf, flags=_re.MULTILINE)
    _qbit_conf = _re.sub(r"^WebUI\\Password_PBKDF2=.*\n?", "", _qbit_conf, flags=_re.MULTILINE)

    # Insert the credentials immediately after the [Preferences] section header
    _creds = f'WebUI\\Username={_qbit_user}\nWebUI\\Password_PBKDF2="{_qbit_hash}"\n'
    if "[Preferences]" in _qbit_conf:
        _qbit_conf = _qbit_conf.replace("[Preferences]\n", f"[Preferences]\n{_creds}", 1)
    else:
        _qbit_conf += f"\n[Preferences]\n{_creds}"
else:
    print(
        "WARNING: QBIT_USER or QBIT_PASS not set — uploading qBittorrent.conf without credentials.\n"
        "Set them in .env to have the password pre-seeded on deploy."
    )

systemd.service(
    name="Stop qbittorrent before config upload",
    service="qbittorrent.service",
    running=False,
)

files.put(
    name="Upload qBittorrent.conf (credentials + WebUI settings)",
    src=io.StringIO(_qbit_conf),
    dest=f"{REMOTE_DIR}/qbittorrent/qBittorrent/qBittorrent.conf",
    mode="600",
)

# Do NOT start qbittorrent here — systemd.py starts home-media.target which
# brings up all containers.  Starting it here would cause qBittorrent to write
# its config on shutdown and potentially overwrite the credentials we just uploaded.

# ── .env (runtime environment for quadlet EnvironmentFile=) ───────────────────
_env_file = os.path.join(_repo_root, ".env")
if os.path.exists(_env_file):
    files.put(
        name="Upload .env (quadlet runtime environment)",
        src=_env_file,
        dest=f"{REMOTE_DIR}/.env",
        mode="600",
    )
else:
    print(
        f"WARNING: .env not found at {_env_file} — skipping upload.\n"
        "Quadlets will use whatever .env already exists on the server."
    )
