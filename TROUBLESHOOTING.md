# TROUBLESHOOTING.md — home-media

Diagnostic procedure and incident history for the media server.

Two things make this stack harder to debug than it looks, and both are covered below:
containers can report `active (running)` while the application inside them is crash-looping,
and the ordinary log commands return nothing useful unless you know where to look.

> **Note on agent access:** `AGENTS.md` forbids agents from running commands on the remote
> server. That rule stands by default — a human operator runs these commands unless the user
> has granted SSH access in that same conversation.

---

## Access gotchas (read first)

These will waste your time otherwise. All examples assume `ssh db@192.168.0.50`.

| Symptom | Cause | What to do instead |
|---|---|---|
| `podman ps` shows no containers | Quadlets in `/etc/containers/systemd/` are **rootful**. Their containers live in root's storage, invisible to `db`. | `sudo podman ps` — but see the next row. |
| `sudo: a terminal is required to read the password` | Non-interactive SSH has no TTY for the password prompt. | `ssh -t db@192.168.0.50 'sudo ...'`, or avoid sudo using the alternatives below. |
| `journalctl -u <service>` prints `-- No entries --` | `db` is not in the `systemd-journal` group, so it only sees its own messages. | `sudo journalctl`, or read the app's own log files under `/srv/containers/<service>/log/`. |
| `systemctl status <service>` works fine, though | Unit *state* is world-readable even when its logs are not. | Use it for uptime, PID, restart count, and the process tree. |

**Rootless exception:** the devpod agent sandboxes (`devcontainers/`) run under the devcontainer
user's own rootless Podman — use plain `podman` (no sudo) and `devpod list` for those.

---

## Diagnosing a service that "isn't running"

Work down this list. Most failures are identified by step 3.

### 1. Is the unit up?

```bash
systemctl status <service>.service --no-pager -l
```

`Loaded: ... (/etc/containers/systemd/<service>.container; generated)` confirms the quadlet
generator picked up the file. If the unit does not exist at all, the quadlet was never deployed
or `daemon-reload` never ran — see "Unit not found" below.

### 2. Is the *application* up, or just the container?

**This is the step people skip.** LinuxServer.io images run an s6 supervisor as PID 1. If the
app inside crashes, s6 restarts it in a loop — the container stays alive and systemd keeps
reporting `active (running)` indefinitely.

Read the process tree in the `systemctl status` output. A healthy service shows its actual
process (`jellyfin.dll`, `Sonarr`, etc.). A crash-looping one shows only s6 scaffolding —
`s6-supervise svc-<name>` with no child, `s6-svlisten1`, `sleep infinity`.

Two corroborating signals:
- **CPU time far exceeding uptime's idle baseline.** 5 minutes of CPU in 16 minutes of uptime is
  a restart loop, not idle.
- **A log file growing by tens of MB per day.** Steady-state services do not do this.

### 3. Read the application's own log

Independent of the journal, and readable without sudo (files are owned by `PUID`):

```bash
ls -lat /srv/containers/<service>/log/
tail -c 6000 /srv/containers/<service>/log/log_$(date +%Y%m%d).log
```

In a crash loop the same fatal block repeats every couple of seconds. Search for `[FTL]`,
`Unhandled Exception`, `FATAL`, or `panic`. **Tail with `-c`, not `-n`** — these files reach
tens of MB and reading whole lines from the top is slow and pointless.

### 4. Check the resources it depends on

```bash
df -h /srv /var                # disk — see "Disk pressure" below
findmnt /srv/media             # media drive; must show /dev/sdX1 exfat, not just autofs
curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://localhost:<port>/health
```

`findmnt /srv/media` returning **only** the `autofs` line means the automount point exists but
the drive is not actually mounted. Every quadlet has `Requires=srv-media.mount`, so a failed
mount blocks the whole stack from starting — and produces no container logs at all, because no
container ever starts.

---

## Common failure modes

### Disk pressure on `/srv`

The NVMe is split into a **20G `/srv`** (nvme0n1p2) and a **219G `/var`** (nvme0n1p3).
`/srv` is small and holds all container config, so anything that grows without bound will fill
it. Check `/srv` before `/var` — it is nearly always the one under pressure.

```bash
du -sh /srv/containers/* | sort -rh | head
```

Jellyfin's cache is bind-mounted from `/var/lib/jellyfin-cache` for exactly this reason. When
adding a service, identify which of its directories has no upper bound and mount that one from
`/var` (convention documented in `AGENTS.md`).

Safe to delete when space is needed: anything under a service's `cache/`, and rotated
`log_*.log` files. Do **not** delete `data/` — that holds library databases and metadata.

### Unit not found

`Unit <service>.service could not be found` means the quadlet generator never saw the file:

