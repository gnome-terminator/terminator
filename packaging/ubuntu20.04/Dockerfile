FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        devscripts \
        equivs \
    && rm -rf /var/lib/apt/lists/*

# Keep the image dependencies aligned with the package metadata. Docker only
# rebuilds this layer when debian/control changes.
COPY debian/control /tmp/terminator-control
RUN apt-get update \
    && mk-build-deps \
        --install \
        --remove \
        --tool "apt-get -y --no-install-recommends" \
        /tmp/terminator-control \
    && rm -f /tmp/terminator-control \
    && rm -rf /var/lib/apt/lists/*

