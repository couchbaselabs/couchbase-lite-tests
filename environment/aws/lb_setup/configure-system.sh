#!/bin/bash

set -x

if ! command -v docker &> /dev/null; then
  sudo dnf install -y docker
  sudo systemctl start docker
fi

if ! groups $USER | grep -q "\bdocker\b"; then
  sudo usermod -aG docker $USER
fi