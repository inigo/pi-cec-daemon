import logging

from cec_comms import CECCommand
from cec_delegate import with_timeout


@with_timeout(5.0)
def SoundbarOnWithTv():
    """
    Processor that ensures soundbar is on when TV is on.

    Steps:
    1. Check if TV is on
    2. If TV is on, check if soundbar is on
    3. If soundbar is off, turn it on
    """
    logger = logging.getLogger('SoundbarOnWithTv')

    # CEC addresses
    TV_ADDRESS = 0
    SOUNDBAR_ADDRESS = 5

    # CEC opcodes
    GIVE_DEVICE_POWER_STATUS = 0x8F
    REPORT_POWER_STATUS = 0x90
    USER_CONTROL_PRESSED = 0x44
    USER_CONTROL_RELEASE = 0x45

    # Power status values
    POWER_ON = 0x00
    POWER_STANDBY = 0x01

    # User control codes
    POWER_BUTTON = 0x40

    # Step 1: Check TV power status
    logger.info("Checking TV power status")
    cmd = yield [CECCommand.build(destination=TV_ADDRESS, opcode=GIVE_DEVICE_POWER_STATUS)]

    # Wait for TV power status response
    while cmd.initiator != TV_ADDRESS or cmd.opcode != REPORT_POWER_STATUS:
        cmd = yield []

    tv_status = cmd.parameters[0] if cmd.parameters else POWER_STANDBY
    logger.info(f"TV status: 0x{tv_status:02X} ({'ON' if tv_status == POWER_ON else 'STANDBY'})")

    # If TV is not on, we're done
    if tv_status != POWER_ON:
        logger.info("TV is off, nothing to do")
        yield [None]
        return

    # Step 2: TV is on, check soundbar status
    logger.info("TV is on, checking soundbar power status")
    cmd = yield [CECCommand.build(destination=SOUNDBAR_ADDRESS, opcode=GIVE_DEVICE_POWER_STATUS)]

    # Wait for soundbar power status response
    while cmd.initiator != SOUNDBAR_ADDRESS or cmd.opcode != REPORT_POWER_STATUS:
        cmd = yield []

    soundbar_status = cmd.parameters[0] if cmd.parameters else POWER_STANDBY
    logger.info(f"Soundbar status: 0x{soundbar_status:02X} ({'ON' if soundbar_status == POWER_ON else 'STANDBY'})")

    # Step 3: If soundbar is off, turn it on
    if soundbar_status == POWER_STANDBY:
        logger.info("Soundbar is off, sending power toggle")
        yield [
            CECCommand.build(destination=SOUNDBAR_ADDRESS, opcode=USER_CONTROL_PRESSED, parameters=bytes([POWER_BUTTON])),
            CECCommand.build(destination=SOUNDBAR_ADDRESS, opcode=USER_CONTROL_RELEASE),
            None  # Signal termination
        ]
        logger.info("Sent power toggle to soundbar")
    else:
        # Soundbar is already on, signal termination
        yield [None]
