"""
CEC Event Bus - Low-level CEC transmit/receive interface

Provides an abstraction over libcec for HDMI CEC communication.
"""

import logging
import time
from typing import Callable, Generator, Optional

from cec_comms import CECComms, CECCommand


def with_timeout(seconds: float):
    """
    Decorator to add timeout handling to processor generators.

    Args:
        seconds: Timeout in seconds

    Returns:
        Decorator function

    Example:
        @with_timeout(5.0)
        def my_processor():
            cmd = yield [CECCommand.build(destination=0, opcode=0x8F)]
            while cmd.initiator != 0 or cmd.opcode != 0x90:
                cmd = yield []
            # Process response...
            yield [CECCommand.build(...), None]  # Terminate with None
    """
    def decorator(processor_func):
        def wrapper():
            gen = processor_func()  # Create the actual processor
            start_time = time.time()
            logger = logging.getLogger(f'Processor({processor_func.__name__})')

            try:
                # Start the generator and get first commands
                result = next(gen)

                while True:
                    # Check timeout before forwarding each event
                    elapsed = time.time() - start_time
                    if elapsed > seconds:
                        logger.warning(f"Processor '{processor_func.__name__}' timed out after {elapsed:.2f}s")
                        gen.close()
                        yield None  # Signal termination to event bus
                        return

                    # Act as proxy: receive event, forward to real processor
                    event = yield result
                    result = gen.send(event)

            except StopIteration:
                return

        # Preserve function name for logging
        wrapper.__name__ = processor_func.__name__
        return wrapper

    return decorator


class CECEventBus:
    """Event bus for CEC communication - manages callbacks and delegates to CECComms"""

    def __init__(self, comms: CECComms):
        self.logger = logging.getLogger('CECEventBus')
        self._comms = comms
        self._callbacks = []
        self._processors = []  # Active processor generators

    def init(self) -> bool:
        """Initialize the CEC communication layer"""
        return self._comms.init(self._on_cec_command_internal)

    def transmit(self, destination: int, opcode: int, params: bytes = b'') -> bool:
        """Transmit a CEC command via the comms layer"""
        command = CECCommand.build(destination, opcode, params)
        return self._comms.transmit(command)

    def add_callback(self, handler: Callable[[CECCommand], None]) -> None:
        """Register a callback for received CEC commands"""
        self._callbacks.append(handler)

    def add_processor(self, processor: Generator) -> None:
        """
        Add a processor generator.

        The processor should yield lists of CECCommands to transmit, and receives
        CECCommands via send(). Include None in the command list to terminate.

        Args:
            processor: Generator that yields lists of CECCommands and receives CECCommands
        """
        try:
            # Start the processor and get the first list of commands to transmit
            first_commands = next(processor)

            # Transmit all initial commands, check for None termination signal
            processor_done = False
            for cmd in first_commands:
                if cmd is None:
                    # Processor signaled termination
                    processor_done = True
                    break
                self._comms.transmit(cmd)
                self.logger.debug(f"Processor '{processor.__name__}' sent initial command: {cmd}")

            if processor_done:
                self.logger.debug(f"Processor '{processor.__name__}' completed immediately (None in command list)")
                return

            # Add to active processors list
            self._processors.append(processor)
            self.logger.debug(f"Added processor '{processor.__name__}' (total: {len(self._processors)})")

        except StopIteration:
            # Processor completed immediately
            self.logger.debug(f"Processor '{processor.__name__}' completed immediately (StopIteration)")
        except Exception as e:
            self.logger.error(f"Error starting processor '{processor.__name__}': {e}")

    def _on_cec_command_internal(self, cmd_string: str) -> int:
        """Internal callback from comms layer"""
        try:
            # Strip the ">>" prefix if present
            # @todo Does this ever happen? I suspect not
            if cmd_string and cmd_string.startswith(">>"):
                cmd_string = cmd_string.strip().lstrip(">").strip()

            cec_cmd = CECCommand(cmd_string)

            self.logger.debug(f"RX: {cec_cmd}")

            # Dispatch to all registered callbacks
            for handler in self._callbacks:
                try:
                    handler(cec_cmd)
                except Exception as e:
                    self.logger.error(f"Error in CEC callback handler: {e}")

            # Dispatch to all active processors
            finished_processors = []
            for processor in self._processors:
                try:
                    # Send the command to the processor
                    commands = processor.send(cec_cmd)

                    # Processor yielded a list of commands - transmit them all
                    # Check for None in the list which signals termination
                    for cmd in commands:
                        if cmd is None:
                            self.logger.debug(f"Processor '{processor.__name__}' signaled termination (None in command list)")
                            finished_processors.append(processor)
                            break
                        self._comms.transmit(cmd)
                        self.logger.debug(f"Processor '{processor.__name__}' sent command: {cmd}")

                except StopIteration:
                    # Processor finished via return
                    self.logger.debug(f"Processor '{processor.__name__}' completed (StopIteration)")
                    finished_processors.append(processor)
                except Exception as e:
                    self.logger.error(f"Error in processor '{processor.__name__}': {e}")
                    finished_processors.append(processor)

            # Remove finished processors
            for processor in finished_processors:
                self._processors.remove(processor)

            if finished_processors:
                finished_names = [p.__name__ for p in finished_processors]
                self.logger.debug(f"Removed {len(finished_processors)} processor(s) {finished_names}, {len(self._processors)} remaining")

            return 0  # Callback should return 0

        except ValueError as e:
            self.logger.warning(f"Invalid CEC command: {e}")
            return 0
        except Exception as e:
            self.logger.error(f"Error processing CEC command '{cmd_string}': {e}")
            return 0

    def close(self) -> None:
        """Close the CEC communication layer"""
        self._comms.close()
