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
    """CEC communication using libcec Python bindings"""

    def __init__(self):
        self.logger = logging.getLogger('CECDelegate')
        self._cec = None
        self._lib = None
        self._config = None
        self._callbacks = []

    def init(self) -> bool:
        """Initialize the CEC adapter"""
        try:
            import cec
            self._cec = cec

            # Create configuration
            self._config = cec.libcec_configuration()
            self._config.strDeviceName = "PiCEC"
            self._config.bActivateSource = 0
            self._config.deviceTypes.Add(cec.CEC_DEVICE_TYPE_RECORDING_DEVICE)
            self._config.clientVersion = cec.LIBCEC_VERSION_CURRENT

            # Set command callback
            self._config.SetCommandCallback(self._on_cec_command_internal)

            # Create adapter
            self._lib = cec.ICECAdapter.Create(self._config)
            if not self._lib:
                self.logger.error("Failed to create CEC adapter")
                return False

            self.logger.info(f"libCEC version {self._lib.VersionToString(self._config.serverVersion)} loaded")

            # Detect and open adapter
            adapters = self._lib.DetectAdapters()
            if not adapters or len(adapters) == 0:
                self.logger.error("No CEC adapters found")
                return False

            adapter = adapters[0]
            self.logger.info(f"Found CEC adapter on port: {adapter.strComName}")

            if not self._lib.Open(adapter.strComName):
                self.logger.error("Failed to open connection to CEC adapter")
                return False

            self.logger.info("CEC adapter initialized successfully")
            return True

        except ImportError:
            self.logger.error("libcec Python bindings not found. See README.md for installation instructions")
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize CEC: {e}")
            return False

    def transmit(self, destination: int, opcode: int, params: bytes = b'') -> bool:
        """Transmit a CEC command"""
        if self._lib is None:
            self.logger.error("CEC not initialized")
            return False

        try:
            # Build command as hex string for CommandFromString
            # Format: "XX:YY:ZZ..." where XX is (source << 4 | destination)
            # Source address is our logical address (usually 1 for recording device)
            addresses = self._lib.GetLogicalAddresses()
            source = 1  # Default to CECDEVICE_RECORDINGDEVICE1

            # Find our actual logical address
            for i in range(15):
                if addresses.IsSet(i):
                    source = i
                    break

            first_byte = (source << 4) | destination
            cmd_parts = [f"{first_byte:02X}", f"{opcode:02X}"]
            if params:
                cmd_parts.extend([f"{b:02X}" for b in params])
            cmd_string = ":".join(cmd_parts)

            # Create command from string
            cmd = self._lib.CommandFromString(cmd_string)

            # Log for debugging
            self.logger.debug(f"TX: {cmd_string}")

            # Transmit
            if self._lib.Transmit(cmd):
                return True
            else:
                # Log as debug - failure is expected when device is off/unreachable
                self.logger.debug(f"Failed to transmit CEC command: {cmd_string}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to transmit CEC command: {e}")
            return False

    def add_callback(self, handler: Callable[[CECCommand], None]) -> None:
        """Register a callback for received CEC commands"""
        self._callbacks.append(handler)

    def _on_cec_command_internal(self, cmd_string):
        """Internal callback from libcec"""
        try:
            # Parse the command string (format: "XX:YY:ZZ..." where XX is initiator+destination)
            if not cmd_string or cmd_string.startswith(">>"):
                # Strip the ">>" prefix if present
                cmd_string = cmd_string.strip().lstrip(">").strip()

            parts = cmd_string.split(':')
            if len(parts) < 2:
                self.logger.warning(f"Invalid CEC command format: {cmd_string}")
                return 0

            # Parse first byte: high nibble = initiator, low nibble = destination
            first_byte = int(parts[0], 16)
            initiator = (first_byte >> 4) & 0xF
            destination = first_byte & 0xF

            # Parse opcode (second byte)
            opcode = int(parts[1], 16)

            # Parse parameters (remaining bytes)
            parameters = bytes([int(p, 16) for p in parts[2:]]) if len(parts) > 2 else b''

            # Create CECCommand object
            cec_cmd = CECCommand(
                initiator=initiator,
                destination=destination,
                opcode=opcode,
                parameters=parameters
            )

            self.logger.debug(f"RX: {cec_cmd}")

            # Dispatch to all registered callbacks
            for handler in self._callbacks:
                try:
                    handler(cec_cmd)
                except Exception as e:
                    self.logger.error(f"Error in CEC callback handler: {e}")

            return 0  # Callback should return 0

        except Exception as e:
            self.logger.error(f"Error processing CEC command '{cmd_string}': {e}")
            return 0

    def close(self) -> None:
        """Close the CEC adapter"""
        if self._lib is not None:
            try:
                self._lib.Close()
                self.logger.info("CEC adapter closed")
            except Exception as e:
                self.logger.error(f"Error closing CEC adapter: {e}")
