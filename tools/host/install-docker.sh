#!/usr/bin/env bash

# Installs Docker Engine from Docker's own apt repository on Debian trixie arm64.
# Same result as get.docker.com, without piping a remote script into a root shell.

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive LC_ALL=C
user=${1:?usage: install-docker.sh <user to add to the docker group>}

# The daemon reads this on its very first start, so no image is ever stored
# with the containerd image store, which keeps compressed and unpacked copies.
install -d -m 755 /etc/docker
if [ ! -f /etc/docker/daemon.json ]; then
  cat > /etc/docker/daemon.json <<'JSON'
{
  "features": { "containerd-snapshotter": false },
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
JSON
fi

install -d -m 755 /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

# Docker's published release key fingerprint.
want=9DC858229FC7DD38854AE2D88D81803C0EBFCD88
got=$(gpg --show-keys --with-colons /etc/apt/keyrings/docker.asc | awk -F: '$1 == "fpr" {print $10; exit}')
if [ "$got" != "$want" ]; then
  echo "Unexpected Docker key fingerprint: $got"
  rm -f /etc/apt/keyrings/docker.asc
  exit 1
fi

cat > /etc/apt/sources.list.d/docker.sources <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: trixie
Components: stable
Architectures: arm64
Signed-By: /etc/apt/keyrings/docker.asc
EOF

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

usermod -aG docker "$user"
echo "DOCKER_INSTALL_OK"
