# AGENTS.md — home-media

This repository is a **self-hosted home media server** infrastructure-as-code project.
It contains no application code, no package manager, and no test framework.
The stack is managed via Podman quadlets and systemd.
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
  dashy/conf.yml                      # Dashboard layout and service tiles (${SERVER_IP} placeholder)
  qbittorrent/
    custom-cont-init.d/
      99-webui-proxy.sh               # qBittorrent WebUI proxy settings patch
quadlets/                             # Podman quadlet unit files (*.container, *.network)
devcontainers/                        # Per-project devcontainer templates (see below)
  dotnet/
    devcontainer.json                 # .NET agent sandbox: build config, firewall capabilities, mounts
    Dockerfile                        # .NET SDK 8.0 image, non-root "agent" user, Claude/Kimi installed
    init-firewall.sh                  # Default-deny egress firewall (iptables/ipset), run per container
  flutter/
    devcontainer.json                 # Flutter agent sandbox: build config, firewall capabilities, mounts
    Dockerfile                        # Ubuntu + Dart/Flutter SDK (stable, no Android SDK), Claude/Kimi installed
    init-firewall.sh                  # Default-deny egress firewall, allowlists pub.dev + storage.googleapis.com
  cpp/
    devcontainer.json                 # C/C++ agent sandbox: build config, firewall capabilities, mounts
    Dockerfile                        # Debian + gcc/clang/cmake/gdb/valgrind, non-root "agent" user, Claude/Kimi installed
    init-firewall.sh                  # Default-deny egress firewall (iptables/ipset), run per container
systemd/
  home-media.target                   # systemd target: groups all container services
  srv-media.mount                     # systemd unit: mount external drive
  srv-media.automount                 # systemd unit: lazy automount
deploy/
  inventory.py                        # pyinfra inventory (reads REMOTE from env/.env)
  deploy.py                           # Main deploy entry point — includes all tasks
  tasks/
    system.py                         # Install packages, create /srv/containers dirs
    config.py                         # Upload dashy conf.yml, qbit init, .env
    quadlets.py                       # Upload quadlet files to /etc/containers/systemd/
    devcontainers.py                  # Upload devcontainers/ templates (recursive) to REMOTE_DIR
    systemd.py                        # Upload systemd units (MEDIA_UUID substituted), daemon-reload, enable services
    firewall.py                       # Open required ports in firewalld (public zone: 6881, 8096, admin UIs)
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

All pyinfra commands must be run via `uv run` so that the project's virtual environment
(including `pyinfra` and `python-dotenv`) is used and `.env` is loaded automatically.

```bash
# Full deploy: packages + config + quadlets + systemd units + firewall
uv run pyinfra deploy/inventory.py deploy/deploy.py

# Deploy only a specific task (e.g. after editing config files):
uv run pyinfra deploy/inventory.py deploy/tasks/config.py
uv run pyinfra deploy/inventory.py deploy/tasks/quadlets.py
uv run pyinfra deploy/inventory.py deploy/tasks/devcontainers.py
uv run pyinfra deploy/inventory.py deploy/tasks/firewall.py
```

### One-time arr wiring (run after the stack is up for the first time)

```bash
# Fill in API keys in .env first (or leave blank — they will be auto-fetched from the server)
uv run pyinfra deploy/inventory.py deploy/tasks/arr_setup.py
```

### Stack management (on the remote server: `ssh user@mediaserver`)

```bash
# Restart a single container service
systemctl restart sonarr.service
```

### Firewall (on the remote server — MicroOS uses firewalld)

Handled automatically by `deploy/tasks/firewall.py`.

**Single-zone strategy:**
- `public` zone: BitTorrent peer traffic (6881), Jellyfin LAN streaming (8096), and all admin web UIs.

To open an additional port manually:

```bash
sudo firewall-cmd --permanent --add-port=<PORT>/tcp
sudo firewall-cmd --reload
```

### No build, lint, or test commands

There is no compiled code, no test framework, and no linter. Validation is manual.

---

## Coding Agent Sandbox

