# AGENTS.md — home-media

This repository is a **self-hosted home media server** infrastructure-as-code project.
It contains no application code, no package manager, and no test framework.
The stack is managed via Docker/Podman Compose, Caddy reverse proxy, and systemd.

---

## Agent Rules

- **Never run commands on the remote server.** Do not `ssh` into the remote host or any other
  host. Do not execute `podman`, `systemctl`, or any other command remotely. All remote operations
  are the responsibility of the human operator.
- **Never deploy changes without explicit user approval.** Do not run `deploy.sh`, do not invoke
  `rsync` to push files, and do not suggest or initiate a deployment unless the user has explicitly
  asked you to deploy in that same conversation turn.

---

## Repository Layout

```
containers/
  compose.yaml                          # Full service definitions (Podman Compose)
  deploy.sh                             # rsync config files to remote server
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

---

## Operational Commands

### Deploy (from developer machine, run inside `containers/`)

```bash
# Sync config files to the remote server via rsync
./containers/deploy.sh

# After deploying, start or restart the stack on the server
ssh user@mediaserver 'podman compose -f /srv/containers/compose.yaml up -d'
```

### Stack management (on the remote server: `ssh user@mediaserver`)

```bash
# Start all containers
podman compose -f /srv/containers/compose.yaml up -d

# Stop all containers
podman compose -f /srv/containers/compose.yaml down

# View logs for a specific service
podman logs -f <service>        # e.g. podman logs -f sonarr

# Restart a single service
podman restart <service>        # e.g. podman restart caddy
```

### systemd (on the remote server)

```bash
systemctl start home-media
systemctl stop home-media
systemctl enable home-media
systemctl status home-media
```

### One-time setup (run after stack first starts)

```bash
# Configures qBittorrent, Sonarr, Radarr, and Prowlarr via their REST APIs.
# Safe to re-run — all API calls are idempotent.
./containers/setup-arr.sh
```

### Firewall (on the remote server — MicroOS uses firewalld)

Whenever a new host port is exposed, open it in the firewall on the server:

```bash
sudo firewall-cmd --permanent --add-port=<PORT>/tcp
sudo firewall-cmd --reload
```

For example, adding Listenarr (port 4545):

```bash
sudo firewall-cmd --permanent --add-port=4545/tcp
sudo firewall-cmd --reload
```

### No build, lint, or test commands

There is no compiled code, no test framework, and no linter. Validation is manual.

---

## Services and Ports

| Service      | Image                                  | Internal Port | `.home` URL           |
|--------------|----------------------------------------|---------------|-----------------------|
| Caddy        | `caddy:latest`                         | 80, 443       | (reverse proxy)       |
| Pi-hole      | `pihole/pihole:2024.07.0`              | 8053          | `pihole.home`         |
| Dashy        | `ghcr.io/lissy93/dashy:latest`         | 8081          | `dash.home`           |
| Prowlarr     | `lscr.io/linuxserver/prowlarr:latest`  | 9696          | `prowlarr.home`       |
| FlareSolverr | `ghcr.io/flaresolverr/flaresolverr:latest` | 8191      | (internal only)       |
| Jellyfin     | `lscr.io/linuxserver/jellyfin:latest`  | 8096          | `jellyfin.home`       |
| Audiobookshelf | `ghcr.io/advplyr/audiobookshelf:latest` | 13378       | `audiobooks.home`     |
| qBittorrent  | `lscr.io/linuxserver/qbittorrent:latest` | 8080        | `qbit.home`           |
| Sonarr       | `lscr.io/linuxserver/sonarr:latest`    | 8989          | `sonarr.home`         |
| Radarr       | `lscr.io/linuxserver/radarr:latest`    | 7878          | `radarr.home`         |
| Listenarr    | `ghcr.io/listenarrs/listenarr:canary`  | 4545          | `listenarr.home`      |
| Bitmagnet    | `ghcr.io/bitmagnet-io/bitmagnet:latest` | 3333         | `bitmagnet.home`      |
| Bitmagnet DB | `postgres:16-alpine`                   | (internal)    | (internal only)       |

All containers share the `media_net` bridge network and discover each other by container name
(e.g. `http://sonarr:8989`, `reverse_proxy jellyfin:8096`).

---

## Bash Script Style Guide

All `.sh` files in this repo follow these conventions:

### Shebang and strict mode

```bash
#!/usr/bin/env bash
set -euo pipefail
```

- Always use `#!/usr/bin/env bash` (not `/bin/bash`) for portability.
- Always set strict mode at the top — no exceptions.
- `99-webui-proxy.sh` uses `#!/bin/bash` since it runs inside a container where `env` is not needed.

