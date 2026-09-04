#!/usr/bin/env bash
# ==============================================================================
# Service restart script for Medicine Safety Platform
# ==============================================================================

set -euo pipefail

echo "Restarting Medicine Safety systemd services..."

sudo systemctl restart medicine-api
sudo systemctl restart medicine-worker
sudo systemctl restart medicine-scheduler
sudo systemctl restart redis-server
sudo systemctl restart nginx

echo "Services restarted. Status:"
sudo systemctl status medicine-api medicine-worker medicine-scheduler --no-pager -n 3
