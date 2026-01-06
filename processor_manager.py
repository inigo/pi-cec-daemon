import logging

from cec_comms import CECComms
from eventbus import CECEventBus
from processors import Addresses, SwitchStatusProcessor, SoundbarOnWithTvProcessor


class ProcessorManager:
    """
    Top-level manager for CEC processors.

    Sets up the event bus, addresses, and manages processor lifecycle.
    """

    def __init__(self, comms: CECComms):
        """
        Initialize the processor manager.

        Args:
            comms: CECComms instance (RealCECComms or MockCECComms)
        """
        self.logger = logging.getLogger('ProcessorManager')
        self.comms = comms
        self.eventbus = CECEventBus(comms)
        self.addresses = Addresses()

    def start(self):
        """Initialize the event bus and start all processors"""
        self.logger.info("Starting processor manager")

        # Initialize the event bus
        if not self.eventbus.init():
            self.logger.error("Failed to initialize event bus")
            return False

        # Add long-running processors
        self.logger.info("Adding SwitchStatusProcessor")
        self.eventbus.add_processor(SwitchStatusProcessor(self.eventbus, self.addresses))

        self.logger.info("Adding SoundbarOnWithTvProcessor")
        self.eventbus.add_processor(SoundbarOnWithTvProcessor(self.eventbus, self.addresses))

        self.logger.info("Processor manager started")
        return True

    def stop(self):
        """Stop the processor manager and clean up resources"""
        self.logger.info("Stopping processor manager")

        # Close the event bus
        self.eventbus.close()

        self.logger.info("Processor manager stopped")
