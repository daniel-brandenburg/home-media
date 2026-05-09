# home-media

A self-hosted home media server stack managed as infrastructure-as-code.
No application code, no package manager, no test framework — just config files,
Podman quadlets, Caddy, and systemd.  Deployment is automated with **pyinfra**.

## Stack

| Service          | Image                                              | Port   | Local URL             |
|------------------|----------------------------------------------------|--------|-----------------------|
| Caddy            | `caddy:latest`                                     | 80/443 | (reverse proxy)       |
| Dashy            | `ghcr.io/lissy93/dashy:latest`                     | 8081   | `dash.home`           |
| Jellyfin         | `lscr.io/linuxserver/jellyfin:latest`              | 8096   | `jellyfin.home`       |
| Audiobookshelf   | `ghcr.io/advplyr/audiobookshelf:latest`            | 13378  | `audiobooks.home`     |
| Sonarr           | `lscr.io/linuxserver/sonarr:latest`                | 8989   | `sonarr.home`         |
| Radarr           | `lscr.io/linuxserver/radarr:latest`                | 7878   | `radarr.home`         |
| Listenarr        | `ghcr.io/listenarrs/listenarr:canary`              | 4545   | `listenarr.home`      |
| qBittorrent      | `lscr.io/linuxserver/qbittorrent:latest`           | 8080   | `qbit.home`           |
| Prowlarr         | `lscr.io/linuxserver/prowlarr:latest`              | 9696   | `prowlarr.home`       |
| FlareSolverr     | `ghcr.io/flaresolverr/flaresolverr:latest`         | 8191   | (internal only)       |
| Calibre-Web      | `crocodilestick/calibre-web-automated:latest`      | 8083   | `ebooks.home`         |
| Shelfmark        | `ghcr.io/calibrain/shelfmark-lite:latest`          | 8084   | `shelfmark.home`      |
| Ebook Handoff    | `alpine:3.20`                                      | —      | (internal only)       |

All services share the `media_net` bridge network and discover each other by container name.
Local `.home` DNS names are resolved by your LAN DNS (e.g. Pi-hole or router DNS overrides).

## Repository Layout

```
.env.example                          # Environment variable template — copy to .env
packages.txt                          # Host system packages to install on the server
config/
  caddy/Caddyfile                     # Reverse proxy virtual hosts
  dashy/conf.yml                      # Dashboard layout (${SERVER_IP} placeholder)
  qbittorrent/
    custom-cont-init.d/
      99-webui-proxy.sh               # qBittorrent WebUI proxy patch
quadlets/                             # Podman quadlet unit files (*.container, *.network)
systemd/
  home-media.target                   # Groups all container services into one target
  srv-media.mount                     # Mounts the external exFAT drive at /srv/media
  srv-media.automount                 # Lazy automount wrapper
deploy/
  inventory.py                        # pyinfra inventory — reads REMOTE from .env
  deploy.py                           # Main deploy entry point
  tasks/
    system.py                         # Install packages, create /srv/containers dirs
    config.py                         # Upload Caddyfile, dashy conf.yml, qbit init, .env
    quadlets.py                       # Sync quadlets/ to /etc/containers/systemd/
    systemd.py                        # Install systemd units, daemon-reload, enable services
    firewall.py                       # Open required ports in firewalld
    arr_setup.py                      # One-time API wiring (*arr + qBittorrent)
```

## Prerequisites

**Developer machine** (where you edit and deploy from):
- Python 3.11+
- `pyinfra` (`pip install pyinfra` or `uv tool install pyinfra`)
- `python-dotenv` (optional — `pip install python-dotenv` — enables auto-loading `.env`)
- SSH access to the server

**Server** (OpenSUSE MicroOS or similar):
- Podman with quadlet support (Podman ≥ 4.4)
- `firewalld`
- An exFAT drive that will be mounted at `/srv/media`

## First-Time Setup

### 1. Configure your environment

```bash
cp .env.example .env
$EDITOR .env
```

Fill in at minimum: `REMOTE`, `SERVER_IP`, `PUID`/`PGID`, `TZ`, `MEDIA_UUID`, `QBIT_USER`,
`QBIT_PASS`.  Leave API key fields (`SONARR_API`, etc.) empty for now — they are auto-fetched.

### 2. Full deploy

From the **repo root**:

```bash
pyinfra deploy/inventory.py deploy/deploy.py
```

This will (in order):
1. Install required host packages
2. Create `/srv/containers/<service>` directories
3. Upload app config files (`Caddyfile`, `dashy/conf.yml`, `.env`, etc.)
4. Sync quadlet unit files to `/etc/containers/systemd/`
5. Install systemd units, daemon-reload, and enable/start all services
6. Open required firewall ports

### 3. Wire the services together (one-time)

After all containers are healthy, run the arr setup task:

```bash
pyinfra deploy/inventory.py deploy/tasks/arr_setup.py
```

This configures:
- qBittorrent password, save paths, and download categories
- Sonarr and Radarr: root folders, hardlink import settings, qBittorrent download client
- Prowlarr: Sonarr + Radarr app registrations, FlareSolverr indexer proxy
- Listenarr: qBittorrent download client and audiobooks root folder

It is idempotent and safe to re-run.

### 4. Add indexers

Open `http://prowlarr.home` → **Indexers → Add Indexer**.  Prowlarr automatically syncs
added indexers to Sonarr and Radarr.

## Day-to-Day Operations

### Deploy a config change

```bash
# Push only updated config files
pyinfra deploy/inventory.py deploy/tasks/config.py

# Push only updated quadlets (then restart affected services on the server)
pyinfra deploy/inventory.py deploy/tasks/quadlets.py
```

### Stack management (on the server)

```bash
# Start / stop the whole stack
systemctl start home-media.target
systemctl stop home-media.target

# Tail logs for a specific service
journalctl -u sonarr.service -f

# Restart a single service after a config change
systemctl restart caddy.service
```

## Design Notes

**Quadlets** — Each container is defined as a Podman quadlet unit file in `quadlets/`.
Systemd's generator converts them to `.service` units automatically on `daemon-reload`.
No `docker-compose.yml` or `podman-compose` is needed.

**Hardlinks** — Sonarr and Radarr import using hardlinks instead of copies.  This requires
`/data/downloads`, `/data/TV`, and `/data/Movies` inside the containers to all resolve to
paths on the **same filesystem** (`/srv/media` on the host).

**SELinux** — All volume mounts on the host filesystem use `:Z` so Podman relabels them.
Mounts on the exFAT media drive intentionally omit `:Z` (exFAT has no SELinux label support).

**Prowlarr firewall** — Port 9696 may be blocked externally.  `arr_setup.py` calls the
Prowlarr API via `localhost` through the SSH connection pyinfra already holds — no second hop.

## Security

- Never commit `.env` — it is gitignored.
- API keys are auto-fetched from the server's config files on first arr_setup run if left blank.
- `/srv/containers/.env` on the server should be readable only by the service user (`PUID`/`PGID`).
