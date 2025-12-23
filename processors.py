import logging

from cec_comms import CECCommand
from cec_delegate import with_timeout
from devices import PowerStatus, CECOpcode, UserControlCode


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

    # Step 1: Check TV power status
    logger.info("Checking TV power status")
    cmd = yield [CECCommand.build(destination=TV_ADDRESS, opcode=CECOpcode.GIVE_DEVICE_POWER_STATUS)]

    # Wait for TV power status response
    while cmd.initiator != TV_ADDRESS or cmd.opcode != CECOpcode.REPORT_POWER_STATUS:
        cmd = yield []

    tv_status = cmd.parameters[0] if cmd.parameters else PowerStatus.STANDBY
    logger.info(f"TV status: 0x{tv_status:02X} ({'ON' if tv_status == PowerStatus.ON else 'STANDBY'})")

    # If TV is not on, we're done
    if tv_status != PowerStatus.ON:
        logger.info("TV is off, nothing to do")
        return

    # Step 2: TV is on, check soundbar status
    logger.info("TV is on, checking soundbar power status")
    cmd = yield [CECCommand.build(destination=SOUNDBAR_ADDRESS, opcode=CECOpcode.GIVE_DEVICE_POWER_STATUS)]

    # Wait for soundbar power status response
    while cmd.initiator != SOUNDBAR_ADDRESS or cmd.opcode != CECOpcode.REPORT_POWER_STATUS:
        cmd = yield []

    soundbar_status = cmd.parameters[0] if cmd.parameters else PowerStatus.STANDBY
    logger.info(f"Soundbar status: 0x{soundbar_status:02X} ({'ON' if soundbar_status == PowerStatus.ON else 'STANDBY'})")

    # Step 3: If soundbar is off, turn it on
    if soundbar_status == PowerStatus.STANDBY:
        logger.info("Soundbar is off, sending power toggle")
        yield [
            CECCommand.build(destination=SOUNDBAR_ADDRESS, opcode=CECOpcode.USER_CONTROL_PRESSED, parameters=bytes([UserControlCode.POWER])),
            CECCommand.build(destination=SOUNDBAR_ADDRESS, opcode=CECOpcode.USER_CONTROL_RELEASE),
            None  # Signal termination
        ]
        logger.info("Sent power toggle to soundbar")