```bash
ls /etc/containers/systemd/           # is the .container file there?
sudo systemctl daemon-reload          # regenerates units from quadlets
```

Quadlet-generated services **cannot be `systemctl enable`d** — they are generated into
`/run/systemd/generator/`. Each declares `WantedBy=home-media.target`, so
`systemctl start home-media.target` is what brings them up.

### Service is up but unreachable from the LAN

Port not open in firewalld. `deploy/tasks/firewall.py` handles this; to check by hand:

```bash
sudo firewall-cmd --list-ports
```

---

## Resetting Audiobookshelf root password (offline DB edit)

Audiobookshelf keep no CLI password-reset. DB direct edit only way if root password lost.
DB file: `/srv/containers/audiobookshelf/config/absdatabase.sqlite` (rootful quadlet, `db@192.168.0.50`).

**Stop container first.** SQLite write while app hold file open risk corruption.

```bash
ssh -t db@192.168.0.50 'sudo systemctl stop audiobookshelf.service'
```

**Backup + download DB:**

```bash
ssh -t db@192.168.0.50 'sudo cp /srv/containers/audiobookshelf/config/absdatabase.sqlite /srv/containers/audiobookshelf/config/absdatabase.sqlite.bak'
scp db@192.168.0.50:/srv/containers/audiobookshelf/config/absdatabase.sqlite ./absdatabase.sqlite
```

(root owns file — may need `sudo chmod 644` on remote copy first, or `sudo cat ... > /tmp/... && chown db` workaround, before scp pull works as `db`.)

**Edit locally with sqlite3:**

```bash
sqlite3 absdatabase.sqlite
```

```sql
.headers on
SELECT id, username, type FROM users;
-- confirm root user row (type = 'root')
UPDATE users SET pash = '' WHERE username = 'root';
.quit
```

Blank `pash` = known Audiobookshelf behavior: root user with empty hash log in with **any password / blank password** at next login. Set real password immediately after login, in Settings → Users.

**Reupload + restore ownership/SELinux label:**

```bash
scp ./absdatabase.sqlite db@192.168.0.50:/tmp/absdatabase.sqlite
ssh -t db@192.168.0.50 'sudo mv /tmp/absdatabase.sqlite /srv/containers/audiobookshelf/config/absdatabase.sqlite && sudo restorecon -v /srv/containers/audiobookshelf/config/absdatabase.sqlite'
```

Volume line has `:Z` (`Volume=/srv/containers/audiobookshelf/config:/config:Z`), so SELinux context matter — `restorecon` fix label after file replaced from outside container context, else container may fail to read it.

**Start container back up, log in, set new password right away:**

```bash
ssh -t db@192.168.0.50 'sudo systemctl start audiobookshelf.service'
```

Verify app healthy after (see "Diagnosing a service that isn't running" above) before call it done. Keep `.bak` file until confirmed working.

---

## Incident log

### 2026-08-12 — Jellyfin crash-looping for two days on a full disk

**Symptom.** Jellyfin unreachable on 8096. `systemctl status jellyfin.service` reported
`active (running)`, 16 minutes uptime, no obvious error.

**Diagnosis.** The process tree showed s6 scaffolding but no `jellyfin.dll` process, and 5m33s
of CPU across 16 minutes of uptime — a restart loop. `podman logs` as `db` failed (rootful
container) and `journalctl -u jellyfin` was empty (no `systemd-journal` group), so the finding
came from `/srv/containers/jellyfin/log/log_20260812.log`, repeating every ~2 seconds:

```
[FTL] [1] Main: Unhandled Exception
System.InvalidOperationException: The path `/config/data/data` has insufficient free space.
Available: 989.5MiB, Required: 2GiB.
```

**Root cause.** A transcode session on Aug 10 18:03 left 735 orphaned `.mp4` segments — 4.8G —
in `/srv/containers/jellyfin/cache/transcodes`, taking the 20G `/srv` to 95% full. Jellyfin
10.11+ enforces a 2GiB free-space precondition on its data path at startup. This deadlocks:
the **"Clean Transcode Directory" task that would free the space only runs after startup
completes**, so Jellyfin could never recover on its own. The loop then wrote 89MB (Aug 11) and
62MB (Aug 12) of logs, consuming what space remained.

**Fix.** Deleted the orphaned segments and the two crash-spam log files — `/srv` 95% → 69%,
5.9G free. No restart was needed: the s6 retry loop picked it up within seconds, and Jellyfin
ran its own transcode cleanup on boot. Permanent fix: cache relocated to `/var/lib/jellyfin-cache`
(`quadlets/jellyfin.container`), with the directory created by `deploy/tasks/system.py`.

**Lessons carried into this document.** `active (running)` does not mean the application is
running. The journal is not the only log, and often not the reachable one. A service that
cleans up after itself cannot do so if the cleanup runs post-startup and startup is what fails.
