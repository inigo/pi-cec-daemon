#!/bin/bash
# Update script for Pi CEC Daemon
# Run this after pulling code changes from git

set -e  # Exit on any error

INSTALL_DIR="/opt/pi-cec-daemon"
SERVICE_NAME="pi-cec-daemon"
USER="pi"

echo "===================================="
echo "Pi CEC Daemon Update Script"
echo "===================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

# Check if installation directory exists
if [ ! -d "$INSTALL_DIR" ]; then
    echo "Error: Installation directory $INSTALL_DIR does not exist"
    echo "Please run ./install.sh first"
    exit 1
fi

echo "Step 1: Stopping service..."
systemctl stop "$SERVICE_NAME" || true

echo ""
echo "Step 2: Backing up current installation..."
BACKUP_DIR="$INSTALL_DIR.backup.$(date +%Y%m%d_%H%M%S)"
cp -r "$INSTALL_DIR" "$BACKUP_DIR"
echo "Backup created at: $BACKUP_DIR"

echo ""
echo "Step 3: Updating Python files..."
cp ./*.py "$INSTALL_DIR/"

echo ""
echo "Step 4: Updating configuration..."
# Only update config.yaml if user hasn't modified it, or create if missing
if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
    echo "Config file missing, copying new one..."
    cp config.yaml "$INSTALL_DIR/"
elif diff -q config.yaml "$INSTALL_DIR/config.yaml" > /dev/null 2>&1; then
    echo "Config unchanged, skipping..."
else
    echo "WARNING: config.yaml has local changes"
    echo "New config saved as: $INSTALL_DIR/config.yaml.new"
    cp config.yaml "$INSTALL_DIR/config.yaml.new"
    echo "Please merge changes manually if needed"
fi

echo ""
echo "Step 5: Setting permissions..."
chown -R "$USER:$USER" "$INSTALL_DIR"

echo ""
echo "Step 6: Starting service..."
systemctl start "$SERVICE_NAME"

echo ""
echo "Step 7: Checking service status..."
sleep 1
systemctl status "$SERVICE_NAME" --no-pager || true

echo ""
echo "===================================="
echo "Update complete!"
echo "===================================="
echo ""
echo "Useful commands:"
echo "  - View logs:        journalctl -u $SERVICE_NAME -f"
echo "  - Restart service:  sudo systemctl restart $SERVICE_NAME"
echo "  - Stop service:     sudo systemctl stop $SERVICE_NAME"
echo "  - Check status:     sudo systemctl status $SERVICE_NAME"
echo ""
echo "Backup location: $BACKUP_DIR"
echo ""
