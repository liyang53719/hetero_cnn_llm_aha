#!/usr/bin/env bash
set -euo pipefail

proxy=${HTTPS_PROXY:-${https_proxy:-}}
if [[ -z "$proxy" ]]; then
  echo "No HTTPS proxy is exported in this shell." >&2
  exit 2
fi

cat <<EOF
Docker daemon needs the same proxy reachable from this shell:
  $proxy

User-owned one-time sudo action:
  sudo mkdir -p /etc/systemd/system/docker.service.d
  sudo tee /etc/systemd/system/docker.service.d/http-proxy.conf >/dev/null <<'CONF'
[Service]
Environment="HTTP_PROXY=$proxy"
Environment="HTTPS_PROXY=$proxy"
Environment="NO_PROXY=localhost,127.0.0.1,::1"
CONF
  sudo systemctl daemon-reload
  sudo systemctl restart docker

Then verify with:
  sg docker -c 'docker pull hello-world:latest'
EOF
