#!/usr/bin/env bash
# ==============================================================================
# Deployment script for Medicine Safety Backend
# ==============================================================================

set -euo pipefail

APP_DIR="/opt/medicine-safety"
VENV_DIR="$APP_DIR/backend/.venv"

echo "Deploying Medicine Safety Backend to $APP_DIR..."

cd "$APP_DIR/backend"

# Ensure virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate and install dependencies
source "$VENV_DIR/bin/activate"
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Run migrations if configured
if [ -f "alembic.ini" ]; then
    echo "Running Alembic database migrations..."
    alembic upgrade head || true
fi

# Copy systemd service files
echo "Installing systemd services..."
sudo cp ../systemd/medicine-api.service /etc/systemd/system/
sudo cp ../systemd/medicine-worker.service /etc/systemd/system/
sudo cp ../systemd/medicine-scheduler.service /etc/systemd/system/

sudo systemctl daemon-reload

# Restart services
sudo systemctl restart medicine-api
sudo systemctl restart medicine-worker
sudo systemctl restart medicine-scheduler

sudo systemctl enable medicine-api
sudo systemctl enable medicine-worker
sudo systemctl enable medicine-scheduler

# Configure Nginx
if [ -f "../nginx/medicine-safety.conf" ]; then
    echo "Configuring Nginx..."
    sudo cp ../nginx/medicine-safety.conf /etc/nginx/sites-available/
    sudo ln -sf /etc/nginx/sites-available/medicine-safety.conf /etc/nginx/sites-enabled/
    sudo nginx -t
    sudo systemctl restart nginx
fi

echo "Deployment complete! Checking status:"
sudo systemctl status medicine-api --no-pager -n 5
