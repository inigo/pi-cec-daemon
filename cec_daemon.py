#!/usr/bin/env python3
"""
CEC Daemon - Main business logic for HDMI CEC automation

Monitors CEC traffic and automatically controls TV and peripherals based on state changes.
"""

import sys
import logging
import signal
import time
import yaml
from datetime import datetime
from pathlib import Path
from threading import Thread, Event
from typing import Optional

from cec_delegate import CECDelegate, CECCommand
from devices import TV, Soundbar, Switch, Chromecast, PowerStatus, CECOpcode


class CECDaemon:
    """Main daemon that orchestrates CEC device automation"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize the CEC daemon.

        Args:
            config_path: Path to configuration file
        """
        self.config = self._load_config(config_path)
        self._setup_logging()

        self.logger = logging.getLogger('CECDaemon')
        self.logger.info("Initializing CEC Daemon")

        # Initialize CEC delegate
        self.delegate = CECDelegate()

        # Initialize devices
        self.tv = TV(
            logical_address=self.config['devices']['tv']['logical_address'],
            delegate=self.delegate
        )
        self.soundbar = Soundbar(
            logical_address=self.config['devices']['soundbar']['logical_address'],
            delegate=self.delegate
        )
        self.switch = Switch(
            logical_address=self.config['devices']['switch']['logical_address'],
            delegate=self.delegate
        )
        self.chromecast = Chromecast(
            logical_address=self.config['devices']['chromecast']['logical_address'],
            delegate=self.delegate
        )

        # Polling thread control
        self._stop_event = Event()
        self._polling_thread: Optional[Thread] = None

        # Track pending volume adjustments with timestamps
        self._pending_volume_switch_on = None  # Timestamp or None
        self._pending_volume_switch_off = None  # Timestamp or None
        self._volume_request_timeout = 60.0  # seconds

        # Track if Switch is currently on (for polling)
        self._switch_is_on = False
        self._switch_poll_failures = 0

        # Initialization flag - prevents business logic triggers during startup
        self._initializing = True

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Error: Configuration file '{config_path}' not found", file=sys.stderr)
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"Error parsing configuration file: {e}", file=sys.stderr)
            sys.exit(1)

    def _setup_logging(self) -> None:
        """Setup logging configuration"""
        log_config = self.config.get('logging', {})
        level = getattr(logging, log_config.get('level', 'INFO'))
        log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        log_file = log_config.get('file', 'cec_daemon.log')

        # Configure root logger
        logging.basicConfig(
            level=level,
            format=log_format,
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )

    def start(self) -> None:
        """Start the daemon"""
        self.logger.info("Starting CEC Daemon")

        # Initialize CEC adapter
        if not self.delegate.init():
            self.logger.error("Failed to initialize CEC adapter")
            sys.exit(1)

        # Register callback for CEC messages
        self.delegate.add_callback(self._on_cec_message)

        # Query initial device states
        self.logger.info("Querying initial device states...")
        self.tv.get_power_status()
        self.switch.get_power_status()

        # Start polling thread for TV status
        self._start_polling()

        # Wait for initial state responses (2 seconds should be sufficient)
        time.sleep(2)

        # End initialization phase - enable business logic
        self._initializing = False
        self.logger.info("Initialization complete")

        self.logger.info("CEC Daemon started successfully")

    def stop(self) -> None:
        """Stop the daemon"""
        self.logger.info("Stopping CEC Daemon")

        # Stop polling thread
        self._stop_event.set()
        if self._polling_thread is not None:
            self._polling_thread.join(timeout=5)

        # Close CEC adapter
        self.delegate.close()

        self.logger.info("CEC Daemon stopped")

    def run(self) -> None:
        """Run the daemon (blocks until stopped)"""
        self.start()

        # Wait for stop signal
        try:
            while not self._stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")

        self.stop()

    def _start_polling(self) -> None:
        """Start the TV and Switch status polling thread"""
        interval_ms = self.config.get('tv_polling', {}).get('interval_ms', 1000)
        interval_sec = interval_ms / 1000.0

        def polling_loop():
            self.logger.info(f"Polling started (interval: {interval_ms}ms)")
            while not self._stop_event.is_set():
                # Poll TV status
                self.tv.get_power_status()

                # Poll Switch status if it's currently on
                if self._switch_is_on:
                    if self.switch.get_power_status():
                        # Successfully sent command, reset failure counter
                        self._switch_poll_failures = 0
                    else:
                        # Failed to send command (Switch likely off)
                        self._switch_poll_failures += 1
                        if self._switch_poll_failures >= 3:
                            # After 3 consecutive failures, assume Switch is off
                            self.logger.info("Switch not responding to polls (3 failures), assuming it's off")
                            self._switch_is_on = False
                            self._switch_poll_failures = 0
                            self._on_switch_turned_off()

                # Wait for next poll (or until stop event)
                self._stop_event.wait(interval_sec)

        self._polling_thread = Thread(target=polling_loop, daemon=True)
        self._polling_thread.start()

    def _on_cec_message(self, cmd: CECCommand) -> None:
        """
        Callback for received CEC messages.

        Args:
            cmd: Received CEC command
        """
        # Check if this is background traffic we should ignore for triggering immediate polls
        is_background = self._is_background_traffic(cmd)

        if not is_background:
            # Non-background traffic - check TV status if it's currently off
            if self.tv.is_on() == False:
                self.logger.debug("Non-background traffic detected, checking TV status")
                self.tv.get_power_status()

        # Handle specific message types
        self._handle_power_status_report(cmd)
        self._handle_audio_status_report(cmd)
        self._handle_active_source(cmd)
        self._handle_standby(cmd)

    def _is_background_traffic(self, cmd: CECCommand) -> bool:
        """
        Check if a CEC message is ignorable background traffic.

        Background traffic:
        - TV saying "0F:87:00:E0:91" (vendor ID broadcast)
        - Any traffic from the Pi (initiator = 1)

        Args:
            cmd: CEC command to check

        Returns:
            True if this is background traffic, False otherwise
        """
        # Traffic from the Pi (our device)
        pi_address = self.config['devices']['raspberry_pi']['logical_address']
        if cmd.initiator == pi_address:
            return True

        # TV vendor ID broadcast: 0F:87:00:E0:91
        if (cmd.initiator == 0 and
            cmd.destination == 0x0F and
            cmd.opcode == 0x87 and
            cmd.parameters == b'\x00\xE0\x91'):
            return True

        return False

    def _handle_power_status_report(self, cmd: CECCommand) -> None:
        """
        Handle power status reports from TV and Switch.

        Expected: X1:90:XX where XX is power status
        """
        if cmd.opcode != CECOpcode.REPORT_POWER_STATUS:
            return

        if not cmd.parameters or len(cmd.parameters) < 1:
            self.logger.warning("Received power status report with no parameters")
            return

        try:
            status = PowerStatus(cmd.parameters[0])

            # Handle TV power status
            if cmd.initiator == self.tv.logical_address:
                old_is_on = self.tv.is_on()
                self.tv.update_power_status(status)
                new_is_on = self.tv.is_on()

                # Business logic: TV state changed (skip during initialization)
                if not self._initializing:
                    if old_is_on != new_is_on and new_is_on is not None:
                        if new_is_on:
                            self._on_tv_turned_on()
                        else:
                            self._on_tv_turned_off()

            # Handle Switch power status
            elif cmd.initiator == self.switch.logical_address:
                # We got a response, so reset failure counter
                self._switch_poll_failures = 0

                # Switch is on if status is ON (not standby/transitioning)
                new_is_on = (status == PowerStatus.ON)

                if self._initializing:
                    # During initialization, just set the state
                    if new_is_on:
                        self.logger.info("Switch detected as ON during initialization")
                        self._switch_is_on = True
                else:
                    # Normal operation: detect state changes
                    old_is_on = self._switch_is_on

                    if old_is_on and not new_is_on:
                        # Switch just turned off
                        self.logger.info("Switch turned off (detected via polling)")
                        self._switch_is_on = False
                        self._on_switch_turned_off()

        except ValueError:
            self.logger.warning(f"Unknown power status value: {cmd.parameters[0]:02X}")

    def _handle_audio_status_report(self, cmd: CECCommand) -> None:
        """
        Handle soundbar audio status reports.

        Expected: 51:7A:XX where XX is volume
        """
        if cmd.opcode != CECOpcode.REPORT_AUDIO_STATUS:
            return

        if cmd.initiator != self.soundbar.logical_address:
            return

        if not cmd.parameters or len(cmd.parameters) < 1:
            self.logger.warning("Received audio status report with no parameters")
            return

        # Volume is in the lower 7 bits (bit 7 is mute status)
        volume_cec = cmd.parameters[0] & 0x7F
        self.soundbar.update_volume(volume_cec)

        # Check if we have pending volume adjustments
        if self._pending_volume_switch_on is not None:
            # Check if request hasn't timed out
            if time.time() - self._pending_volume_switch_on < self._volume_request_timeout:
                target_volume = self.config['soundbar']['target_volume_cec']
                volume_step = self.config['soundbar']['volume_step']
                self.logger.info(f"Adjusting volume to {target_volume} (Switch on)")
                self.soundbar.set_volume(
                    target_cec=target_volume,
                    current_cec=volume_cec,
                    step=volume_step
                )
            else:
                self.logger.warning("Volume request timed out (Switch on)")
            self._pending_volume_switch_on = None

        elif self._pending_volume_switch_off is not None:
            # Check if request hasn't timed out
            if time.time() - self._pending_volume_switch_off < self._volume_request_timeout:
                target_volume = 0x18  # 12 on display = 0x18 (24 decimal) in CEC
                volume_step = self.config['soundbar']['volume_step']
                self.logger.info(f"Adjusting volume to {target_volume} (Switch off)")
                self.soundbar.set_volume(
                    target_cec=target_volume,
                    current_cec=volume_cec,
                    step=volume_step
                )
            else:
                self.logger.warning("Volume request timed out (Switch off)")
            self._pending_volume_switch_off = None

    def _handle_active_source(self, cmd: CECCommand) -> None:
        """
        Handle active source announcements.

        Switch broadcasts: 4F:82:10:00 when it becomes active source
        """
        if cmd.opcode != CECOpcode.ACTIVE_SOURCE:
            return

        # Check if it's from the Switch
        if cmd.initiator == self.switch.logical_address:
            was_active = self.switch.is_active_source()
            self.switch.update_active_source(True)

            if not was_active:
                # Switch just turned on, start polling it
                self._switch_is_on = True
                self._switch_poll_failures = 0
                self._on_switch_turned_on()

    def _handle_standby(self, cmd: CECCommand) -> None:
        """
        Handle standby (power off) messages.

        TV broadcasts: 0f:36 when it turns off
        """
        if cmd.opcode != CECOpcode.STANDBY:
            return

        # Check if Switch sent standby (backup detection method, polling is primary)
        if cmd.initiator == self.switch.logical_address:
            was_on = self._switch_is_on
            self._switch_is_on = False
            self.switch.update_active_source(False)

            if was_on:
                self.logger.info("Switch turned off (detected via standby message)")
                self._on_switch_turned_off()

    # ===== Business Logic Rules =====

    def _on_tv_turned_on(self) -> None:
        """Business logic: When TV turns on, turn on soundbar"""
        self.logger.info("TV turned on - turning on soundbar")
        self.soundbar.power_on()

    def _on_tv_turned_off(self) -> None:
        """Business logic: When TV turns off, turn off soundbar"""
        self.logger.info("TV turned off - turning off soundbar")
        self.soundbar.power_off()

    def _on_switch_turned_on(self) -> None:
        """Business logic: When Switch turns on, turn on soundbar and set volume to 8"""
        self.logger.info("Switch turned on - turning on soundbar and requesting volume")

        # Turn on soundbar
        self.soundbar.power_on()

        # Request volume - will be adjusted asynchronously when response arrives
        self._pending_volume_switch_on = time.time()
        self.soundbar.get_volume()

    def _on_switch_turned_off(self) -> None:
        """
        Business logic: When Switch turns off:
        1. Switch to Chromecast as active source
        2. Set soundbar volume to 12 (0x18 CEC)
        3. Turn off TV if it's before 5pm or after 10pm
        """
        self.logger.info("Switch turned off - switching to Chromecast and requesting volume")

        # Make Chromecast the active source
        self.chromecast.make_active_source()

        # Request volume - will be adjusted asynchronously when response arrives
        self._pending_volume_switch_off = time.time()
        self.soundbar.get_volume()

        # Check if we should turn off the TV based on time
        if self._should_turn_off_tv():
            self.logger.info("Time condition met - turning off TV")
            time.sleep(1)  # Brief delay to let Chromecast switch complete
            self.tv.power_off()
        else:
            self.logger.info("Time condition not met - keeping TV on")

    def _should_turn_off_tv(self) -> bool:
        """
        Check if TV should be turned off based on current time.

        TV turns off if current time is NOT between start and end hours.
        (i.e., before 5pm or after 10pm)

        Returns:
            True if TV should be turned off, False otherwise
        """
        now = datetime.now()
        current_hour = now.hour

        rules = self.config.get('rules', {}).get('tv_auto_off_outside_hours', {})
        start_hour = rules.get('start', 17)  # 5pm
        end_hour = rules.get('end', 22)      # 10pm

        # Turn off if NOT between start and end
        # (i.e., before start OR after end)
        should_turn_off = current_hour < start_hour or current_hour >= end_hour

        self.logger.debug(
            f"Current hour: {current_hour}, "
            f"TV on hours: {start_hour}-{end_hour}, "
            f"Should turn off: {should_turn_off}"
        )

        return should_turn_off


def main():
    """Main entry point"""
    # Handle command line arguments
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"

    # Create daemon
    daemon = CECDaemon(config_path)

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        daemon.logger.info(f"Received signal {signum}")
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run daemon
    daemon.run()


if __name__ == "__main__":
    main()
