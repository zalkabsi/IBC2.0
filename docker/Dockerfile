# syntax=docker/dockerfile:1
#
# Headless IB Gateway + IBC + ibc2 watchdog.
#
#   docker build -f docker/Dockerfile -t ibc2 .
#
# The IB Gateway installer is downloaded from Interactive Brokers at build time
# (we cannot redistribute it). Override GATEWAY_URL to pin a specific version.

# ---- stage 1: build IBC.jar and the ibc2 wheel --------------------------------------------------
FROM debian:bookworm-slim AS build
ARG GATEWAY_URL=https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh
# SHA-256 of the installer; set it (with a versioned GATEWAY_URL) so two builds cannot silently differ
ARG GATEWAY_SHA256=
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl ant openjdk-17-jdk-headless python3 python3-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Download and install Gateway into a scratch dir; we only need its jars to compile IBC,
# and the whole install is copied to the final image.
RUN curl -fsSL "$GATEWAY_URL" -o /tmp/ibgateway.sh \
    && echo "Gateway installer sha256: $(sha256sum /tmp/ibgateway.sh | cut -d' ' -f1)" \
    && if [ -n "$GATEWAY_SHA256" ]; then echo "$GATEWAY_SHA256  /tmp/ibgateway.sh" | sha256sum -c -; fi \
    && chmod +x /tmp/ibgateway.sh \
    && /tmp/ibgateway.sh -q -dir /tmp/gw \
    && ls /tmp/gw/jars | head -3

WORKDIR /src
COPY build.xml LICENSE.txt ./
COPY src ./src
COPY test ./test
COPY resources ./resources
COPY python ./python

ENV IBC_BIN=/tmp/gw/jars
RUN ant jar test \
    && python3 -m venv /tmp/buildvenv \
    && /tmp/buildvenv/bin/pip install --no-cache-dir build \
    && cd python \
    && /tmp/buildvenv/bin/python build_assets.py --jar /src/resources/IBC.jar \
    && /tmp/buildvenv/bin/python -m build --wheel --outdir /dist

# ---- stage 2: runtime ----------------------------------------------------------------------------
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates xvfb x11vnc xauth procps bash tini \
        libxrender1 libxtst6 libxi6 libxext6 libxrandr2 libfreetype6 fontconfig fonts-dejavu-core \
        python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 --shell /bin/bash ibc2
COPY --from=build /tmp/gw /tmp/gw
# Move the install to ~/Jts/ibgateway/<version>, the layout IBC expects.
RUN set -eu; \
    ver="$(ls /tmp/gw/jars/jts4launch-*.jar | sed -E 's/.*jts4launch-([0-9]+)\.jar/\1/')"; \
    test -n "$ver"; \
    mkdir -p "/home/ibc2/Jts/ibgateway"; \
    mv /tmp/gw "/home/ibc2/Jts/ibgateway/$ver"; \
    mkdir -p /home/ibc2/gateway-settings /home/ibc2/.ibc2; \
    chown -R ibc2:ibc2 /home/ibc2

COPY --from=build /dist/*.whl /tmp/
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

COPY docker/entrypoint.sh /usr/local/bin/ibc2-entrypoint
# strip any CR characters (a Windows checkout may have added them) and prepare the X11 socket dir for Xvfb
RUN tr -d '\015' < /usr/local/bin/ibc2-entrypoint > /tmp/entry && mv /tmp/entry /usr/local/bin/ibc2-entrypoint \
    && chmod +x /usr/local/bin/ibc2-entrypoint \
    && mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

USER ibc2
ENV PATH="/opt/venv/bin:$PATH" \
    DISPLAY=:1 \
    IBC2_HOME=/home/ibc2/.ibc2 \
    IBC2_APP=gateway \
    IBC2_MODE=paper \
    IBC2_TWS_PATH=/home/ibc2/Jts \
    IBC2_TWS_SETTINGS_PATH=/home/ibc2/gateway-settings \
    IBC2_ALLOW_REMOTE_CLIENTS=true

# 4001 live API, 4002 paper API, 5900 optional VNC (bind it to localhost on the host!)
EXPOSE 4001 4002 5900
VOLUME ["/home/ibc2/.ibc2", "/home/ibc2/gateway-settings"]

# Healthy only when the supervisor is up AND the API answers a real handshake.
# While waiting for your 2FA approval this reports unhealthy, which is accurate.
HEALTHCHECK --interval=60s --timeout=15s --start-period=10m --retries=3 \
    CMD ibc2 status >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "ibc2-entrypoint"]
