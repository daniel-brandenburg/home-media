#!/bin/bash
CONF="/config/qBittorrent/qBittorrent.conf"

# Ensure the [Preferences] section exists
if ! grep -q "\[Preferences\]" "$CONF"; then
    echo "[Preferences]" >> "$CONF"
fi

# Function to update or add settings
update_setting() {
    key=$1
    value=$2
    if grep -q "^$key=" "$CONF"; then
        sed -i "s|^$key=.*|$key=$value|" "$CONF"
    else
        sed -i "/^\[Preferences\]/a $key=$value" "$CONF"
    fi
}

# Apply necessary proxy settings
update_setting "WebUI\HostHeaderValidation" "false"
update_setting "WebUI\CSRFProtection" "false"
update_setting "WebUI\LocalHostAuthentication" "false"