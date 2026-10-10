# ibc2 in Docker (headless Gateway)

A container with IB Gateway, IBC, a virtual display and the `ibc2` watchdog. Works on any machine
that runs Docker (Linux, Windows, macOS), including cheap VPSs.

```bash
# 1. your IBKR password as a Docker secret (never in the compose file or git)
mkdir -p secrets && printf '%s' 'your-ibkr-password' > secrets/ibkr_password.txt

# 2. settings
cp docker/.env.example .env      # set IBC2_USERNAME, IBC2_MODE=paper, TZ and an alert channel

# 3. go
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml logs -f
```

Your bot connects to `127.0.0.1:4002` (paper) or `4001` (live). The ports are published on the host's
loopback only, because the IB API is unencrypted. To reach it from another machine use an SSH tunnel
or a VPN rather than publishing the port.

## The weekly 2FA

Roughly once a week IBKR requires a second-factor approval. With an alert channel configured, `ibc2`
messages you when the request appears (and a few hours before it is due). Approve it in the IBKR Mobile
app; nothing else is needed. Without an alert channel the container will sit waiting - the health check
shows *unhealthy* in `docker ps` while it does.

## When Gateway shows something unexpected

You will get an alert naming the window. To look at it, publish the VNC port to localhost and set a
password:

```yaml
    environment:
      VNC_PASSWORD_FILE: /run/secrets/vnc_password
    ports:
      - "127.0.0.1:5900:5900"
```

then connect a VNC client to `localhost:5900` (through an SSH tunnel if the container is remote). To make
the fix permanent, add a rule to `dialogrules.txt` inside the `ibc2-home` volume (see `python/README.md`).

## Notes

- The Gateway installer is downloaded from Interactive Brokers while building the image
  (`--build-arg GATEWAY_URL=...` pins a version). It is not redistributed.
- Settings, logs and Gateway's own configuration live in two named volumes, so recreating the container
  keeps them.
- The container runs as an unprivileged user.
- Always start with `IBC2_MODE=paper`.
