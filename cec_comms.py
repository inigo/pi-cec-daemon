import logging
from typing import Callable
from abc import ABC, abstractmethod


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


class CECComms(ABC):
    """Abstract interface for CEC communication"""

    @abstractmethod
    def init(self, on_command: Callable[[str], int]) -> bool:
        pass

    @abstractmethod
    def transmit(self, command: CECCommand) -> bool:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


class RealCECComms(CECComms):
    """Real CEC communication using libcec Python bindings"""

    def __init__(self):
        self.logger = logging.getLogger('RealCECComms')
        self._cec = None
        self._lib = None
        self._config = None
        self._on_command_callback = None

    def init(self, on_command: Callable[[str], int]) -> bool:
        """Initialize the CEC adapter"""
        self._on_command_callback = on_command

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
            self._config.SetCommandCallback(self._on_libcec_command)

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

    def transmit(self, command: CECCommand) -> bool:
        """Transmit a CEC command"""
        if self._lib is None:
            self.logger.error("CEC not initialized")
            return False

        try:
            # Get the command string from the CECCommand
            cmd_string = command.command_string

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

    def close(self) -> None:
        """Close the CEC adapter"""
        if self._lib is not None:
            try:
                self._lib.Close()
                self.logger.info("CEC adapter closed")
            except Exception as e:
                self.logger.error(f"Error closing CEC adapter: {e}")

    def _on_libcec_command(self, cmd_string: str) -> int:
        """Internal callback from libcec - forwards to event bus"""
        if self._on_command_callback:
            return self._on_command_callback(cmd_string)
        return 0


class MockCECComms(CECComms):
    """Mock CEC communication for testing"""

    def __init__(self):
        self.logger = logging.getLogger('MockCECComms')
        self._on_command_callback = None
        self._initialized = False
        self.transmitted_commands = []

    def init(self, on_command: Callable[[str], int]) -> bool:
        """Initialize mock CEC"""
        self._on_command_callback = on_command
        self._initialized = True
        self.logger.info("Mock CEC initialized")
        return True

    def transmit(self, command: CECCommand) -> bool:
        """Record transmitted command"""
        if not self._initialized:
            self.logger.error("Mock CEC not initialized")
            return False

        # Get command string from the CECCommand
        cmd_string = command.command_string

        self.transmitted_commands.append(cmd_string)
        self.logger.debug(f"Mock TX: {cmd_string}")
        return True

    def close(self) -> None:
        """Close mock CEC"""
        self._initialized = False
        self.logger.info("Mock CEC closed")

    def simulate_received_command(self, cmd_string: str) -> None:
        """Simulate receiving a CEC command (for testing)"""
        if self._on_command_callback:
            self._on_command_callback(cmd_string)
