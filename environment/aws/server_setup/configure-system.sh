#!/bin/bash

# Check if the script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit 1
fi

echo "Disabling Transparent Huge Pages (THP)..."

cp /tmp/disable-thp.service /etc/systemd/system/disable-thp.service
systemctl daemon-reload
systemctl start disable-thp
systemctl enable disable-thp

tmp=$(cat /sys/kernel/mm/transparent_hugepage/enabled)
if [[ $tmp != *"[never]"* ]]; then
  echo "Failed to disable Transparent Huge Pages!"
  exit 1
fi

tmp=$(cat /sys/kernel/mm/transparent_hugepage/defrag)
if [[ $tmp != *"[never]"* ]]; then
  echo "Failed to disable THP defrag"
  exit 1
fi

echo "Setting swappiness to 1..."

echo 1 > /proc/sys/vm/swappiness
tmp=$(cat /proc/sys/vm/swappiness)
if [[ $tmp != "1" ]]; then
  echo "Failed to set swappiness to 1"
  exit 1
fi

rm -f /home/ec2-user/container-configured