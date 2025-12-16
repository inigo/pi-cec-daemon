#!/bin/bash
# Installation script for Pi CEC Daemon
# Run this on the Raspberry Pi to install and configure the daemon

set -e  # Exit on any error

INSTALL_DIR="/opt/pi-cec-daemon"
SERVICE_NAME="pi-cec-daemon"
USER="pi"

echo "===================================="
echo "Pi CEC Daemon Installation Script"
echo "===================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Step 1: Installing system dependencies..."
apt-get update
apt-get install -y python3 python3-pip python3-venv python3-cec python3-yaml cec-utils

echo ""
echo "Step 2: Creating installation directory..."
mkdir -p "$INSTALL_DIR"

echo ""
echo "Step 3: Copying files to $INSTALL_DIR..."
cp -r ./*.py "$INSTALL_DIR/"
cp config.yaml "$INSTALL_DIR/"

echo ""
echo "Step 4: Setting permissions..."
chown -R "$USER:$USER" "$INSTALL_DIR"

echo ""
echo "Step 5: Installing systemd service..."
cp "$(dirname "$0")/pi-cec-daemon.service" /etc/systemd/system/
systemctl daemon-reload

echo ""
echo "Step 6: Enabling and starting service..."
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

echo ""
echo "===================================="
echo "Installation complete!"
echo "===================================="
echo ""
echo "Service status:"
systemctl status "$SERVICE_NAME" --no-pager
echo ""
echo "Useful commands:"
echo "  - View logs:        journalctl -u $SERVICE_NAME -f"
echo "  - Restart service:  sudo systemctl restart $SERVICE_NAME"
echo "  - Stop service:     sudo systemctl stop $SERVICE_NAME"
echo "  - Check status:     sudo systemctl status $SERVICE_NAME"
echo "  - View log file:    tail -f $INSTALL_DIR/cec_daemon.log"
echo ""
echo "Configuration file: $INSTALL_DIR/config.yaml"
echo ""
