"""
CEC Delegate Layer - Low-level CEC transmit/receive interface

Provides an abstraction over libcec for HDMI CEC communication.
"""

import logging
from typing import Callable


class CECCommand:
    """Represents a received CEC command"""
    def __init__(self, initiator: int, destination: int, opcode: int, parameters: bytes):
        self.initiator = initiator
        self.destination = destination
        self.opcode = opcode
        self.parameters = parameters

    def __str__(self):
        """Format as hex string like '0F:87:00:E0:91'"""
        # First byte is initiator (high nibble) + destination (low nibble)
        first_byte = (self.initiator << 4) | self.destination
        parts = [f"{first_byte:02X}", f"{self.opcode:02X}"]
        if self.parameters:
            parts.extend([f"{b:02X}" for b in self.parameters])
        return ":".join(parts)


class CECDelegate:
    """CEC communication using python-cec library"""

    def __init__(self):
        self.logger = logging.getLogger('CECDelegate')
        self._cec = None
        self._callbacks = []

    def init(self) -> bool:
        """Initialize the CEC adapter"""
        try:
            import cec
            self._cec = cec

            # Initialize CEC
            self._cec.init()
            self.logger.info("CEC adapter initialized successfully")

            # Register internal callback to dispatch to our handlers
            self._cec.add_callback(self._on_cec_command, self._cec.EVENT_COMMAND)

            return True
        except ImportError:
            self.logger.error("python3-cec library not found. Install with: sudo apt install python3-cec")
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize CEC: {e}")
            return False

    def transmit(self, destination: int, opcode: int, params: bytes = b'') -> bool:
        """Transmit a CEC command"""
        if self._cec is None:
            self.logger.error("CEC not initialized")
            return False

        try:
            # Format for logging
            cmd_str = CECCommand(0, destination, opcode, params)  # 0 is placeholder for source
            self.logger.debug(f"TX: {cmd_str}")

            # Transmit via python-cec
            self._cec.transmit(destination, opcode, params)
            return True
        except Exception as e:
            self.logger.error(f"Failed to transmit CEC command: {e}")
            return False

    def add_callback(self, handler: Callable[[CECCommand], None]) -> None:
        """Register a callback for received CEC commands"""
        self._callbacks.append(handler)

    def _on_cec_command(self, cmd):
        """Internal callback from python-cec library"""
        try:
            # Convert to our CECCommand format
            cec_cmd = CECCommand(
                initiator=cmd.initiator,
                destination=cmd.destination,
                opcode=cmd.opcode,
                parameters=bytes(cmd.parameters) if hasattr(cmd, 'parameters') else b''
            )

            self.logger.debug(f"RX: {cec_cmd}")

            # Dispatch to all registered callbacks
            for handler in self._callbacks:
                try:
                    handler(cec_cmd)
                except Exception as e:
                    self.logger.error(f"Error in CEC callback handler: {e}")
        except Exception as e:
            self.logger.error(f"Error processing CEC command: {e}")

    def close(self) -> None:
        """Close the CEC adapter"""
        if self._cec is not None:
            try:
                self._cec.close()
                self.logger.info("CEC adapter closed")
            except Exception as e:
                self.logger.error(f"Error closing CEC adapter: {e}")
