#!/usr/bin/env python3
"""
CEC Daemon - Main business logic for HDMI CEC automation

Monitors CEC traffic and automatically controls TV and peripherals based on state changes.
"""
import logging
import signal
import sys

from cec_comms import RealCECComms
from processor_manager import ProcessorManager


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def main():
    setup_logging()
    logger = logging.getLogger('CECDaemon')

    logger.info("Starting CEC Daemon")

    comms = RealCECComms()
    daemon = ProcessorManager(comms)

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down")
        daemon.stop()
        logger.info("CEC Daemon stopped")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if not daemon.start():
        logger.error("Failed to start daemon")
        sys.exit(1)

    logger.info("CEC Daemon running, waiting for events...")

    # Block indefinitely until signal is received
    # This keeps the main thread alive while libcec callbacks run in background
    signal.pause()


if __name__ == "__main__":
    main()
