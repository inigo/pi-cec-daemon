#!/usr/bin/env python3
"""
CEC Daemon - Main business logic for HDMI CEC automation

Monitors CEC traffic and automatically controls TV and peripherals based on state changes.
"""
import signal
import sys

from cec_comms import RealCECComms
from processor_manager import ProcessorManager


def main():
    comms = RealCECComms()
    daemon = ProcessorManager(comms)

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        daemon.logger.info(f"Received signal {signum}")
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    daemon.start()


if __name__ == "__main__":
    main()
