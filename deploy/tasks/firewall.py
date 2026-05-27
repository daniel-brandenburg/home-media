"""
tasks/firewall.py — open required ports in firewalld

Strategy:
  - Public zone (WAN/LAN interface): only BitTorrent peer traffic and Jellyfin
    for local LAN streaming. All admin UIs are locked down.
  - Tailscale zone: all service web UIs are accessible only via Tailscale
    (tailscale0 interface). This zone is assigned to the tailscale0 interface.

Idempotent: firewall-cmd ignores ports that are already open / zones that are
already assigned. Safe to re-run at any time.

Requires the server to be running firewalld (standard on OpenSUSE MicroOS).
Tailscale must be installed and `tailscale up` run before this task is deployed
for the tailscale0 interface assignment to take effect.
"""

from pyinfra.operations import server

# ── Public zone — reachable from LAN (and internet if no upstream NAT) ─────────
# Keep this list minimal. Admin UIs are Tailscale-only.
PUBLIC_PORTS = [
    # BitTorrent peer traffic — must be reachable from the internet for good
    # swarm connectivity.
    (6881, "tcp", "qbittorrent", "BitTorrent peer traffic (TCP)"),
    (6881, "udp", "qbittorrent", "BitTorrent peer traffic (UDP)"),
    # Jellyfin on LAN — for local clients that don't go through Tailscale.
    # Remove this if you only ever stream via Tailscale.
    (8096, "tcp", "jellyfin", "Media streaming (LAN)"),
]

# ── Tailscale zone — only reachable via the tailscale0 interface ───────────────
# All service web UIs. Only devices on your Tailnet can reach these.
TAILSCALE_PORTS = [
    (7878,  "tcp", "radarr",         "Movie automation"),
    (8080,  "tcp", "qbittorrent",    "qBittorrent WebUI"),
    (8081,  "tcp", "dashy",          "Dashboard"),
    (8083,  "tcp", "calibre-web",    "Ebook library"),
    (8084,  "tcp", "shelfmark",      "Ebook downloader"),
    (8989,  "tcp", "sonarr",         "TV automation"),
    (9696,  "tcp", "prowlarr",       "Indexer management"),
    (13378, "tcp", "audiobookshelf", "Audiobook server"),
]


def _open_port(port: int, proto: str, service: str, desc: str, zone: str = "public") -> None:
    """Ensure a single port/protocol is permanently open in the given firewalld zone."""
    server.shell(
        name=f"firewalld [{zone}]: open {port}/{proto} ({service} — {desc})",
        commands=[
            f"firewall-cmd --permanent --zone={zone} --add-port={port}/{proto} 2>/dev/null || true",
        ],
    )


# ── Ensure the tailscale zone exists and is bound to tailscale0 ────────────────
server.shell(
    name="firewalld: create tailscale zone (no-op if exists)",
    commands=[
        "firewall-cmd --permanent --new-zone=tailscale 2>/dev/null || true",
    ],
)

server.shell(
    name="firewalld: assign tailscale0 interface to tailscale zone",
    commands=[
        "firewall-cmd --permanent --zone=tailscale --add-interface=tailscale0 2>/dev/null || true",
    ],
)

# ── Open public ports ──────────────────────────────────────────────────────────
for _port, _proto, _svc, _desc in PUBLIC_PORTS:
    _open_port(_port, _proto, _svc, _desc, zone="public")

# ── Open tailscale-only ports ─────────────────────────────────────────────────
for _port, _proto, _svc, _desc in TAILSCALE_PORTS:
    _open_port(_port, _proto, _svc, _desc, zone="tailscale")

# ── Reload firewalld once to activate all permanent rules ─────────────────────
server.shell(
    name="firewalld: reload to activate permanent rules",
    commands=["firewall-cmd --reload"],
)
