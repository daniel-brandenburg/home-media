# home-media

A self-hosted home media server stack managed as infrastructure-as-code.
No application code, no package manager, no test framework — just config files,
Podman quadlets, Caddy, and systemd.  Deployment is automated with **pyinfra**.

## Stack

| Service          | systemd unit                          | Image                                              | Port   | Local URL             |
|------------------|---------------------------------------|----------------------------------------------------|--------|-----------------------|
| Caddy            | `caddy.service`                       | `caddy:latest`                                     | 80/443 | (reverse proxy)       |
| Dashy            | `dashy.service`                       | `ghcr.io/lissy93/dashy:latest`                     | 8081   | `dash.home`           |
| Jellyfin         | `jellyfin.service`                    | `lscr.io/linuxserver/jellyfin:latest`              | 8096   | `jellyfin.home`       |
| Audiobookshelf   | `audiobookshelf.service`              | `ghcr.io/advplyr/audiobookshelf:latest`            | 13378  | `audiobooks.home`     |
| Sonarr           | `sonarr.service`                      | `lscr.io/linuxserver/sonarr:latest`                | 8989   | `sonarr.home`         |
| Radarr           | `radarr.service`                      | `lscr.io/linuxserver/radarr:latest`                | 7878   | `radarr.home`         |
| Listenarr        | `listenarr.service`                   | `ghcr.io/listenarrs/listenarr:canary`              | 4545   | `listenarr.home`      |
| qBittorrent      | `qbittorrent.service`                 | `lscr.io/linuxserver/qbittorrent:latest`           | 8080   | `qbit.home`           |
| Prowlarr         | `prowlarr.service`                    | `lscr.io/linuxserver/prowlarr:latest`              | 9696   | `prowlarr.home`       |
| FlareSolverr     | `flaresolverr.service`                | `ghcr.io/flaresolverr/flaresolverr:latest`         | 8191   | (internal only)       |
| Calibre-Web      | `calibre-web-automated.service`       | `crocodilestick/calibre-web-automated:latest`      | 8083   | `ebooks.home`         |
| Shelfmark        | `shelfmark.service`                   | `ghcr.io/calibrain/shelfmark-lite:latest`          | 8084   | `shelfmark.home`      |
| Ebook Handoff    | `ebook-handoff.service`               | `alpine:3.20`                                      | —      | (internal only)       |

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
- [uv](https://docs.astral.sh/uv/) — manages the Python environment and dependencies
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
uv run pyinfra deploy/inventory.py deploy/deploy.py
```

`uv run` automatically creates a virtual environment and installs all dependencies
declared in `pyproject.toml` (including `pyinfra` and `python-dotenv`) before running.

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
uv run pyinfra deploy/inventory.py deploy/tasks/arr_setup.py
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
uv run pyinfra deploy/inventory.py deploy/tasks/config.py

# Push only updated quadlets (then restart affected services on the server)
uv run pyinfra deploy/inventory.py deploy/tasks/quadlets.py
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

### Pull a media file off the server

Container paths (`/data/TV`, `/data/Movies`, `/data/downloads`) map to `/srv/media/...`
on the host, so use the **host** path when copying over SSH:

```bash
# Copy one episode to your local ~/Downloads
rsync -a --info=progress2 \
  "db@192.168.0.50:/srv/media/TV/Game Changer/Season 8/Game Changer - S08E07 - Earwigs WEBDL-1080p.mkv" \
  ~/Downloads/

# Copy a whole season
rsync -a --info=progress2 \
  "db@192.168.0.50:/srv/media/TV/Game Changer/Season 8/" \
  ~/Downloads/"Game Changer S08"/
```

Quote the remote path — media names contain spaces.  `rsync` resumes safely on re-run;
use `scp` only if `rsync` is not installed on the server.

### Agent devcontainers

Per-project sandboxes for running Claude Code / Kimi Code on the server live in `devcontainers/`
(see "Coding Agent Sandbox" in [AGENTS.md](AGENTS.md)). Deploy the templates with
`uv run pyinfra deploy/inventory.py deploy/tasks/devcontainers.py`. To run the ThirdPlacePages
sandbox, follow [devcontainers/thirdplacepages/README.md](devcontainers/thirdplacepages/README.md).

### When something is broken

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — diagnostic procedure, access gotchas
(rootful containers, unreadable journal), and the incident log.

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
