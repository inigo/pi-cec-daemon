"""
CEC Delegate Layer - Low-level CEC transmit/receive interface

Provides an abstraction over libcec for HDMI CEC communication.
"""

import logging
from typing import Callable


class CECCommand:
    """Represents a received CEC command"""
    def __init__(self, command_string: str):
        # Store the original command string
        self._command_string = command_string.strip()

        # Parse the command string (format: "XX:YY:ZZ..." where XX is initiator+destination)
        parts = self._command_string.split(':')
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

    def __str__(self):
        """Return the original command string"""
        return self._command_string


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
        """Close the CEC adapter"""
        if self._lib is not None:
            try:
                self._lib.Close()
                self.logger.info("CEC adapter closed")
            except Exception as e:
                self.logger.error(f"Error closing CEC adapter: {e}")
