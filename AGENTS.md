# AGENTS.md — home-media

This repository is a **self-hosted home media server** infrastructure-as-code project.
It contains no application code, no package manager, and no test framework.
The stack is managed via Podman quadlets, Caddy reverse proxy, and systemd.
Deployment is automated with **pyinfra**.

---

## Agent Rules

- **Never run commands on the remote server.** Do not `ssh` into the remote host or any other
  host. Do not execute `podman`, `systemctl`, or any other command remotely. All remote operations
  are the responsibility of the human operator.
- **Never deploy changes without explicit user approval.** Do not run `pyinfra`, do not invoke
  `rsync` to push files, and do not suggest or initiate a deployment unless the user has explicitly
  asked you to deploy in that same conversation turn.

---

## Repository Layout

```
.env.example                          # Environment variable template — copy to .env
packages.txt                          # Host system packages required (e.g. rsync)
config/
  caddy/Caddyfile                     # Reverse proxy virtual hosts
  dashy/conf.yml                      # Dashboard layout and service tiles (${SERVER_IP} placeholder)
  qbittorrent/
    custom-cont-init.d/
      99-webui-proxy.sh               # qBittorrent WebUI proxy settings patch
quadlets/                             # Podman quadlet unit files (*.container, *.network)
systemd/
  home-media.target                   # systemd target: groups all container services
  srv-media.mount                     # systemd unit: mount external drive
  srv-media.automount                 # systemd unit: lazy automount
deploy/
  inventory.py                        # pyinfra inventory (reads REMOTE from env/.env)
  deploy.py                           # Main deploy entry point — includes all tasks
  tasks/
    system.py                         # Install packages, create /srv/containers dirs
    config.py                         # Upload Caddyfile, dashy conf.yml, qbit init, .env
    quadlets.py                       # Upload quadlet files to /etc/containers/systemd/
    systemd.py                        # Upload systemd units, daemon-reload, enable services
    firewall.py                       # Open required ports in firewalld
    arr_setup.py                      # One-time API wiring (*arr + qBittorrent) — run separately
```

---

## Operational Commands

### Configure (developer machine)

```bash
cp .env.example .env
$EDITOR .env   # fill in REMOTE, SERVER_IP, PUID, PGID, TZ, MEDIA_UUID, QBIT_*, POSTGRES_PASSWORD
```

### Deploy (from developer machine, run from repo root)

```bash
# Full deploy: packages + config + quadlets + systemd units + firewall
pyinfra deploy/inventory.py deploy/deploy.py

# Deploy only a specific task (e.g. after editing config files):
pyinfra deploy/inventory.py deploy/tasks/config.py
pyinfra deploy/inventory.py deploy/tasks/quadlets.py
pyinfra deploy/inventory.py deploy/tasks/firewall.py
```

### One-time arr wiring (run after the stack is up for the first time)

```bash
# Fill in API keys in .env first (or leave blank — they will be auto-fetched from the server)
pyinfra deploy/inventory.py deploy/tasks/arr_setup.py
```

### Stack management (on the remote server: `ssh user@mediaserver`)

```bash
# Start all containers via the grouping target
systemctl start home-media.target

# Stop all containers
systemctl stop home-media.target

# View logs for a specific service
journalctl -u sonarr.service -f

# Restart a single container service
systemctl restart caddy.service
```

### Firewall (on the remote server — MicroOS uses firewalld)

Handled automatically by `deploy/tasks/firewall.py`.  To open an additional port manually:

```bash
sudo firewall-cmd --permanent --add-port=<PORT>/tcp
sudo firewall-cmd --reload
```

### No build, lint, or test commands

There is no compiled code, no test framework, and no linter. Validation is manual.

---

## Services and Ports

| Service      | Image                                  | Internal Port | `.home` URL           |
|--------------|----------------------------------------|---------------|-----------------------|
| Caddy        | `caddy:latest`                         | 80, 443       | (reverse proxy)       |
| Dashy        | `ghcr.io/lissy93/dashy:latest`         | 8081          | `dash.home`           |
| Prowlarr     | `lscr.io/linuxserver/prowlarr:latest`  | 9696          | `prowlarr.home`       |
| FlareSolverr | `ghcr.io/flaresolverr/flaresolverr:latest` | 8191      | (internal only)       |
| Jellyfin     | `lscr.io/linuxserver/jellyfin:latest`  | 8096          | `jellyfin.home`       |
| Audiobookshelf | `ghcr.io/advplyr/audiobookshelf:latest` | 13378       | `audiobooks.home`     |
| qBittorrent  | `lscr.io/linuxserver/qbittorrent:latest` | 8080        | `qbit.home`           |
| Sonarr       | `lscr.io/linuxserver/sonarr:latest`    | 8989          | `sonarr.home`         |
| Radarr       | `lscr.io/linuxserver/radarr:latest`    | 7878          | `radarr.home`         |
| Calibre-Web  | `crocodilestick/calibre-web-automated:latest` | 8083   | `ebooks.home`         |
| Shelfmark    | `ghcr.io/calibrain/shelfmark-lite:latest` | 8084       | `shelfmark.home`      |
| Ebook Handoff | `alpine:3.20`                         | (none)        | (internal only)       |

All containers share the `media_net` bridge network and discover each other by container name
(e.g. `http://sonarr:8989`, `reverse_proxy jellyfin:8096`).

---

## Python / pyinfra Style Guide

All files under `deploy/` follow these conventions:

### File naming

- Task files: `snake_case.py`
- Entry points: `inventory.py`, `deploy.py`

### Environment variables

- Required vars are validated at import time with a clear error message and `sys.exit(1)`.
- `python-dotenv` is optional — if installed, the root `.env` is auto-loaded.
  If not installed, the real environment is used directly.
- All env var reads use `os.environ.get("VAR", default)` or `os.environ["VAR"]`.

### pyinfra operations

- Prefer `files.put()` for uploading files over raw shell commands.
- Use `systemd.service()` for enabling/starting units rather than `server.shell("systemctl ...")`.
- Use `server.shell()` for tasks that have no native pyinfra operation (firewall-cmd, curl API calls).
- Each `server.shell()` call sets `set -euo pipefail` at the top of its script.
- All API-touching shell blocks check for `.id` in the response and print a clear error on failure.

### Idempotency

- Always GET-then-check before POST (never blindly POST and ignore duplicates).
- `firewall-cmd --add-port` is already idempotent; always add `|| true` to suppress "already open" errors.

---

## Infrastructure Conventions

### Volume mounts and SELinux

- Add `:Z` to volume mounts on SELinux-enabled hosts so Podman relabels files for container access.
- **Do NOT add `:Z`** for volumes on exFAT filesystems — exFAT does not support SELinux labels.
  Comment the reason inline in the quadlet file.

### LinuxServer.io images

All media service containers use `lscr.io/linuxserver/` images. Always set:
```
Environment=PUID=1000
Environment=PGID=1000
```
or use `EnvironmentFile=/srv/containers/.env` in the quadlet.

### Hardlinks for media import

Sonarr/Radarr use hardlinks (not copies) when importing completed downloads. This requires the
downloads directory and the media directory to be on the **same filesystem**.

### Prowlarr firewall

Prowlarr (port 9696) may be firewalled externally. `arr_setup.py` calls the Prowlarr API via
`localhost` inside the `server.shell()` SSH session — no extra SSH hop needed.
