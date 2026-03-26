#!/usr/bin/env bash
# deploy.sh — pull latest, migrate DB, rebuild frontend, restart services
# Usage: ./scripts/deploy.sh
# Run on VPS as root or sudo-capable user.

set -euo pipefail

APP_DIR=/opt/buhgalter-bot
VENV=$APP_DIR/.venv
SERVICE_API=buhgalter-api
SERVICE_BOT=buhgalter-bot

echo "==> Pulling latest code..."
cd "$APP_DIR"
git pull --ff-only

echo "==> Running Alembic migrations..."
cd "$APP_DIR/backend"
"$VENV/bin/alembic" upgrade head

echo "==> Building frontend..."
cd "$APP_DIR"
npm ci --prefer-offline
npm run build

echo "==> Restarting services..."
systemctl restart "$SERVICE_API"
systemctl restart "$SERVICE_BOT"

echo "==> Reloading nginx..."
nginx -t && systemctl reload nginx

echo "==> Smoke test..."
sleep 2
curl -sf http://127.0.0.1:8000/health || { echo "ERROR: backend health check failed"; exit 1; }

echo ""
echo "Deploy complete."
