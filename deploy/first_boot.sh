#!/bin/sh
# Lightsail launch script: runs once, as root, when the server is first created.
# Editing this does not affect a server that already exists.
#
# Lightsail puts its own /bin/sh setup in front of this file, so a different
# shebang is ignored: this must stay plain POSIX sh, with no bash features.
set -eux

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 unattended-upgrades
systemctl enable --now docker
usermod -aG docker ubuntu

# Swap gives Ghost and MySQL some headroom on a 2GB server.
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Database passwords are generated here and stay on the server.
install -d -o ubuntu -g ubuntu -m 750 /opt/ghost
umask 077
cat > /opt/ghost/secrets.env <<EOF
MYSQL_ROOT_PASSWORD=$(openssl rand -hex 32)
MYSQL_PASSWORD=$(openssl rand -hex 32)
EOF
chown ubuntu:ubuntu /opt/ghost/secrets.env

touch /opt/ghost/.first-boot-complete
