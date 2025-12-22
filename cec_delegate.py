"""
CEC Event Bus - Low-level CEC transmit/receive interface

Provides an abstraction over libcec for HDMI CEC communication.
"""

import logging
from typing import Callable

from cec_comms import CECComms


class CECCommand:
    """Represents a CEC command (received or to be transmitted)"""
    def __init__(self, command_string: str):
        """
        Create a CECCommand from a received command string.

        Args:
            command_string: Command string in format "XX:YY:ZZ..." where XX is initiator+destination
        """
        # Store the original command string
        self.command_string = command_string.strip()

        # Parse the command string (format: "XX:YY:ZZ..." where XX is initiator+destination)
        parts = self.command_string.split(':')
        if len(parts) < 2:
            raise ValueError(f"Invalid CEC command format: {command_string}")

        # Parse first byte: high nibble = initiator, low nibble = destination
        first_byte = int(parts[0], 16)
        self.initiator = (first_byte >> 4) & 0xF
        self.destination = first_byte & 0xF

        # Parse opcode (second byte)
        self.opcode = int(parts[1], 16)

        # Parse parameters (remaining bytes)
        self.parameters = bytes([int(p, 16) for p in parts[2:]]) if len(parts) > 2 else b''

    @classmethod
    def build(cls, destination: int, opcode: int, parameters: bytes = b'') -> 'CECCommand':
        """
        Create a CECCommand for transmission.

        Args:
            destination: CEC logical address of destination device (0-15)
            opcode: CEC opcode
            parameters: Optional parameter bytes

        Returns:
            CECCommand instance ready for transmission
        """
        # Source is always 1 (recording device)
        source = 1

        # Build command string
        first_byte = (source << 4) | destination
        cmd_parts = [f"{first_byte:02X}", f"{opcode:02X}"]
        if parameters:
            cmd_parts.extend([f"{b:02X}" for b in parameters])
        command_string = ":".join(cmd_parts)

        # Create instance with all fields populated
        instance = cls.__new__(cls)
        instance.initiator = source
        instance.destination = destination
        instance.opcode = opcode
        instance.parameters = parameters
        instance.command_string = command_string
        return instance

    def __str__(self):
        """Return the command string"""
        return self.command_string



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
