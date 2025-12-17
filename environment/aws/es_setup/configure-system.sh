#!/bin/bash

set -x

mkdir -p $HOME/cert
mkdir -p $HOME/log
mkdir -p $HOME/shell2http

curl -LO https://github.com/caddyserver/caddy/releases/download/v2.10.2/caddy_2.10.2_linux_amd64.tar.gz
tar xvf caddy_2.10.2_linux_amd64.tar.gz caddy
rm caddy_2.10.2_linux_amd64.tar.gz

pushd $HOME/shell2http
curl -LO https://github.com/msoap/shell2http/releases/download/v1.17.0/shell2http_1.17.0_linux_amd64.tar.gz
tar xvf shell2http_1.17.0_linux_amd64.tar.gz shell2http
rm shell2http_1.17.0_linux_amd64.tar.gz

if ! command -v iptables &> /dev/null; then
  sudo yum install iptables-services -y
  sudo systemctl enable iptables
  sudo systemctl start iptables
fi