### Variables

- **Global constants / environment config**: `SCREAMING_SNAKE_CASE`
  ```bash
  REMOTE="user@mediaserver"
  SONARR_URL="http://${SERVER_IP}:8989"
  ```
- **Local function variables**: `snake_case` with the `local` keyword
  ```bash
  local method="$1" path="$2" body="${3:-}"
  ```
- **Temporary variables**: `SCREAMING_SNAKE_CASE`
  ```bash
  EXISTING_ROOTS=$(sonarr GET "rootfolder")
  ```

### Functions

- Named functions use `snake_case`
  ```bash
  qbit_login() { ... }
  prowlarr_ssh() { ... }
  update_setting() { ... }
  ```
- Short single-word helper functions are acceptable for color output and logging:
  ```bash
  red()   { printf '\033[31m%s\033[0m\n' "$*"; }
  green() { printf '\033[32m%s\033[0m\n' "$*"; }
  blue()  { printf '\033[34m%s\033[0m\n' "$*"; }
  step()  { echo; blue "==> $*"; }
  ```

### Dependency guards

Check for required external tools at the top of any script that calls them:

```bash
require() {
  command -v "$1" &>/dev/null || { red "Missing required tool: $1"; exit 1; }
}
require curl
require jq
require ssh
```

### Error handling

1. **`set -euo pipefail`** — script aborts on unhandled errors, unset variables, and pipeline failures.
2. **Trap for cleanup** — always use `trap` to clean up temp files:
   ```bash
   QBIT_COOKIE=$(mktemp)
   trap 'rm -f "$QBIT_COOKIE"' EXIT
   ```
3. **Idempotency pattern** — always GET and check before POST:
   ```bash
   if echo "$EXISTING_ROOTS" | jq -e '.[] | select(.path == "/data/TV")' &>/dev/null; then
     green "  Root folder /data/TV already exists"
   else
     sonarr POST "rootfolder" '{"path":"/data/TV"}' | jq -r '"  Added: " + .path'
   fi
   ```
4. **API response validation** — after a POST, verify `.id` is present:
   ```bash
   if echo "$RESULT" | jq -e '.id' &>/dev/null; then
     echo "$RESULT" | jq -r '"  Added: " + .name'
   else
     red "  Failed:"
     echo "$RESULT" | jq -r '.[] | "  [" + .severity + "] " + .errorMessage' 2>/dev/null || echo "$RESULT"
     exit 1
   fi
   ```
5. **Fallback logic** — try primary action first, fall back gracefully with clear messaging.

### File naming

- Shell scripts: `kebab-case.sh`
- Systemd units: `kebab-case.service` / `.mount` / `.automount`
- Config files: match the tool's convention (`Caddyfile`, `conf.yml`, `compose.yaml`)
- Container init scripts: numeric prefix indicating execution order (`99-webui-proxy.sh`)

---

## Infrastructure Conventions

### Volume mounts and SELinux

- Add `:Z` to volume mounts on SELinux-enabled hosts so Podman relabels files for container access:
  ```yaml
  - /srv/containers/caddy/Caddyfile:/etc/caddy/Caddyfile:Z
  ```
- **Do NOT add `:Z`** for volumes on exFAT filesystems — exFAT does not support SELinux labels.
  Comment the reason inline:
  ```yaml
  - /srv/media:/data # NO :Z (exFAT drive)
  ```

### LinuxServer.io images

All media service containers use `lscr.io/linuxserver/` images. Always set:
```yaml
environment:
  - PUID=1000
  - PGID=1000
```
Config lives under `/config` inside the container, mapped to `/srv/containers/<service>` on the host.

### Hardlinks for media import

Sonarr/Radarr use hardlinks (not copies) when importing completed downloads. This requires the
downloads directory and the media directory to be on the **same filesystem**. Both `/data/downloads`
and `/data/TV` (or `/data/Movies`) inside the containers must resolve to the same physical drive
(`/srv/media` on the host).

### Firewalled services

Prowlarr (port 9696) may be firewalled externally. Route API calls to it via SSH:
```bash
prowlarr_ssh() {
  ssh "$REMOTE" "curl -sf -X '${1}' -H 'X-Api-Key: ${PROWLARR_API}' \
    http://localhost:9696/api/v1/${2}"
}
```

### Network naming

Internal service discovery uses container names as hostnames on `media_net`.
External user-facing URLs use `.home` local DNS names resolved by Pi-hole.
