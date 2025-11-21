#!/bin/bash

set -x

mkdir -p $HOME/config
mkdir -p $HOME/cert
mkdir -p $HOME/logs

sudo dnf install -y wget

curl -LO https://github.com/caddyserver/caddy/releases/download/v2.10.2/caddy_2.10.2_linux_arm64.tar.gz
tar xvf caddy_2.10.2_linux_arm64.tar.gz caddy
rm caddy_2.10.2_linux_arm64.tar.gz