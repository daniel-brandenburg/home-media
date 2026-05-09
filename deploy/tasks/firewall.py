"""
tasks/firewall.py — open required ports in firewalld

Idempotent: firewall-cmd ignores ports that are already open.
Safe to re-run at any time.

Requires the server to be running firewalld (standard on OpenSUSE MicroOS).
"""

from pyinfra.operations import server

# ── Port definitions ──────────────────────────────────────────────────────────
# Each entry is (port, protocol, service_name, description)
PORTS = [
    # TCP
    (80,    "tcp", "caddy",          "HTTP reverse proxy"),
    (443,   "tcp", "caddy",          "HTTPS reverse proxy"),
    (3333,  "tcp", "bitmagnet",      "HTTP UI and API"),
    (3334,  "tcp", "bitmagnet",      "DHT crawler (TCP)"),
    (4545,  "tcp", "listenarr",      "Audiobook automation"),
    (6881,  "tcp", "qbittorrent",    "BitTorrent peer traffic (TCP)"),
    (7878,  "tcp", "radarr",         "Movie automation"),
    (8080,  "tcp", "qbittorrent",    "WebUI"),
    (8081,  "tcp", "dashy",          "Dashboard"),
    (8083,  "tcp", "calibre-web",    "Ebook library"),
    (8084,  "tcp", "shelfmark",      "Ebook downloader"),
    (8096,  "tcp", "jellyfin",       "Media streaming"),
    (8989,  "tcp", "sonarr",         "TV automation"),
    (9696,  "tcp", "prowlarr",       "Indexer management"),
    (13378, "tcp", "audiobookshelf", "Audiobook server"),
    # UDP
    (3334,  "udp", "bitmagnet",      "DHT crawler (UDP)"),
    (6881,  "udp", "qbittorrent",    "BitTorrent peer traffic (UDP)"),
]


def _open_port(port: int, proto: str, service: str, desc: str) -> None:
    """Ensure a single port/protocol is permanently open in firewalld."""
    server.shell(
        name=f"firewalld: open {port}/{proto} ({service} — {desc})",
        commands=[
            # Add the port permanently (no-op if already open)
            f"firewall-cmd --permanent --add-port={port}/{proto} 2>/dev/null || true",
        ],
    )


for _port, _proto, _svc, _desc in PORTS:
    _open_port(_port, _proto, _svc, _desc)

# ── Reload firewalld once to activate all permanent rules ─────────────────────
server.shell(
    name="firewalld: reload to activate permanent rules",
    commands=["firewall-cmd --reload"],
)
