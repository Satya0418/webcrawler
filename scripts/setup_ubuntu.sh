#!/usr/bin/env bash
# ==============================================================================
# Setup script for Medicine Safety Web Crawling Platform on Ubuntu 22.04/24.04
# Target: Production server deployment (Native Ubuntu - NO Docker)
# ==============================================================================

set -euo pipefail

echo "========================================================="
echo " Starting Medicine Safety Platform Ubuntu Setup"
echo "========================================================="

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies: Python 3.11+, PostgreSQL, Redis, Nginx, UFW, Git, curl
sudo apt install -y \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    postgresql \
    postgresql-contrib \
    libpq-dev \
    redis-server \
    nginx \
    ufw \
    curl \
    git \
    certbot \
    python3-certbot-nginx

# Configure UFW Firewall
echo "Configuring UFW firewall..."
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# Create dedicated non-root application user
if ! id -u medicine > /dev/null 2>&1; then
    echo "Creating dedicated application user 'medicine'..."
    sudo useradd -m -s /bin/bash medicine
fi

# Create application directories
echo "Creating application and runtime data directories..."
sudo mkdir -p /opt/medicine-safety
sudo mkdir -p /var/lib/medicine-safety/raw
sudo mkdir -p /var/lib/medicine-safety/downloads
sudo mkdir -p /var/lib/medicine-safety/exports
sudo mkdir -p /var/log/medicine-safety
sudo mkdir -p /var/backups/medicine-safety

sudo chown -R medicine:medicine /opt/medicine-safety
sudo chown -R medicine:medicine /var/lib/medicine-safety
sudo chown -R medicine:medicine /var/log/medicine-safety
sudo chown -R medicine:medicine /var/backups/medicine-safety

# Configure PostgreSQL Database and User
echo "Setting up PostgreSQL database..."
sudo -u postgres psql -c "CREATE DATABASE medicine_safety;" || true
sudo -u postgres psql -c "CREATE USER medicine_user WITH PASSWORD 'change_this_password_in_production';" || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE medicine_safety TO medicine_user;" || true

# Start and enable Redis
echo "Starting and enabling Redis..."
sudo systemctl enable redis-server
sudo systemctl restart redis-server

# Verify Redis
redis-cli ping

echo "========================================================="
echo " System packages and services successfully prepared!"
echo " Next step: Copy project to /opt/medicine-safety and run scripts/deploy.sh"
echo "========================================================="
