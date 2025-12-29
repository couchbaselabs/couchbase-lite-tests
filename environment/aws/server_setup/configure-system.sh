#!/bin/bash

set -x

if ! command -v docker &> /dev/null; then
  echo "Docker not found, installing and starting..."
  sudo dnf install -y docker
  sudo systemctl start docker
fi

if ! groups $USER | grep -q "\bdocker\b"; then
  echo "Adding $USER to docker group"
  sudo usermod -aG docker $USER
fi

mkdir -p $HOME/log
mkdir -p $HOME/shell2http

curl -LO https://github.com/caddyserver/caddy/releases/download/v2.10.2/caddy_2.10.2_linux_arm64.tar.gz
tar xvf caddy_2.10.2_linux_arm64.tar.gz caddy
rm caddy_2.10.2_linux_arm64.tar.gz

# Install shell2http for remote management
pushd $HOME/shell2http
curl -LO https://github.com/msoap/shell2http/releases/download/v1.17.0/shell2http_1.17.0_linux_arm64.tar.gz
tar xvf shell2http_1.17.0_linux_arm64.tar.gz shell2http
rm shell2http_1.17.0_linux_arm64.tar.gz
popd