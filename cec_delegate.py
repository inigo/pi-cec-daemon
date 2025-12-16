"""
CEC Delegate Layer - Low-level CEC transmit/receive interface

Provides an abstraction over libcec with both real and mock implementations.
"""

import logging
from abc import ABC, abstractmethod
from typing import Callable, Optional


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

    @classmethod
    def from_hex_string(cls, hex_string: str) -> 'CECCommand':
        """Parse a hex string like '0F:87:00:E0:91' into a CECCommand"""
        parts = hex_string.split(':')
        if len(parts) < 2:
            raise ValueError(f"Invalid CEC command format: {hex_string}")

        first_byte = int(parts[0], 16)
        initiator = (first_byte >> 4) & 0xF
        destination = first_byte & 0xF
        opcode = int(parts[1], 16)
        parameters = bytes([int(p, 16) for p in parts[2:]]) if len(parts) > 2 else b''

        return cls(initiator, destination, opcode, parameters)


class CECDelegate(ABC):
    """Abstract base class for CEC communication"""

    @abstractmethod
    def init(self) -> bool:
        """
        Initialize the CEC adapter.

        Returns:
            True if initialization was successful, False otherwise
        """
        pass

    @abstractmethod
    def transmit(self, destination: int, opcode: int, params: bytes = b'') -> bool:
        """
        Transmit a CEC command.

        Args:
            destination: Logical address of destination device (0-15)
            opcode: CEC opcode byte
            params: Parameter bytes (optional)

        Returns:
            True if transmission was successful, False otherwise
        """
        pass

    @abstractmethod
    def add_callback(self, handler: Callable[[CECCommand], None]) -> None:
        """
        Register a callback for received CEC commands.

        Args:
            handler: Function that takes a CECCommand object
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the CEC adapter and cleanup resources"""
        pass


class RealCECDelegate(CECDelegate):
    """Real CEC implementation using python-cec library"""

    def __init__(self):
        self.logger = logging.getLogger('RealCECDelegate')
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
            self.logger.error("python-cec library not found. Install with: pip install cec")
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


class MockCECDelegate(CECDelegate):
    """Mock CEC implementation for development without hardware"""

    def __init__(self):
        self.logger = logging.getLogger('MockCECDelegate')
        self._callbacks = []
        self._initialized = False

    def init(self) -> bool:
        """Initialize the mock CEC adapter"""
        self.logger.info("[MOCK] CEC adapter initialized (no real hardware)")
        self._initialized = True
        return True

    def transmit(self, destination: int, opcode: int, params: bytes = b'') -> bool:
        """Mock transmit - just log what would be sent"""
        if not self._initialized:
            self.logger.error("[MOCK] CEC not initialized")
            return False

        # Create command for logging
        cmd = CECCommand(0, destination, opcode, params)  # 0 is placeholder for source
        self.logger.info(f"[MOCK] TX: {cmd}")

        # Simulate some common responses for testing
        self._simulate_response(destination, opcode, params)

        return True

    def _simulate_response(self, destination: int, opcode: int, params: bytes):
        """Simulate CEC responses for common commands"""
        # TV power status request (tx 10:8F -> response 01:90:XX)
        if destination == 0 and opcode == 0x8F:
            # Simulate TV responding with "ON" status
            response = CECCommand(initiator=0, destination=1, opcode=0x90, parameters=b'\x00')
            self.logger.info(f"[MOCK] RX: {response} (simulated TV ON response)")
            for handler in self._callbacks:
                handler(response)

        # Soundbar status request (tx 15:71 -> response 51:7A:XX)
        elif destination == 5 and opcode == 0x71:
            # Simulate soundbar responding with volume 8 (0x10 in CEC)
            response = CECCommand(initiator=5, destination=1, opcode=0x7A, parameters=b'\x10')
            self.logger.info(f"[MOCK] RX: {response} (simulated soundbar volume 8)")
            for handler in self._callbacks:
                handler(response)

    def add_callback(self, handler: Callable[[CECCommand], None]) -> None:
        """Register a callback for received CEC commands"""
        self._callbacks.append(handler)
        self.logger.debug(f"[MOCK] Registered callback: {handler.__name__}")

    def inject_command(self, hex_string: str) -> None:
        """
        Inject a simulated CEC command (for testing).

        Args:
            hex_string: CEC command in hex format like '0F:87:00:E0:91'
        """
        try:
            cmd = CECCommand.from_hex_string(hex_string)
            self.logger.info(f"[MOCK] RX (injected): {cmd}")
            for handler in self._callbacks:
                handler(cmd)
        except Exception as e:
            self.logger.error(f"[MOCK] Failed to inject command '{hex_string}': {e}")

    def close(self) -> None:
        """Close the mock CEC adapter"""
        self.logger.info("[MOCK] CEC adapter closed")
        self._initialized = False


def get_cec_delegate(mock_mode: bool = False) -> CECDelegate:
    """
    Factory function to get the appropriate CEC delegate.

    Args:
        mock_mode: If True, force mock mode even if real CEC is available

    Returns:
        CECDelegate instance (Real or Mock)
    """
    if mock_mode:
        return MockCECDelegate()

    # Try to import cec library
    try:
        import cec
        return RealCECDelegate()
    except ImportError:
        logging.getLogger('CECDelegate').warning(
            "python-cec library not available, using mock mode. "
            "Install with: pip install cec"
        )
        return MockCECDelegate()
