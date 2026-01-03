import logging
import time

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


def SwitchStatus():
    """
    Processor that monitors Switch status and switches to Chromecast when Switch turns off.

    Steps:
    1. Initially check if Switch is on
    2. While Switch is on: poll periodically to detect when it turns off
    3. While Switch is off: watch for ACTIVE_SOURCE message indicating it turned on
    4. When Switch turns off: switch active source to Chromecast
    """
    logger = logging.getLogger('SwitchStatus')

    # CEC addresses
    SWITCH_ADDRESS = 4
    BROADCAST_ADDRESS = 0x0F

    # Chromecast physical address (HDMI 3)
    CHROMECAST_PHYSICAL_ADDRESS = b'\x30\x00'

    # Timing constants
    POLL_INTERVAL = 5.0  # Poll every 5 seconds when Switch is on
    POLL_TIMEOUT = 2.0   # Wait 2 seconds for poll response

    # State tracking
    switch_is_on = False
    last_poll_time = 0
    waiting_for_poll_response = False
    poll_start_time = 0

    # Step 1: Initial status check
    logger.info("Checking initial Switch status")
    cmd = yield [CECCommand.build(destination=SWITCH_ADDRESS, opcode=CECOpcode.GIVE_DEVICE_POWER_STATUS)]
    waiting_for_poll_response = True
    poll_start_time = time.time()

    # Main event loop - runs indefinitely
    while True:
        current_time = time.time()

        # Check for timeout on poll response
        if waiting_for_poll_response and (current_time - poll_start_time) >= POLL_TIMEOUT:
            logger.debug("Switch poll timeout - no response")
            waiting_for_poll_response = False

            if switch_is_on:
                # Switch was on but now not responding - it turned off
                logger.info("Switch turned off (poll timeout)")
                switch_is_on = False
                logger.info("Switching active source to Chromecast")
                cmd = yield [CECCommand.build(
                    destination=BROADCAST_ADDRESS,
                    opcode=CECOpcode.SET_STREAM_PATH,
                    parameters=CHROMECAST_PHYSICAL_ADDRESS
                )]
                continue

        # Process incoming command
        if cmd.initiator == SWITCH_ADDRESS:
            # Check for ACTIVE_SOURCE broadcast (Switch turned on)
            if cmd.opcode == CECOpcode.ACTIVE_SOURCE:
                if not switch_is_on:
                    logger.info("Switch turned on (ACTIVE_SOURCE detected)")
                    switch_is_on = True
                    last_poll_time = current_time
                    waiting_for_poll_response = False

            # Check for power status response
            elif cmd.opcode == CECOpcode.REPORT_POWER_STATUS:
                if waiting_for_poll_response:
                    waiting_for_poll_response = False
                    status = cmd.parameters[0] if cmd.parameters else PowerStatus.STANDBY

                    if status == PowerStatus.ON:
                        if not switch_is_on:
                            logger.info("Switch is ON")
                            switch_is_on = True
                            last_poll_time = current_time
                    else:
                        # Switch reported non-ON status
                        if switch_is_on:
                            logger.info("Switch turned off (status report)")
                            switch_is_on = False
                            logger.info("Switching active source to Chromecast")
                            cmd = yield [CECCommand.build(
                                destination=BROADCAST_ADDRESS,
                                opcode=CECOpcode.SET_STREAM_PATH,
                                parameters=CHROMECAST_PHYSICAL_ADDRESS
                            )]
                            continue

        # Send periodic poll if Switch is on and not waiting for response
        if switch_is_on and not waiting_for_poll_response:
            if (current_time - last_poll_time) >= POLL_INTERVAL:
                logger.debug("Polling Switch status")
                cmd = yield [CECCommand.build(destination=SWITCH_ADDRESS, opcode=CECOpcode.GIVE_DEVICE_POWER_STATUS)]
                last_poll_time = current_time
                waiting_for_poll_response = True
                poll_start_time = current_time
                continue

        # Wait for next event
        cmd = yield []
