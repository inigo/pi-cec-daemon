"""
Device Classes - High-level abstractions for CEC devices

Each device class encapsulates the CEC commands specific to that device type.
"""

import logging
from typing import Optional
from enum import IntEnum

from cec_delegate import CECDelegate, CECCommand


class PowerStatus(IntEnum):
    """CEC power status values"""
    ON = 0x00
    STANDBY = 0x01
    IN_TRANSITION_STANDBY = 0x02
    IN_TRANSITION_ON = 0x03


class CECOpcode(IntEnum):
    """Common CEC opcodes"""
    ACTIVE_SOURCE = 0x82
    STANDBY = 0x36
    IMAGE_VIEW_ON = 0x04
    GIVE_DEVICE_POWER_STATUS = 0x8F
    REPORT_POWER_STATUS = 0x90
    USER_CONTROL_PRESSED = 0x44
    USER_CONTROL_RELEASE = 0x45
    GIVE_AUDIO_STATUS = 0x71
    REPORT_AUDIO_STATUS = 0x7A
    SET_STREAM_PATH = 0x86


class UserControlCode(IntEnum):
    """CEC user control codes"""
    VOLUME_UP = 0x41
    VOLUME_DOWN = 0x42


class CECDevice:
    """Base class for CEC devices"""

    def __init__(self, name: str, logical_address: int, delegate: CECDelegate):
        """
        Initialize a CEC device.

        Args:
            name: Human-readable device name (for logging)
            logical_address: CEC logical address (0-15)
            delegate: CEC delegate for communication
        """
        self.name = name
        self.logical_address = logical_address
        self.delegate = delegate
        self.logger = logging.getLogger(f'{self.__class__.__name__}({name})')

    def _transmit(self, opcode: int, params: bytes = b'') -> bool:
        """Helper to transmit to this device"""
        return self.delegate.transmit(self.logical_address, opcode, params)


class TV(CECDevice):
    """TV device (logical address 0)"""

    BROADCAST_ADDRESS = 0x0F

    def __init__(self, logical_address: int, delegate: CECDelegate):
        super().__init__("TV", logical_address, delegate)
        self._last_known_status: Optional[PowerStatus] = None

    def get_power_status(self) -> Optional[PowerStatus]:
        """
        Request TV power status.

        Sends: tx 10:8F
        Expects response: 01:90:XX where XX is power status

        Note: This is async - the response comes via callback.
        Use _last_known_status to get the cached value.

        Returns:
            The last known power status, or None if unknown
        """
        self._transmit(CECOpcode.GIVE_DEVICE_POWER_STATUS)
        return self._last_known_status

    def is_on(self) -> Optional[bool]:
        """
        Check if TV is on based on last known status.

        Returns:
            True if ON, False if STANDBY/OFF, None if unknown
        """
        if self._last_known_status is None:
            return None
        return self._last_known_status == PowerStatus.ON

    def update_power_status(self, status: PowerStatus) -> None:
        """Update the cached power status (called by business logic on response)"""
        old_status = self._last_known_status
        self._last_known_status = status

        if old_status != status:
            self.logger.info(f"Power status changed: {old_status} -> {status.name}")

    def power_off(self) -> bool:
        """
        Turn off the TV.

        Sends: tx 1f:36 (broadcast standby)

        Returns:
            True if command was sent successfully
        """
        # Broadcast to all devices
        result = self.delegate.transmit(self.BROADCAST_ADDRESS, CECOpcode.STANDBY)
        if result:
            self.logger.info("Sent power off command")
        return result


