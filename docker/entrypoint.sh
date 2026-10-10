#!/usr/bin/env bash
# Starts a virtual display (and optionally VNC), then runs the ibc2 supervisor in the foreground.
set -euo pipefail

: "${DISPLAY:=:1}"
export DISPLAY

# a stale lock from a previous run of this container would stop Xvfb starting
rm -f "/tmp/.X${DISPLAY#:}-lock" "/tmp/.X11-unix/X${DISPLAY#:}" 2>/dev/null || true

Xvfb "$DISPLAY" -screen 0 1280x1024x24 -nolisten tcp &
for _ in $(seq 1 50); do
    [ -e "/tmp/.X11-unix/X${DISPLAY#:}" ] && break
    sleep 0.2
done

# Optional VNC so you can watch / click through an unexpected dialog. Only started when
# a password is supplied; never expose port 5900 beyond localhost without a tunnel.
vnc_password="${VNC_PASSWORD:-}"
if [ -z "$vnc_password" ] && [ -n "${VNC_PASSWORD_FILE:-}" ] && [ -r "$VNC_PASSWORD_FILE" ]; then
    vnc_password="$(tr -d '\r\n' < "$VNC_PASSWORD_FILE")"
fi
if [ -n "$vnc_password" ]; then
    mkdir -p "$HOME/.vnc"
    x11vnc -storepasswd "$vnc_password" "$HOME/.vnc/passwd" >/dev/null 2>&1
    x11vnc -display "$DISPLAY" -rfbauth "$HOME/.vnc/passwd" -forever -shared -noxdamage -rfbport 5900 \
        -bg -o "$HOME/.vnc/x11vnc.log" >/dev/null 2>&1
    echo "VNC enabled on port 5900"
fi
unset vnc_password

# IBC2_USERNAME is required; the password comes from IBC2_PASSWORD_FILE (a Docker secret) or IBC2_PASSWORD
if [ -z "${IBC2_USERNAME:-}" ]; then
    echo "ibc2: IBC2_USERNAME is not set" >&2
    exit 2
fi
if [ -z "${IBC2_PASSWORD:-}" ] && [ -z "${IBC2_PASSWORD_FILE:-}" ]; then
    echo "ibc2: set IBC2_PASSWORD_FILE (recommended) or IBC2_PASSWORD" >&2
    exit 2
fi

exec ibc2 run
