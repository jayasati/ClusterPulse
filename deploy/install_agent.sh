#!/usr/bin/env bash
# ClusterPulse Agent installer for systemd Linux (tested: Ubuntu 24.04).
#
# Idempotent: safe to re-run for upgrades — existing config is never
# overwritten.
#
# Usage: sudo ./deploy/install_agent.sh [/path/to/repo]
set -euo pipefail

REPO_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
INSTALL_DIR=/opt/clusterpulse
CONFIG_DIR=/etc/clusterpulse
DATA_DIR=/var/lib/clusterpulse
SERVICE_USER=clusterpulse

[ "$(id -u)" -eq 0 ] || { echo "must run as root (sudo)"; exit 1; }
command -v python3.13 >/dev/null || { echo "python3.13 not found on PATH"; exit 1; }

echo "==> system user"
id -u "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"

echo "==> code -> $INSTALL_DIR"
mkdir -p "$INSTALL_DIR" "$DATA_DIR"
cp -r "$REPO_DIR"/{agent,collector,shared,pyproject.toml,README.md} "$INSTALL_DIR"/

echo "==> virtualenv + dependencies"
[ -d "$INSTALL_DIR/.venv" ] || python3.13 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet "$INSTALL_DIR"

echo "==> config"
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/agent.env" ]; then
    cat > "$CONFIG_DIR/agent.env" <<'EOF'
# ClusterPulse Agent configuration - edit before first start.
CLUSTERPULSE_AGENT_COLLECTOR_BASE_URL=http://CHANGE_ME:8000
CLUSTERPULSE_AGENT_AUTH_TOKEN=CHANGE_ME
# node_id defaults to the hostname; set explicitly on cloned images.
#CLUSTERPULSE_AGENT_NODE_ID=
CLUSTERPULSE_AGENT_BUFFER_PATH=/var/lib/clusterpulse/agent_buffer.jsonl
# Optional: remediation execution (opt-in, plus a directory allowlist)
#CLUSTERPULSE_AGENT_REMEDIATION_ENABLED=true
#CLUSTERPULSE_AGENT_REMEDIATION_ALLOWED_DIRECTORIES=/tmp/clusterpulse-reclaimable
EOF
    chmod 640 "$CONFIG_DIR/agent.env"
    chown root:"$SERVICE_USER" "$CONFIG_DIR/agent.env"
    echo "    wrote $CONFIG_DIR/agent.env - EDIT IT before starting"
else
    echo "    $CONFIG_DIR/agent.env exists - left untouched"
fi

echo "==> systemd unit"
cp "$REPO_DIR/deploy/systemd/clusterpulse-agent.service" /etc/systemd/system/
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR" "$DATA_DIR"
systemctl daemon-reload
systemctl enable clusterpulse-agent

echo "done. next: edit $CONFIG_DIR/agent.env, then: systemctl start clusterpulse-agent"