Uses the [Dev Container spec](https://containers.dev/) instead of a hand-rolled quadlet stack —
each project gets its own container, built from a template in `devcontainers/`, with only the
toolchain that project needs.

### How it works

- `devcontainers/<stack>/` holds a reusable template (`devcontainer.json` + `Dockerfile` +
  `init-firewall.sh`) — not tied to any one project repo.
- Templates are **not** copied into each project. [devpod](https://github.com/loft-sh/devpod)'s
  `--devcontainer-path` flag points at the template directly, so `devcontainers/dotnet/` can be
  reused for every .NET repo under `/srv/repos` without modification.
- Each container runs as a non-root `agent` user (uid/gid 1000), mounts the target repo (via the
  CLI's normal workspace mount, at `/workspaces/<repo-name>`), and enforces a default-deny egress
  firewall (iptables/ipset, adapted from
  [Anthropic's reference devcontainer](https://github.com/anthropics/claude-code/blob/main/.devcontainer/init-firewall.sh))
  instead of a shared proxy container — allowlisting only GitHub, the Claude/Kimi APIs, and
  whatever package registry the stack needs (NuGet for .NET, etc).
- Claude Code, Kimi Code, and GitHub CLI (`gh`) auth persist across every project via three fixed
  named volumes (`agent-claude-config`, `agent-kimi-config`, `agent-gh-config`) shared by all
  templates — log in once, reuse everywhere. `gh` itself is installed from GitHub's own apt repo
  (not in Debian's default repos); no firewall changes were needed since `api.github.com` /
  `github.com` were already allowlisted via GitHub's `/meta` IP ranges.
  - `~/.claude.json` (a file, not inside `.claude/`) is symlinked into the `.claude` volume by
    `postCreateCommand` so it persists too — Claude Code writes there directly, not just under
    `.claude/`.
  - Kimi's volume mounts at `/home/agent/.kimi-code`, matching where its installer actually put
    the binary/config — not `/home/agent/.kimi`.
- `postCreateCommand` also git-clones `github.com/daniel-brandenburg/.dotfiles` fresh on every
  container creation (not persisted — the repo itself is the source of truth) and symlinks its
  `.agents/skills` into both `~/.claude/skills` and `~/.agents/skills`.

### Prerequisites (one-time, on the server)

- Podman (already installed for the media stack).
- devpod CLI — a static Go binary installed to `/usr/local/bin/devpod` by
  `deploy/tasks/devcontainers.py` (pinned version + sha256 in that file). No Node/npm or zypper
  package needed, which sidesteps this host's transactional-server package-install path entirely.
- The devcontainer templates themselves, synced to `REMOTE_DIR/devcontainers/` by the same task
  (part of the full deploy, or run standalone — see Deploy above).

### Spinning up a project

Templates live on the server at `REMOTE_DIR/devcontainers/<stack>/` (default
`/srv/containers/devcontainers/<stack>/`) once deployed — reference that path, not this repo's
local `devcontainers/` copy.

**`--devcontainer-path` is always resolved relative to the workspace folder, even if you pass an
absolute path** (devpod naively joins them — confirmed against v0.6.15) — so with the default
`/srv/repos/<project>` and `/srv/containers` layout (siblings under `/srv`), use `../../containers/...`:

`--ide none` skips devpod's default behavior of opening a browser-based VS Code — without it, `up`
starts a local port-forward and idles waiting for someone to open it, then times out
(`EXIT_AFTER_TIMEOUT`, default 3 min); harmless, but the container is already up by then anyway —
just `devpod ssh` in directly regardless:

```bash
devpod up /srv/repos/<your-dotnet-project> \
  --provider docker \
  --devcontainer-path ../../containers/devcontainers/dotnet/devcontainer.json \
  --ide none

# then attach:
devpod ssh /srv/repos/<your-dotnet-project>
```

Devpod's `docker` provider shells out to whatever's on `$PATH` named `docker`/`podman`-compatible;
point it at podman explicitly with `devpod provider add docker --option DOCKER_PATH=podman` once,
or set `DOCKER_PATH=podman` in the environment before `devpod up`.

First run inside: `claude login` / Kimi's equivalent / `gh auth login` — one-time each, since the
config volumes persist. `gh auth login` has no browser in the container; use its device-code flow
(`gh auth login --hostname github.com --git-protocol https --web`, then open the printed URL/code
on another device) or `gh auth login --with-token < token-file` with a PAT.

### Caveats

- **Kimi Code's runtime API domain(s) are unconfirmed** in `init-firewall.sh` — only its installer
  host (`code.kimi.com`) is verified. Watch for connection failures after login and add whatever
  domain the CLI actually talks to.
- **The `up`/`exec` commands above are untested against this repo's actual Podman version** — the
  Dev Container CLI's Podman support (`--docker-path podman`) is less exercised than its Docker
  path; verify `up` succeeds before relying on it.
- `dotnet/`, `flutter/`, and `cpp/` templates exist. The `flutter/` template deliberately omits
  the Android SDK/Gradle — that toolchain pulls from Google Maven, the Gradle plugin portal, and
  `dl.google.com`, which is a much wider (and harder to keep tight) runtime firewall allowlist than
  this default-deny setup aims for. It covers `flutter analyze`/`test`/`build web`/`build linux`,
  not `flutter build apk`/`appbundle`. An Android-SDK variant is still to do if mobile builds are
  needed.

---

## Services and Ports

| Service      | Image                                  | Internal Port | `.home` URL           |
|--------------|----------------------------------------|---------------|-----------------------|
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
(e.g. `http://sonarr:8989`).

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
