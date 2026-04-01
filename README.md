# home-media

A self-hosted home media server stack managed as infrastructure-as-code.
No application code, no package manager, no test framework — just config files, Podman Compose, Caddy, and systemd.

## Stack

| Service          | Image                                          | Port   | Local URL             |
|------------------|------------------------------------------------|--------|-----------------------|
| Caddy            | `caddy:latest`                                 | 80/443 | (reverse proxy)       |
| Dashy            | `ghcr.io/lissy93/dashy:latest`                 | 8081   | `dash.home`           |
| Jellyfin         | `lscr.io/linuxserver/jellyfin:latest`          | 8096   | `jellyfin.home`       |
| Audiobookshelf   | `ghcr.io/advplyr/audiobookshelf:latest`        | 13378  | `audiobooks.home`     |
| Sonarr           | `lscr.io/linuxserver/sonarr:latest`            | 8989   | `sonarr.home`         |
| Radarr           | `lscr.io/linuxserver/radarr:latest`            | 7878   | `radarr.home`         |
| Listenarr        | `ghcr.io/listenarrs/listenarr:canary`          | 4545   | `listenarr.home`      |
| qBittorrent      | `lscr.io/linuxserver/qbittorrent:latest`       | 8080   | `qbit.home`           |
| Prowlarr         | `lscr.io/linuxserver/prowlarr:latest`          | 9696   | `prowlarr.home`       |
| FlareSolverr     | `ghcr.io/flaresolverr/flaresolverr:latest`     | 8191   | (internal only)       |
| Bitmagnet        | `ghcr.io/bitmagnet-io/bitmagnet:latest`        | 3333   | `bitmagnet.home`      |
| Bitmagnet DB     | `postgres:16-alpine`                           | —      | (internal only)       |

All services share the `media_net` bridge network and discover each other by container name.
Local `.home` DNS names are resolved by your LAN DNS (for example Pi-hole or router DNS overrides).

## Design Goals

- Keep only the currently-used ARR apps: Prowlarr, Sonarr, Radarr, Listenarr
- Keep a dashboard-first UX with Dashy and stable `.home` hostnames
- Follow Servarr folder strategy: one filesystem for `/data/downloads`, `/data/TV`, and `/data/Movies` to preserve hardlinks
- Keep setup idempotent so you can redeploy and re-run wiring scripts safely

## Repository Layout

```
containers/
  compose.yaml                          # Full service definitions (Podman Compose)
  .env.example                          # Environment variable template — copy to .env
  deploy.sh                             # rsync config files to the remote server
  setup-arr.sh                          # One-time API wiring for *arr + qBittorrent
  caddy/Caddyfile                       # Reverse proxy virtual hosts
  dashy/conf.yml                        # Dashboard layout and service tiles
  qbittorrent/
    custom-cont-init.d/
      99-webui-proxy.sh                 # qBittorrent WebUI proxy settings patch
systemd/
  home-media.service                    # systemd unit: start/stop the stack
  srv-media.mount                       # systemd unit: mount external drive
  srv-media.automount                   # systemd unit: lazy automount
packages.txt                            # Host system packages required (e.g. rsync)
```

## Prerequisites

**Developer machine** (where you edit and deploy from):
- `rsync`
- `envsubst` (usually part of `gettext`)
- SSH access to the server

**Server** (OpenSUSE MicroOS or similar):
- Podman + `podman-compose`
- `firewalld`
- An exFAT drive mounted at `/srv/media`

Install the required host packages listed in `packages.txt`.

## First-Time Setup

### 1. Configure your environment

```bash
cd containers
cp .env.example .env
$EDITOR .env
```

Fill in every value — at minimum: `REMOTE`, `SERVER_IP`, `PUID`/`PGID`, `TZ`, `MEDIA_UUID`, `QBIT_USER`, `QBIT_PASS`, and `POSTGRES_PASSWORD`. Leave the API key fields empty for now.

### 2. Install systemd units on the server

Copy the systemd units to the server and enable them:

```bash
scp systemd/* user@mediaserver:/etc/systemd/system/
ssh user@mediaserver 'systemctl daemon-reload && systemctl enable --now srv-media.automount home-media'
```

### 3. Deploy config files

From inside the `containers/` directory:

```bash
./deploy.sh
```

This rsyncs `compose.yaml`, `Caddyfile`, `dashy/conf.yml`, and the qBittorrent init scripts to the server.

### 4. Start the stack

```bash
ssh user@mediaserver 'podman compose -f /srv/containers/compose.yaml up -d'
```

### 5. Wire the services together

After all containers are healthy, run the setup script once from the developer machine:

```bash
./setup-arr.sh
```

This script:
- Logs in to qBittorrent and sets a persistent password and download categories
- Configures Sonarr and Radarr with root folders, hardlink import settings, and qBittorrent as a download client
- Registers Sonarr and Radarr in Prowlarr
- Registers FlareSolverr in Prowlarr as an indexer proxy
- Configures Listenarr with qBittorrent and the audiobooks root folder

It is idempotent and safe to re-run.

### 6. Add indexers

Open `http://prowlarr.home` → **Indexers → Add Indexer**. Prowlarr will automatically sync added indexers to Sonarr and Radarr.

### 7. Open firewall ports (if needed)

On the server, open any port that needs to be reachable outside the LAN:

```bash
sudo firewall-cmd --permanent --add-port=<PORT>/tcp
sudo firewall-cmd --reload
```

## Day-to-Day Operations

### Deploy a config change

```bash
# From containers/
./deploy.sh
ssh user@mediaserver 'podman restart caddy'   # or whichever service changed
```

### Stack management (on the server)

```bash
podman compose -f /srv/containers/compose.yaml up -d   # start
podman compose -f /srv/containers/compose.yaml down    # stop
podman logs -f sonarr                                   # tail logs
podman restart caddy                                    # restart one service
```

### systemd

```bash
systemctl start home-media
systemctl stop home-media
systemctl status home-media
```

## Design Notes

**Hardlinks** — Sonarr and Radarr import files using hardlinks instead of copies. This requires the downloads directory and the media library to live on the same filesystem. Both `/data/downloads` and `/data/TV` (or `/data/Movies`) inside the containers resolve to `/srv/media` on the host.

**SELinux** — All volume mounts on the host filesystem use the `:Z` flag so Podman relabels them for container access. Mounts on the exFAT media drive intentionally omit `:Z` because exFAT does not support SELinux labels.

**DNS** — your local DNS resolver maps `*.home` names on the LAN. All inter-container traffic uses container names as hostnames (e.g. `http://sonarr:8989`).

**Prowlarr firewall** — Prowlarr's port (9696) may be blocked externally. `setup-arr.sh` routes Prowlarr API calls through SSH to avoid this.

## Security

- Never commit `.env` — it is gitignored.
- API keys are auto-fetched from the server by `setup-arr.sh` on first run if left blank in `.env`.
- The `containers/` directory on the server should be readable only by the service user (`PUID`/`PGID`).
