#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 VERSION CHANGELOG_MESSAGE" >&2
    echo "Example: $0 2.1.5-1personal4~ubuntu20.04 'Describe the changes'" >&2
    exit 2
fi

version=$1
shift
message=$*
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
image=${TERMINATOR_DEB_IMAGE:-terminator-deb:ubuntu20.04}

docker_cmd=(docker)
if ! docker info >/dev/null 2>&1; then
    if command -v sudo >/dev/null 2>&1; then
        docker_cmd=(sudo docker)
    else
        echo "Docker is unavailable or the current user cannot access it." >&2
        exit 1
    fi
fi

"${docker_cmd[@]}" build \
    --file "$repo_root/packaging/ubuntu20.04/Dockerfile" \
    --tag "$image" \
    "$repo_root"

"${docker_cmd[@]}" run --rm \
    --user "$(id -u):$(id -g)" \
    --env HOME=/tmp \
    --env DEBFULLNAME="${DEBFULLNAME:-Personal Build}" \
    --env DEBEMAIL="${DEBEMAIL:-root@localhost}" \
    --volume "$repo_root:/src" \
    --workdir /src \
    "$image" \
    dch --newversion "$version" --distribution focal "$message"

echo "Updated debian/changelog to version: $version"

