# ThirdPlacePages agent sandbox

A devcontainer for running Claude Code (or Kimi Code) against the
[ThirdPlacePages](https://github.com/ThirdPlacePages/thirdplacepages) repo on the home-media
server. It is built and started with [devpod](https://github.com/loft-sh/devpod) on rootless
Podman, the same way as the other templates in `devcontainers/`.

## What's inside

| Tool | Notes |
|------|-------|
| .NET 10 SDK | `src/Server/global.json` pins `10.0.100` (`rollForward: latestFeature`) |
| `dotnet-ef` 10.0.11 | global tool, matches EF Core in `Directory.Packages.props` |
| `claude`, `kimi` | native installers, in `~/.local/bin` and `~/.kimi-code/bin` |
| `gh`, `git`, `tmux`, `jq`, `sqlite3`, `python3`, `build-essential` | `sqlite3` is used by `scripts/new-worktree.sh` |

There is **no container engine** in the container, and **no network filtering** — outbound
traffic is unrestricted.

### What works and what doesn't

| Works | Does not work |
|-------|---------------|
| `dotnet build`, `dotnet format` | Any test that uses Testcontainers (Postgres, RabbitMQ, MinIO, Mailpit, Keycloak) |
| `scripts/test-backend.sh <Module>` for test projects that don't start containers | `scripts/test-all.sh` and the full `dotnet test --solution` run |
| `scripts/new-worktree.sh`, git, `gh` | `run.sh` (Aspire AppHost), `scripts/test-e2e.sh`, `scripts/regen-openapi.sh` |
| | The `pre-push` hook when pushing to `main` (it runs `test-all.sh`) |

`AGENTS.md` in the repo requires `scripts/test-all.sh` before any merge to `main`. Run that
from your laptop (or wherever Docker is available), not in this sandbox.

The Flutter client (`src/Client`) is not supported here — it is being replaced by KMP. When
`src/Native` exists, add a JDK 21 + Android SDK layer to the `Dockerfile`.

## One-time setup

All of this runs on the server (`ssh db@<server>`) unless noted.

1. **Deploy the template** (from your laptop, in the home-media repo):

   ```bash
   claude-config/link.sh        # once: symlinks your ~/.claude config into claude-config/
   uv run pyinfra deploy/inventory.py deploy/tasks/devcontainers.py
   ```

   This puts the template at `/srv/containers/devcontainers/thirdplacepages/` and your Claude
   config at `/srv/containers/claude-config/`. The container mounts the latter, so deploy first:
   container creation fails if that directory is missing.

2. **Point devpod at Podman** (once per server user):

   ```bash
   devpod provider add docker --option DOCKER_PATH=podman
   ```

   If the provider already exists, use `devpod provider set-options docker --option DOCKER_PATH=podman`.

3. **Clone the repo over HTTPS** (SSH remotes are not used in the sandbox):

   ```bash
   git clone https://github.com/ThirdPlacePages/thirdplacepages.git /srv/repos/ThirdPlacePages
   ```

   The repo is private, so cloning on the host needs a credential. Either run `gh auth login` on
   the host, or clone with a PAT.

## Start the container

```bash
devpod up /srv/repos/ThirdPlacePages \
  --provider docker \
  --devcontainer-path ../../containers/devcontainers/thirdplacepages/devcontainer.json \
  --ide none
```

- `--devcontainer-path` is resolved relative to the workspace folder even when absolute, so with
  the repo in `/srv/repos` and the templates in `/srv/containers` (siblings under `/srv`) it
  is `../../containers/...`.
- `--ide none` stops devpod waiting for a browser VS Code to connect. The container is up
  regardless.
- The first run builds the image, which takes a few minutes.

## Connect

On the server:

```bash
devpod list                      # shows the workspace name (derived from the folder: thirdplacepages)
devpod ssh thirdplacepages       # shell as the "ubuntu" user, repo at /workspaces/ThirdPlacePages
```

From your laptop in one go:

```bash
ssh -t db@<server> devpod ssh thirdplacepages
```

### First login (once)

The login volumes are shared by every sandbox (`agent-claude-config`, `agent-kimi-config`,
`agent-gh-config`). If you already logged in from another sandbox, skip this.

```bash
claude                                                       # follow the login prompt
gh auth login --hostname github.com --git-protocol https --web
```

There is no browser in the container, so `gh` prints a URL and a one-time code to open on
another device. Alternatively: `gh auth login --with-token < token-file` with a PAT that can
access `ThirdPlacePages/thirdplacepages`.

`git push` over HTTPS uses `gh` as its credential helper; the template configures that
automatically.

### Your Claude config

Your laptop's `~/.claude` `CLAUDE.md`, `settings.json`, `statusline.sh`, `rules/`, `agents/` and
`skills/` are available in every sandbox (mounted read-only at `/opt/claude-config` and linked
or copied into `~/.claude` when the container is created). To update them: edit locally, redeploy
(`devcontainers.py` task), then:

- `skills`, `agents`, `rules`, `CLAUDE.md` update immediately (they are links).
- `settings.json` and `statusline.sh` are copies: run `bash /opt/claude-config/setup.sh` in the
  container, or recreate it.

Not carried over: MCP servers (they live in `~/.claude.json`), plugins' installed files (plugins in
`enabledPlugins` are fetched by Claude Code on first start), history, and credentials. Files you
delete locally stay on the server until you remove them from `/srv/containers/claude-config`.
Note that your global `CLAUDE.md` applies to headless `claude -p` runs too, including its
"ask clarifying questions before non-trivial work" rule.

### Keep Claude running after you disconnect

Closing the SSH session kills foreground processes. Run Claude inside tmux:

```bash
tmux new -A -s claude        # create or re-attach
cd /workspaces/ThirdPlacePages && claude
# detach: Ctrl-b d        re-attach later: tmux new -A -s claude
```

tmux sessions live inside the container, so they survive disconnects but not
`devpod stop` or `--recreate`. Rootless Podman containers survive you logging out of the host
only because `deploy/tasks/devcontainers.py` enables systemd linger for the server user.

## Day to day

```bash
devpod stop thirdplacepages          # stop the container (keeps it and its volumes)
devpod up /srv/repos/ThirdPlacePages --provider docker \
  --devcontainer-path ../../containers/devcontainers/thirdplacepages/devcontainer.json --ide none
                                     # start it again
devpod delete thirdplacepages        # remove the container (named volumes stay)
```

After you change anything in this template, redeploy it and rebuild:

```bash
# on your laptop
uv run pyinfra deploy/inventory.py deploy/tasks/devcontainers.py
# on the server: same `devpod up ...` command as above, plus --recreate
```

What survives `--recreate`: the three login volumes and the `thirdplacepages-worktrees` volume.
What doesn't: everything else in the container, including the NuGet cache, tmux sessions and
the copied `settings.json` (re-copied from `/opt/claude-config` on every create).

### Worktrees

`scripts/new-worktree.sh` creates worktrees in `/workspaces/ThirdPlacePages_worktrees`
(a named volume), so they persist across rebuilds. The repo's `.git/worktrees/*` metadata points
at container-only paths, so don't run `git worktree prune` on the host checkout: it would drop
the metadata of worktrees it can't see. Run `scripts/install-hooks.sh` in each new worktree
(per the repo's `AGENTS.md`).

## Caveats

- **Disk:** `/srv` is only 20G and the repo checkout (including `bin/` and `obj/`) lives in
  `/srv/repos`. Check `df -h /srv` if builds start failing. The image and named volumes live in the
  server user's Podman store (`podman system df`); check which partition holds it, since
  the .NET SDK image plus tools is a couple of GB.
- **Security:** the sandbox has unrestricted internet access and `gh` credentials for your
  GitHub account. Treat what the agent can reach accordingly.
- **Untested:** this template has not been built or run on the server's Podman yet. If
  `devpod up` fails, check `podman ps -a` and `devpod up ... --debug`.

## Removing the old Squid proxy leftovers (one-time)

The Squid egress proxy was removed from the stack. `deploy/tasks/devcontainers.py` stops the
service and deletes its quadlet, network quadlet and config files on the next deploy, but it
does not touch Podman objects. On the server, as the devpod user:

```bash
podman ps -a --filter name=squid          # should be empty after the deploy
podman network rm systemd-devcontainer-egress
podman image rm docker.io/ubuntu/squid:6.6-24.04_edge
```

The `alarmclock` and `anothertradingplatform` workspaces were created attached to the old
`systemd-devcontainer-egress` network. Recreate them (`devpod up ... --recreate`) after
deploying, and before removing that network.
