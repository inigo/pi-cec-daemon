# Pi CEC Daemon

A Python daemon that monitors HDMI CEC traffic and automatically controls TV and audio peripherals based on device state changes.

## Dependencies

- **libcec Python bindings**: Python module for libcec (must be compiled from source - see below)
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
   - Install system dependencies
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

## Updating Code

After pulling new changes from git:

```bash
cd pi-cec-daemon
git pull
sudo ./update-install.sh
```

This will:
- Stop the service
- Create a timestamped backup
- Copy updated Python files
- Restart the service

## Manual Testing

Run the daemon in foreground for testing (make sure it's not running via systemd first):
```bash
cd /opt/pi-cec-daemon
python3 cli.py
```

Note: Runs as regular user (pi), accesses CEC via libcec. Press Ctrl+C to stop.


# Specification

## Device addresses

* TV: 0
* Pi: 1
* Switch: 4
* Soundbar: 5
* Chromecast: 8

These are currently hardcoded in `Addresses`, but could be looked up dynamically if they turn out to change.

## Business logic

* When the TV is turned on, turn on the soundbar
  * We detect TV on via polling: tx 10:8F (GIVE_DEVICE_POWER_STATUS)
  * TV responds with 01:90:00 (REPORT_POWER_STATUS with status ON)
  * To turn on soundbar: tx 15:8F to check status
  * Soundbar responds with 51:90:XX
  * If status is STANDBY (0x01), send tx 15:44:40 (USER_CONTROL_PRESSED with POWER), then tx 15:45 (USER_CONTROL_RELEASE)

* When the TV is turned off, turn off the soundbar (we don't need any code for this - the TV does it)
  * We could detect TV off via polling: tx 10:8F
  * TV responds with 01:90:01 (REPORT_POWER_STATUS with status STANDBY)
  * To turn off soundbar: tx 15:36 (STANDBY)

* When the Switch is turned on, turn on the soundbar
  * Switch broadcasts 4F:82:10:00 (ACTIVE_SOURCE) when it becomes active
  * To turn on soundbar: use same sequence as TV turn on (check status, toggle if needed)

* When the Switch is turned off, switch to Chromecast
  * We detect Switch off via polling failure: tx 14:8F fails 3 consecutive times
  * Switch to Chromecast: tx 18:82:20:00 (ACTIVE_SOURCE with Chromecast physical address)

* Other things we could do:
  * Turn off the TV if the Switch is turned off in the late evening. This can't be done via CEC
    (the TV doesn't support the relevant codes), but could be done via separate API control.
  * Change the volume when going to Switch (should usually be quieter than TV)

# Architecture

The daemon uses a **processor/event-bus architecture** with generator-based processors:

- **Event Bus** (`eventbus.py`): Manages CEC communication and dispatches events to processors
- **Processors** (`processors.py`): Generator functions that respond to CEC events and send commands
- **Timeout Wrapper** (`with_timeout.py`): Decorator that adds timeout protection to processors
- **CEC Comms** (`cec_comms.py`): Abstraction layer over libcec Python bindings

## Processor Design

Processors are Python generators that:
1. Yield lists of `CECCommand` objects to transmit
2. Receive incoming `CECCommand` objects via `.send()`
3. Terminate by yielding `[None]` or via `StopIteration`

### SwitchStatusProcessor
- **Lifetime**: Runs continuously from startup
- **Behavior**:
  1. Sends initial poll to Switch on startup
  2. Maintains state: `switch_is_on` (boolean)
  3. When Switch is ON: polls every 5 seconds
  4. When Switch is OFF: polls every 60 seconds
  5. Detects state transitions:
     - **ON→OFF**: Poll timeout (2s) → Switch to Chromecast
     - **OFF→ON**: ACTIVE_SOURCE broadcast or poll response → Turn on soundbar
  6. Never terminates

### SoundbarOnWithTvProcessor
- **Lifetime**: Spawned every 500ms, terminates after checking TV
- **Behavior**:
  1. Polls TV power status
  2. If TV is ON: spawns `TurnSoundbarOnProcessor`, then terminates
  3. If TV is OFF: terminates immediately
- **Duplicate Prevention**: Event bus prevents spawning if instance already active (checks processor name)

### TurnSoundbarOnProcessor
- **Lifetime**: Spawned on-demand, terminates after checking soundbar
- **Behavior**:
  1. Polls soundbar power status
  2. If STANDBY: sends power toggle commands, then terminates
  3. If ON: terminates immediately
- **Timeout**: 5 seconds (via `@with_timeout` decorator)

