"""
tasks/firewall.py — open required ports in firewalld

Strategy:
  - Public zone (LAN/WAN interface): BitTorrent peer traffic, Jellyfin, and all
    admin service web UIs.

Idempotent: firewall-cmd ignores ports that are already open. Safe to re-run
at any time.

Requires the server to be running firewalld (standard on OpenSUSE MicroOS).
"""

from pyinfra.operations import server

# ── Public zone — reachable from LAN (and internet if no upstream NAT) ─────────
PUBLIC_PORTS = [
    # BitTorrent peer traffic — must be reachable from the internet for good
    # swarm connectivity.
    (6881, "tcp", "qbittorrent", "BitTorrent peer traffic (TCP)"),
    (6881, "udp", "qbittorrent", "BitTorrent peer traffic (UDP)"),
    # Jellyfin on LAN.
    (8096, "tcp", "jellyfin", "Media streaming (LAN)"),
    # Admin service web UIs.
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


# ── Open public ports ──────────────────────────────────────────────────────────
for _port, _proto, _svc, _desc in PUBLIC_PORTS:
    _open_port(_port, _proto, _svc, _desc, zone="public")

# ── Reload firewalld once to activate all permanent rules ─────────────────────
server.shell(
    name="firewalld: reload to activate permanent rules",
    commands=["firewall-cmd --reload"],
)
