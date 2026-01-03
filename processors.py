import logging
import time

from cec_comms import CECCommand
from with_timeout import with_timeout
from constants import PowerStatus, CECOpcode, UserControlCode


class Addresses:
    """CEC device addresses used by processors"""
    def __init__(self):
        # Logical addresses
        self.tv = 0
        self.pi = 1
        self.switch = 4
        self.soundbar = 5
        self.chromecast = 8

        # Special addresses
        self.broadcast = 0x0F

        # Physical addresses
        self.chromecast_physical = b'\x30\x00'  # HDMI 3 physical address


@with_timeout(5.0)
def TurnSoundbarOnProcessor(addresses):
    """
    Processor that turns on the soundbar if it's off.

    Checks soundbar status and sends power toggle if needed, then terminates.

    Args:
        addresses: Addresses instance containing CEC device addresses
    """
    logger = logging.getLogger('TurnSoundbarOnProcessor')

    # Check soundbar status
    logger.info("Checking soundbar power status")
    cmd = yield [CECCommand.build(destination=addresses.soundbar, opcode=CECOpcode.GIVE_DEVICE_POWER_STATUS)]

    # Wait for soundbar power status response
    while cmd.initiator != addresses.soundbar or cmd.opcode != CECOpcode.REPORT_POWER_STATUS:
        cmd = yield []

    soundbar_status = cmd.parameters[0] if cmd.parameters else PowerStatus.STANDBY
    logger.info(f"Soundbar status: 0x{soundbar_status:02X} ({'ON' if soundbar_status == PowerStatus.ON else 'STANDBY'})")

    # If soundbar is off, turn it on
    if soundbar_status == PowerStatus.STANDBY:
        logger.info("Soundbar is off, sending power toggle")
        yield [
            CECCommand.build(destination=addresses.soundbar, opcode=CECOpcode.USER_CONTROL_PRESSED, parameters=bytes([UserControlCode.POWER])),
            CECCommand.build(destination=addresses.soundbar, opcode=CECOpcode.USER_CONTROL_RELEASE),
            None  # Signal termination
        ]
        logger.info("Sent power toggle to soundbar")
    else:
        logger.info("Soundbar is already on")


@with_timeout(5.0)
def SoundbarOnWithTvProcessor(eventbus, addresses):
    """
    Processor that ensures soundbar is on when TV is on.

    Steps:
    1. Check if TV is on
    2. If TV is on, spawn TurnSoundbarOnProcessor

    Args:
        eventbus: Reference to CECEventBus for spawning processors
        addresses: Addresses instance containing CEC device addresses
    """
    logger = logging.getLogger('SoundbarOnWithTvProcessor')

    # Check TV power status
    logger.info("Checking TV power status")
    cmd = yield [CECCommand.build(destination=addresses.tv, opcode=CECOpcode.GIVE_DEVICE_POWER_STATUS)]

    # Wait for TV power status response
    while cmd.initiator != addresses.tv or cmd.opcode != CECOpcode.REPORT_POWER_STATUS:
        cmd = yield []

    tv_status = cmd.parameters[0] if cmd.parameters else PowerStatus.STANDBY
    logger.info(f"TV status: 0x{tv_status:02X} ({'ON' if tv_status == PowerStatus.ON else 'STANDBY'})")

    # If TV is on, spawn TurnSoundbarOnProcessor
    if tv_status == PowerStatus.ON:
        logger.info("TV is on, spawning TurnSoundbarOnProcessor")
        eventbus.add_processor(TurnSoundbarOnProcessor(addresses))
    else:
        logger.info("TV is off, nothing to do")


def SwitchStatusProcessor(eventbus, addresses):
    """
    Processor that monitors Switch status and switches to Chromecast when Switch turns off.

    Steps:
    1. Initially check if Switch is on
    2. While Switch is on: poll every 5 seconds to detect when it turns off
    3. While Switch is off: poll every 60 seconds and watch for ACTIVE_SOURCE to detect when it turns on
    4. When Switch turns off: switch active source to Chromecast

    Args:
        eventbus: Reference to CECEventBus for spawning processors
        addresses: Addresses instance containing CEC device addresses
    """
    logger = logging.getLogger('SwitchStatusProcessor')

    # Timing constants
    POLL_INTERVAL_ON = 5.0   # Poll every 5 seconds when Switch is on
    POLL_INTERVAL_OFF = 60.0  # Poll every 60 seconds when Switch is off
    POLL_TIMEOUT = 2.0        # Wait 2 seconds for poll response

    # State tracking
    switch_is_on = False
    last_poll_time = 0
    waiting_for_poll_response = False
    poll_start_time = 0

    # Step 1: Initial status check
    logger.info("Checking initial Switch status")
    cmd = yield [CECCommand.build(destination=addresses.switch, opcode=CECOpcode.GIVE_DEVICE_POWER_STATUS)]
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
                    destination=addresses.broadcast,
                    opcode=CECOpcode.SET_STREAM_PATH,
                    parameters=addresses.chromecast_physical
                )]
                continue

        # Process incoming command
        if cmd.initiator == addresses.switch:
            # Check for ACTIVE_SOURCE broadcast (Switch turned on)
            if cmd.opcode == CECOpcode.ACTIVE_SOURCE:
                if not switch_is_on:
                    logger.info("Switch turned on (ACTIVE_SOURCE detected)")
                    switch_is_on = True
                    last_poll_time = current_time
                    waiting_for_poll_response = False
                    # Spawn TurnSoundbarOnProcessor
                    logger.info("Spawning TurnSoundbarOnProcessor")
                    eventbus.add_processor(TurnSoundbarOnProcessor(addresses))

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
                            # Spawn TurnSoundbarOnProcessor
                            logger.info("Spawning TurnSoundbarOnProcessor")
                            eventbus.add_processor(TurnSoundbarOnProcessor(addresses))
                    else:
                        # Switch reported non-ON status
                        if switch_is_on:
                            logger.info("Switch turned off (status report)")
                            switch_is_on = False
                            logger.info("Switching active source to Chromecast")
                            cmd = yield [CECCommand.build(
                                destination=addresses.broadcast,
                                opcode=CECOpcode.SET_STREAM_PATH,
                                parameters=addresses.chromecast_physical
                            )]
                            continue

        # Send periodic poll if not waiting for response
        if not waiting_for_poll_response:
            poll_interval = POLL_INTERVAL_ON if switch_is_on else POLL_INTERVAL_OFF
            if (current_time - last_poll_time) >= poll_interval:
                if switch_is_on:
                    logger.debug("Polling Switch status (on)")
                else:
                    logger.debug("Polling Switch status (periodic check while off)")
                cmd = yield [CECCommand.build(destination=addresses.switch, opcode=CECOpcode.GIVE_DEVICE_POWER_STATUS)]
                last_poll_time = current_time
                waiting_for_poll_response = True
                poll_start_time = current_time
                continue

        # Wait for next event
        cmd = yield []


