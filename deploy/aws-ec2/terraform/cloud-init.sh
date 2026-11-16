#!/usr/bin/env bash
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 curl
systemctl enable --now docker
usermod -aG docker ubuntu
mkdir -p /opt/group17
chown -R ubuntu:ubuntu /opt/group17

cat >/etc/motd <<'MOTD'
Group 17 cloud chaos demo host.
Upload the chaos_engineering_project directory to /opt/group17, then run ./start.sh.
MOTD
