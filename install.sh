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

echo ""
echo "Checking for libcec Python bindings..."
if ! python3 -c "import cec" 2>/dev/null; then
    echo ""
    echo "ERROR: libcec Python bindings not found!"
    echo ""
    echo "You must install libcec Python bindings before running this script."
    echo "Please follow the instructions in README.md under 'Installing libcec Python Bindings'"
    echo ""
    echo "Quick summary:"
    echo "  1. Install build dependencies"
    echo "  2. Clone and build libcec from source with -DBUILD_PYTHON=1"
    echo "  3. Run 'python3 -c \"import cec\"' to verify"
    echo ""
    echo "See README.md for full step-by-step instructions."
    echo ""
    exit 1
fi
echo "✓ libcec Python bindings found"

echo ""
echo "-- Installing system dependencies..."
apt-get update
apt-get install -y python3-yaml cec-utils

echo ""
echo "-- Creating installation directory..."
mkdir -p "$INSTALL_DIR"

echo ""
echo "-- Copying files to $INSTALL_DIR..."
cp -r ./*.py "$INSTALL_DIR/"
cp config.yaml "$INSTALL_DIR/"

echo ""
echo "-- Setting permissions..."
chown -R "$USER:$USER" "$INSTALL_DIR"

echo ""
echo "-- Installing systemd service..."
cp "$(dirname "$0")/pi-cec-daemon.service" /etc/systemd/system/
systemctl daemon-reload

echo ""
echo "-- Enabling and starting service..."
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
