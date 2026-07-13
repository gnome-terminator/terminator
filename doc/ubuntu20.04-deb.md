# Building the Ubuntu 20.04 Debian package

The repository contains a reproducible Docker image for Ubuntu 20.04 package
builds. The first run downloads and installs the build dependencies. Later runs
reuse Docker's cached image unless the Dockerfile or `debian/control` changes.

## Build the current version

From the repository root, run:

```sh
./scripts/build-deb-ubuntu20.04.sh
```

The script automatically uses `sudo docker` when the current user cannot access
the Docker daemon directly. It builds as the host UID/GID so generated files do
not become owned by root. Before building, it also cleans artifacts left by old
root-based container builds. Packages and build metadata are written to `dist/`.

## Start a new personal package version

Before packaging a new set of changes, add a changelog entry with a version
higher than the previous package:

```sh
./scripts/update-deb-version.sh \
  2.1.5-1personal4~ubuntu20.04 \
  "Describe the new changes"
```

Review the entry and build it:

```sh
head -n 8 debian/changelog
./scripts/build-deb-ubuntu20.04.sh
```

Install the resulting package, using its actual versioned filename:

```sh
sudo apt install ./dist/terminator_2.1.5-1personal4~ubuntu20.04_all.deb
```

## Useful overrides

Set a different local image name if needed:

```sh
TERMINATOR_DEB_IMAGE=my-terminator-builder:focal \
  ./scripts/build-deb-ubuntu20.04.sh
```

Set changelog identity through `DEBFULLNAME` and `DEBEMAIL`; otherwise the
scripts use `Personal Build <root@localhost>`.
