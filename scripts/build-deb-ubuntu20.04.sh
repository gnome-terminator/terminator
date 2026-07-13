#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
image=${TERMINATOR_DEB_IMAGE:-terminator-deb:ubuntu20.04}
output_dir="$repo_root/dist"

docker_cmd=(docker)
if ! docker info >/dev/null 2>&1; then
    if command -v sudo >/dev/null 2>&1; then
        docker_cmd=(sudo docker)
    else
        echo "Docker is unavailable or the current user cannot access it." >&2
        exit 1
    fi
fi

mkdir -p "$output_dir"

"${docker_cmd[@]}" build \
    --file "$repo_root/packaging/ubuntu20.04/Dockerfile" \
    --tag "$image" \
    "$repo_root"

# Remove artifacts left by older root-based container builds. The clean target
# only removes generated package/build files; the real build below runs as the
# host user.
"${docker_cmd[@]}" run --rm \
    --env HOME=/tmp \
    --volume "$repo_root:/src" \
    --workdir /src \
    "$image" \
    debian/rules clean

# /work is the package output directory (the parent of /work/src). Running as
# the host user prevents root-owned pybuild and Debian artifacts in the source.
"${docker_cmd[@]}" run --rm \
    --user "$(id -u):$(id -g)" \
    --env HOME=/tmp \
    --volume "$output_dir:/work" \
    --volume "$repo_root:/work/src" \
    --workdir /work/src \
    "$image" \
    dpkg-buildpackage -b -us -uc

echo "Ubuntu 20.04 packages are available in: $output_dir"
