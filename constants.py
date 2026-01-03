from enum import IntEnum

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
    POWER = 0x40
    VOLUME_UP = 0x41
    VOLUME_DOWN = 0x42
