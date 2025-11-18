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