class Soundbar(CECDevice):
    """Soundbar device"""

    def __init__(self, logical_address: int, delegate: CECDelegate):
        super().__init__("Soundbar", logical_address, delegate)
        self._last_known_volume: Optional[int] = None

    def power_on(self) -> bool:
        """
        Turn on the soundbar.

        Sends: tx 15:04 (image view on)

        Returns:
            True if command was sent successfully
        """
        result = self._transmit(CECOpcode.IMAGE_VIEW_ON)
        if result:
            self.logger.info("Sent power on command")
        return result

    def power_off(self) -> bool:
        """
        Turn off the soundbar.

        Sends: tx 15:36 (standby)

        Returns:
            True if command was sent successfully
        """
        result = self._transmit(CECOpcode.STANDBY)
        if result:
            self.logger.info("Sent power off command")
        return result

    def get_volume(self) -> Optional[int]:
        """
        Request current volume from soundbar.

        Sends: tx 15:71
        Expects response: 51:7A:XX where XX is volume in hex

        Note: This is async - the response comes via callback.

        Returns:
            The last known volume (CEC hex value), or None if unknown
        """
        self._transmit(CECOpcode.GIVE_AUDIO_STATUS)
        return self._last_known_volume

    def update_volume(self, volume_cec: int) -> None:
        """Update the cached volume (called by business logic on response)"""
        old_volume = self._last_known_volume
        self._last_known_volume = volume_cec

        if old_volume != volume_cec:
            self.logger.info(f"Volume changed: {old_volume} -> {volume_cec} (0x{volume_cec:02X})")

    def increase_volume(self) -> bool:
        """
        Increase volume by one step.

        Sends: tx 10:44:41 (volume up pressed) then tx 10:45 (release)

        Returns:
            True if commands were sent successfully
        """
        # Send to TV (address 0) as audio system controller
        tv_address = 0
        result1 = self.delegate.transmit(
            tv_address,
            CECOpcode.USER_CONTROL_PRESSED,
            bytes([UserControlCode.VOLUME_UP])
        )
        result2 = self.delegate.transmit(tv_address, CECOpcode.USER_CONTROL_RELEASE)

        if result1 and result2:
            self.logger.debug("Sent volume increase command")
        return result1 and result2

    def decrease_volume(self) -> bool:
        """
        Decrease volume by one step.

        Sends: tx 10:44:42 (volume down pressed) then tx 10:45 (release)

        Returns:
            True if commands were sent successfully
        """
        # Send to TV (address 0) as audio system controller
        tv_address = 0
        result1 = self.delegate.transmit(
            tv_address,
            CECOpcode.USER_CONTROL_PRESSED,
            bytes([UserControlCode.VOLUME_DOWN])
        )
        result2 = self.delegate.transmit(tv_address, CECOpcode.USER_CONTROL_RELEASE)

        if result1 and result2:
            self.logger.debug("Sent volume decrease command")
        return result1 and result2

    def set_volume(self, target_cec: int, current_cec: Optional[int] = None, step: int = 2) -> None:
        """
        Set volume to target value.

        Args:
            target_cec: Target volume in CEC hex value
            current_cec: Current volume (if None, will request it first)
            step: Volume change per increase/decrease command (default 2)
        """
        if current_cec is None:
            current_cec = self._last_known_volume

        if current_cec is None:
            self.logger.warning("Cannot set volume: current volume unknown")
            # Request volume and hope it gets updated
            self.get_volume()
            return

        if current_cec == target_cec:
            self.logger.info(f"Volume already at target: {target_cec} (0x{target_cec:02X})")
            return

        # Calculate how many steps we need (use ceiling division to avoid being off-by-one)
        diff = target_cec - current_cec
        steps = (abs(diff) + step - 1) // step  # Ceiling division

        if diff > 0:
            self.logger.info(f"Increasing volume from {current_cec} to {target_cec} ({steps} steps)")
            for _ in range(steps):
                self.increase_volume()
        else:
            self.logger.info(f"Decreasing volume from {current_cec} to {target_cec} ({steps} steps)")
            for _ in range(steps):
                self.decrease_volume()


class Switch(CECDevice):
    """Nintendo Switch device"""

    def __init__(self, logical_address: int, delegate: CECDelegate):
        super().__init__("Switch", logical_address, delegate)
        self._is_active = False

    def get_power_status(self) -> bool:
        """
        Request Switch power status.

        Sends: tx 14:8F (request power status from Switch)
        Expects response: 41:90:XX where XX is power status

        Note: This is async - the response comes via callback.

        Returns:
            True if command was sent successfully, False otherwise
        """
        return self._transmit(CECOpcode.GIVE_DEVICE_POWER_STATUS)

    def update_active_source(self, is_active: bool) -> None:
        """Update whether this device is the active source"""
        if self._is_active != is_active:
            self._is_active = is_active
            status = "active" if is_active else "inactive"
            self.logger.info(f"Switch is now {status}")

    def is_active_source(self) -> bool:
        """Check if Switch is currently the active source"""
        return self._is_active


class Chromecast(CECDevice):
    """Google Chromecast device"""

    def __init__(self, logical_address: int, delegate: CECDelegate):
        super().__init__("Chromecast", logical_address, delegate)

    def make_active_source(self) -> bool:
        """
        Make Chromecast the active source.

        Sends: tx 1f:86:30:00 (set stream path to HDMI 3.0.0.0)

        Returns:
            True if command was sent successfully
        """
        # Physical address 3.0.0.0 = 0x3000
        # Broadcast to all devices (0x0F)
        broadcast_address = 0x0F
        result = self.delegate.transmit(
            broadcast_address,
            CECOpcode.SET_STREAM_PATH,
            b'\x30\x00'  # Physical address 3.0.0.0
        )
        if result:
            self.logger.info("Set Chromecast as active source")
        return result
