from cec_comms import MockCECComms
from cec_delegate import CECEventBus
from processors import SoundbarOnWithTv


class TestSoundbarOnWithTv:
    """Test SoundbarOnWithTv processor"""

    def test_tv_on_soundbar_off_turns_on_soundbar(self):
        """Test that soundbar is turned on when TV is on and soundbar is off"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        bus.add_processor(SoundbarOnWithTv())

        # Should send TV power status request
        assert len(mock.transmitted_commands) == 1
        assert mock.transmitted_commands[0] == "10:8F"  # Request TV power status

        # Simulate TV is ON
        mock.simulate_received_command("01:90:00")  # TV reports ON

        # Should send soundbar power status request
        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[1] == "15:8F"  # Request soundbar power status

        # Simulate soundbar is OFF (STANDBY)
        mock.simulate_received_command("51:90:01")  # Soundbar reports STANDBY

        # Should send power toggle to soundbar
        assert len(mock.transmitted_commands) == 4
        assert mock.transmitted_commands[2] == "15:44:40"  # USER_CONTROL_PRESSED (POWER)
        assert mock.transmitted_commands[3] == "15:45"  # USER_CONTROL_RELEASE

        # Processor should be done (terminated via None in command list)
        assert len(bus._processors) == 0

    def test_tv_on_soundbar_already_on_does_nothing(self):
        """Test that nothing happens when both TV and soundbar are already on"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        bus.add_processor(SoundbarOnWithTv())

        # TV power status request
        assert mock.transmitted_commands[0] == "10:8F"

        # Simulate TV is ON
        mock.simulate_received_command("01:90:00")

        # Soundbar power status request
        assert mock.transmitted_commands[1] == "15:8F"

        # Simulate soundbar is already ON
        mock.simulate_received_command("51:90:00")  # Soundbar reports ON

        # Should NOT send power toggle
        assert len(mock.transmitted_commands) == 2

        # Processor should be done
        assert len(bus._processors) == 0

    def test_tv_off_does_nothing(self):
        """Test that nothing happens when TV is off"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        bus.add_processor(SoundbarOnWithTv())

        # TV power status request
        assert mock.transmitted_commands[0] == "10:8F"

        # Simulate TV is OFF (STANDBY)
        mock.simulate_received_command("01:90:01")  # TV reports STANDBY

        # Should NOT request soundbar status or send any more commands
        assert len(mock.transmitted_commands) == 1

        # Processor should be done
        assert len(bus._processors) == 0

    def test_filters_unrelated_traffic(self):
        """Test that processor filters out unrelated CEC traffic"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        bus.add_processor(SoundbarOnWithTv())

        # TV power status request sent
        assert mock.transmitted_commands[0] == "10:8F"

        # Simulate unrelated traffic
        mock.simulate_received_command("4F:82:10:00")  # Switch active source
        mock.simulate_received_command("0F:87:00:E0:91")  # TV vendor ID

        # Should still be waiting for TV response
        assert len(mock.transmitted_commands) == 1

        # Now send TV response
        mock.simulate_received_command("01:90:00")  # TV ON

        # Should have requested soundbar status
        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[1] == "15:8F"

        # More unrelated traffic
        mock.simulate_received_command("4F:82:10:00")

        # Still waiting for soundbar response
        assert len(mock.transmitted_commands) == 2

        # Soundbar responds
        mock.simulate_received_command("51:90:01")  # Soundbar STANDBY

        # Power toggle sent
        assert len(mock.transmitted_commands) == 4

        # Processor done (terminated via None in command list)
        assert len(bus._processors) == 0
