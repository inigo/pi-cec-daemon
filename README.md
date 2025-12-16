# Pi CEC Daemon

A Python daemon that monitors HDMI CEC traffic and automatically controls TV and audio peripherals based on device state changes.

## Architecture

- **CEC Delegate Layer** (`cec_delegate.py`): Low-level CEC transmit/receive interface using python-cec
- **Device Classes** (`devices.py`): TV, Soundbar, Switch, and Chromecast abstractions
- **Business Logic** (`cec_daemon.py`): Main daemon implementing automation rules
- **Configuration** (`config.yaml`): Device addresses and settings

## Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd pi-cec-daemon
   ```

2. Run the install script:
   ```bash
   sudo ./install.sh
   ```

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

## Manual Testing

Run the daemon in foreground for testing:
```bash
python3 cec_daemon.py
```
