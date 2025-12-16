# Pi CEC Daemon

A Python daemon that monitors HDMI CEC traffic and automatically controls TV and audio peripherals based on device state changes.

## Architecture

- **CEC Delegate Layer** (`cec_delegate.py`): Low-level CEC transmit/receive interface using libcec Python bindings
- **Device Classes** (`devices.py`): TV, Soundbar, Switch, and Chromecast abstractions
- **Business Logic** (`cec_daemon.py`): Main daemon implementing automation rules
- **Configuration** (`config.yaml`): Device addresses and settings

## Dependencies

- **libcec Python bindings**: Python module for libcec (must be compiled from source - see below)
- `python3-yaml`: YAML parsing library (installed from apt)
- `cec-utils`: CEC utilities for testing (installed from apt)

## Installing libcec Python Bindings

The Python bindings for libcec are not available as a Debian package and must be compiled from source.

### Build and Install

```bash
# Install build dependencies
sudo apt install -y git cmake build-essential pkg-config \
    python3-dev swig libudev-dev libxrandr-dev libp8-platform-dev

# Clone libcec repository
cd ~
git clone https://github.com/Pulse-Eight/libcec.git
cd libcec

# Check out version 7.0.0 (matches libcec7 package)
git checkout libcec-7.0.0

# Create build directory
mkdir build
cd build

# Configure with Python bindings enabled
cmake .. \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -DPYTHON_LIBRARY=$(python3-config --prefix)/lib/libpython3.13.so \
    -DPYTHON_INCLUDE_DIR=$(python3-config --prefix)/include/python3.13 \
    -DBUILD_PYTHON=1

# Build (takes a few minutes on Raspberry Pi)
make -j4

# Install
sudo make install

# Update library cache
sudo ldconfig
```

### Verify Installation

```bash
python3 -c "import cec; print('libcec Python bindings installed successfully')"
```

If this command succeeds without errors, the bindings are installed correctly.

## Setup

**Important**: Install libcec Python bindings first (see section above) before running the installation script.

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
   - Check that libcec Python bindings are installed
   - Install system dependencies (python3-yaml, cec-utils)
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
