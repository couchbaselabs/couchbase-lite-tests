#!/bin/bash

set -x

mkdir -p $HOME/config
mkdir -p $HOME/cert
mkdir -p $HOME/logs
mkdir -p $HOME/shell2http

sudo dnf install -y wget

curl -LO https://github.com/caddyserver/caddy/releases/download/v2.10.2/caddy_2.10.2_linux_arm64.tar.gz
tar xvf caddy_2.10.2_linux_arm64.tar.gz caddy
rm caddy_2.10.2_linux_arm64.tar.gz

pushd $HOME/shell2http
curl -LO https://github.com/msoap/shell2http/releases/download/v1.17.0/shell2http_1.17.0_linux_arm64.tar.gz
tar xvf shell2http_1.17.0_linux_arm64.tar.gz shell2http
chmod +x shell2http
rm shell2http_1.17.0_linux_arm64.tar.gz
