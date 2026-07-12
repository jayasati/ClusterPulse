#!/usr/bin/env bash
# ClusterPulse Collector installer for systemd Linux (tested: Ubuntu 24.04).
#
# Idempotent: safe to re-run for upgrades — existing config files and the
# database are never overwritten.
#
# Usage: sudo ./deploy/install_collector.sh [/path/to/repo]
set -euo pipefail

REPO_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
INSTALL_DIR=/opt/clusterpulse
CONFIG_DIR=/etc/clusterpulse
SERVICE_USER=clusterpulse

[ "$(id -u)" -eq 0 ] || { echo "must run as root (sudo)"; exit 1; }
command -v python3.13 >/dev/null || { echo "python3.13 not found on PATH"; exit 1; }

echo "==> system user"
id -u "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"

echo "==> code -> $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "$REPO_DIR"/{agent,collector,shared,pyproject.toml,alembic.ini,README.md} "$INSTALL_DIR"/

echo "==> virtualenv + dependencies"
[ -d "$INSTALL_DIR/.venv" ] || python3.13 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet "$INSTALL_DIR"

echo "==> config"
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/collector.env" ]; then
    cat > "$CONFIG_DIR/collector.env" <<'EOF'
# ClusterPulse Collector configuration - edit before first start.
CLUSTERPULSE_COLLECTOR_DATABASE_URL=postgresql+psycopg://clusterpulse:CHANGE_ME@localhost:5432/clusterpulse
CLUSTERPULSE_COLLECTOR_API_TOKENS=CHANGE_ME
CLUSTERPULSE_COLLECTOR_ENVIRONMENT=prod
# Optional: Telegram notifications (both or neither)
#CLUSTERPULSE_COLLECTOR_TELEGRAM_BOT_TOKEN=
#CLUSTERPULSE_COLLECTOR_TELEGRAM_CHAT_ID=
# Optional: data retention (opt-in)
#CLUSTERPULSE_COLLECTOR_RETENTION_ENABLED=true
EOF
    chmod 640 "$CONFIG_DIR/collector.env"
    chown root:"$SERVICE_USER" "$CONFIG_DIR/collector.env"
    echo "    wrote $CONFIG_DIR/collector.env - EDIT IT before starting"
else
    echo "    $CONFIG_DIR/collector.env exists - left untouched"
fi

echo "==> grafana read-only role (if postgres is local)"
if command -v psql >/dev/null && sudo -u postgres psql -tAc "SELECT 1" >/dev/null 2>&1; then
    sudo -u postgres psql -d clusterpulse -f "$REPO_DIR/deploy/postgres/init-grafana-reader.sql" 2>/dev/null \
        || echo "    role exists or db missing - skipped (apply deploy/postgres/init-grafana-reader.sql manually if needed)"
fi

echo "==> database migrations"
set -a; . "$CONFIG_DIR/collector.env"; set +a
(cd "$INSTALL_DIR" && .venv/bin/alembic upgrade head) \
    || echo "    migrations failed (unconfigured database?) - run manually: cd $INSTALL_DIR && .venv/bin/alembic upgrade head"

echo "==> systemd unit"
cp "$REPO_DIR/deploy/systemd/clusterpulse-collector.service" /etc/systemd/system/
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"
systemctl daemon-reload
systemctl enable clusterpulse-collector

echo "done. next: edit $CONFIG_DIR/collector.env, then: systemctl start clusterpulse-collector"
