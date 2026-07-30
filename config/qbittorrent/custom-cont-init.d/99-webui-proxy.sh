#!/bin/bash
# This script previously disabled CSRF protection, host header validation, and
# local authentication to support a reverse proxy setup. Those overrides have
# been removed — qBittorrent's default security settings are now in effect.
# The WebUI is accessed directly over LAN; no proxy bypass is required.
