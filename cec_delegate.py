"""
CEC Event Bus - Low-level CEC transmit/receive interface

Provides an abstraction over libcec for HDMI CEC communication.
"""

import logging
from typing import Callable

from cec_comms import CECComms, CECCommand


class CECEventBus:
    """Event bus for CEC communication - manages callbacks and delegates to CECComms"""

    def __init__(self, comms: CECComms):
        self.logger = logging.getLogger('CECEventBus')
        self._comms = comms
        self._callbacks = []

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
