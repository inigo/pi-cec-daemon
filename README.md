# Pi CEC Daemon

A Python daemon that monitors HDMI CEC traffic and automatically controls TV and audio peripherals based on device state changes.

## Architecture

- **CEC Delegate Layer** (`cec_delegate.py`): Low-level CEC transmit/receive interface using python3-cec
- **Device Classes** (`devices.py`): TV, Soundbar, Switch, and Chromecast abstractions
- **Business Logic** (`cec_daemon.py`): Main daemon implementing automation rules
- **Configuration** (`config.yaml`): Device addresses and settings

## Dependencies

- `python3-cec`: Python bindings for libcec (installed from Debian repos)
- `python3-yaml`: YAML parsing library
- `cec-utils`: CEC utilities for testing

## Setup

1. Clone the repository on your Raspberry Pi:
   ```bash
   git clone <repository-url>
   cd pi-cec-daemon
   ```

2. Run the install script:
   ```bash
   sudo ./install.sh
   ```

   This will:
   - Install system dependencies (python3-cec, python3-yaml, cec-utils)
   - Copy files to /opt/pi-cec-daemon
   - Install and start the systemd service

3. Check service status:
   ```bash
   sudo systemctl status pi-cec-daemon
   ```

4. View logs:
   ```bash
   journalctl -u pi-cec-daemon -f
   ```

## Configuration

Edit `config.yaml` to update device logical addresses if devices are moved to different HDMI ports.

After editing, restart the service:
```bash
sudo systemctl restart pi-cec-daemon
```

## Manual Testing

Run the daemon in foreground for testing:
```bash
cd /opt/pi-cec-daemon
sudo python3 cec_daemon.py
```

Note: May require sudo for CEC hardware access.
