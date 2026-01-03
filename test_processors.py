import time
from unittest.mock import patch, Mock
import pytest

from cec_comms import MockCECComms
from cec_delegate import CECEventBus
from processors import Addresses, TurnSoundbarOnProcessor, SoundbarOnWithTvProcessor, SwitchStatusProcessor


@pytest.fixture
def addresses():
    """Fixture providing Addresses instance for all tests"""
    return Addresses()


class TestSoundbarOnWithTvProcessor:
    """Test SoundbarOnWithTvProcessor"""

    def test_tv_on_soundbar_off_turns_on_soundbar(self, addresses):
        """Test that soundbar is turned on when TV is on and soundbar is off"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        bus.add_processor(SoundbarOnWithTvProcessor(bus, addresses))

        # Should send TV power status request
        assert len(mock.transmitted_commands) == 1
        assert mock.transmitted_commands[0] == "10:8F"  # Request TV power status

        # Simulate TV is ON
        mock.simulate_received_command("01:90:00")  # TV reports ON

        # SoundbarOnWithTvProcessor should be done, TurnSoundbarOnProcessor should be spawned
        # TurnSoundbarOnProcessor should send soundbar power status request
        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[1] == "15:8F"  # Request soundbar power status

        # Simulate soundbar is OFF (STANDBY)
        mock.simulate_received_command("51:90:01")  # Soundbar reports STANDBY

        # Should send power toggle to soundbar
        assert len(mock.transmitted_commands) == 4
        assert mock.transmitted_commands[2] == "15:44:40"  # USER_CONTROL_PRESSED (POWER)
        assert mock.transmitted_commands[3] == "15:45"  # USER_CONTROL_RELEASE

        # All processors should be done
        assert len(bus._processors) == 0

    def test_tv_on_soundbar_already_on_does_nothing(self, addresses):
        """Test that nothing happens when both TV and soundbar are already on"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        bus.add_processor(SoundbarOnWithTvProcessor(bus, addresses))

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

    def test_tv_off_does_nothing(self, addresses):
        """Test that nothing happens when TV is off"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        bus.add_processor(SoundbarOnWithTvProcessor(bus, addresses))

        # TV power status request
        assert mock.transmitted_commands[0] == "10:8F"

        # Simulate TV is OFF (STANDBY)
        mock.simulate_received_command("01:90:01")  # TV reports STANDBY

        # Should NOT request soundbar status or send any more commands
        assert len(mock.transmitted_commands) == 1

        # Processor should be done
        assert len(bus._processors) == 0

    def test_filters_unrelated_traffic(self, addresses):
        """Test that processor filters out unrelated CEC traffic"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        bus.add_processor(SoundbarOnWithTvProcessor(bus, addresses))

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


class TestSwitchStatusProcessor:
    """Test SwitchStatusProcessor"""

    def test_switch_initially_off(self, addresses):
        """Test that processor correctly handles Switch being initially off"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        with patch('time.time', return_value=1000.0):
            bus.add_processor(SwitchStatusProcessor(bus, addresses))

        # Should send initial status request
        assert len(mock.transmitted_commands) == 1
        assert mock.transmitted_commands[0] == "14:8F"  # Request Switch power status

        # Simulate no response (timeout) - advance time past timeout
        with patch('time.time', return_value=1002.5):  # 2.5 seconds later (past 2.0s timeout)
            mock.simulate_received_command("01:90:00")  # Any unrelated command to trigger processing

        # Should not send Chromecast switch command (Switch wasn't on)
        assert len(mock.transmitted_commands) == 1

        # Processor should still be active
        assert len(bus._processors) == 1

    def test_switch_initially_on(self, addresses):
        """Test that processor correctly handles Switch being initially on"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        # Mock add_processor to prevent spawning TurnSoundbarOnProcessor
        original_add_processor = bus.add_processor
        mock_add_processor = Mock()

        with patch('time.time', return_value=1000.0):
            bus.add_processor = original_add_processor
            bus.add_processor(SwitchStatusProcessor(bus, addresses))
            bus.add_processor = mock_add_processor

        # Should send initial status request
        assert mock.transmitted_commands[0] == "14:8F"

        # Simulate Switch responding as ON
        with patch('time.time', return_value=1000.5):
            mock.simulate_received_command("41:90:00")  # Switch reports ON

        # Should have called add_processor to spawn TurnSoundbarOnProcessor
        assert mock_add_processor.call_count == 1

        # Should not send any more commands (TurnSoundbarOnProcessor was mocked)
        assert len(mock.transmitted_commands) == 1

        # Only SwitchStatusProcessor should be active
        assert len(bus._processors) == 1

    def test_switch_turns_on_via_active_source(self, addresses):
        """Test Switch turning on via ACTIVE_SOURCE broadcast"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        # Mock add_processor to prevent spawning TurnSoundbarOnProcessor
        original_add_processor = bus.add_processor
        mock_add_processor = Mock()

        with patch('time.time', return_value=1000.0):
            bus.add_processor = original_add_processor
            bus.add_processor(SwitchStatusProcessor(bus, addresses))
            bus.add_processor = mock_add_processor

        # Initial status request
        assert mock.transmitted_commands[0] == "14:8F"

        # Simulate timeout (Switch is off)
        with patch('time.time', return_value=1002.5):
            mock.simulate_received_command("01:90:00")  # Unrelated command

        # Now simulate Switch broadcasting ACTIVE_SOURCE
        with patch('time.time', return_value=1010.0):
            mock.simulate_received_command("4F:82:10:00")  # Switch ACTIVE_SOURCE

        # Should have called add_processor to spawn TurnSoundbarOnProcessor
        assert mock_add_processor.call_count == 1

        # Should not send any more commands (TurnSoundbarOnProcessor was mocked)
        assert len(mock.transmitted_commands) == 1

    def test_switch_turns_off_via_poll_timeout(self, addresses):
        """Test Switch turning off detected via poll timeout"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        # Mock add_processor to prevent spawning TurnSoundbarOnProcessor
        original_add_processor = bus.add_processor
        mock_add_processor = Mock()

        # Start with Switch on
        with patch('time.time', return_value=1000.0):
            bus.add_processor = original_add_processor
            bus.add_processor(SwitchStatusProcessor(bus, addresses))
            bus.add_processor = mock_add_processor

        # Initial status request
        assert mock.transmitted_commands[0] == "14:8F"

        # Simulate Switch responding as ON
        with patch('time.time', return_value=1000.5):
            mock.simulate_received_command("41:90:00")  # Switch reports ON

        # Should have spawned TurnSoundbarOnProcessor
        assert mock_add_processor.call_count == 1

        # Advance time to trigger first poll
        with patch('time.time', return_value=1005.5):  # 5 seconds later
            mock.simulate_received_command("01:90:00")  # Unrelated event to trigger processing

        # Should have sent a poll
        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[1] == "14:8F"  # Poll Switch status

        # Simulate poll timeout (no response) - advance past timeout
        with patch('time.time', return_value=1008.0):  # 2.5 seconds after poll
            mock.simulate_received_command("01:90:00")  # Unrelated event

        # Should have sent Chromecast switch command
        assert len(mock.transmitted_commands) == 3
        assert mock.transmitted_commands[2] == "1F:86:30:00"  # SET_STREAM_PATH to Chromecast

    def test_switch_turns_off_via_status_report(self, addresses):
        """Test Switch turning off detected via status report"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        # Mock add_processor to prevent spawning TurnSoundbarOnProcessor
        original_add_processor = bus.add_processor
        mock_add_processor = Mock()

        # Start with Switch on
        with patch('time.time', return_value=1000.0):
            bus.add_processor = original_add_processor
            bus.add_processor(SwitchStatusProcessor(bus, addresses))
            bus.add_processor = mock_add_processor

        # Simulate Switch responding as ON
        with patch('time.time', return_value=1000.5):
            mock.simulate_received_command("41:90:00")  # Switch reports ON

        # Should have spawned TurnSoundbarOnProcessor
        assert mock_add_processor.call_count == 1

        # Advance time to trigger poll
        with patch('time.time', return_value=1005.5):
            mock.simulate_received_command("01:90:00")  # Unrelated event

        # Should have sent a poll
        assert mock.transmitted_commands[1] == "14:8F"

        # Simulate Switch responding with STANDBY status
        with patch('time.time', return_value=1006.0):
            mock.simulate_received_command("41:90:01")  # Switch reports STANDBY

        # Should have sent Chromecast switch command
        assert len(mock.transmitted_commands) == 3
        assert mock.transmitted_commands[2] == "1F:86:30:00"  # SET_STREAM_PATH to Chromecast

    def test_periodic_polling_while_on(self, addresses):
        """Test that Switch is polled periodically while on"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        # Mock add_processor to prevent spawning TurnSoundbarOnProcessor
        original_add_processor = bus.add_processor
        mock_add_processor = Mock()

        # Start with Switch on
        with patch('time.time', return_value=1000.0):
            bus.add_processor = original_add_processor
            bus.add_processor(SwitchStatusProcessor(bus, addresses))
            bus.add_processor = mock_add_processor

        # Simulate Switch responding as ON
        with patch('time.time', return_value=1000.5):
            mock.simulate_received_command("41:90:00")  # Switch reports ON

        # Should have spawned TurnSoundbarOnProcessor
        assert mock_add_processor.call_count == 1

        # Advance time to trigger first poll (5 second interval)
        with patch('time.time', return_value=1005.5):
            mock.simulate_received_command("01:90:00")  # Unrelated event

        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[1] == "14:8F"  # First poll

        # Respond to poll
        with patch('time.time', return_value=1006.0):
            mock.simulate_received_command("41:90:00")  # Switch still ON

        # Advance time to trigger second poll
        with patch('time.time', return_value=1011.5):
            mock.simulate_received_command("01:90:00")  # Unrelated event

        assert len(mock.transmitted_commands) == 3
        assert mock.transmitted_commands[2] == "14:8F"  # Second poll

    def test_filters_unrelated_traffic(self, addresses):
        """Test that processor correctly filters unrelated CEC traffic"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        with patch('time.time', return_value=1000.0):
            bus.add_processor(SwitchStatusProcessor(bus, addresses))

        # Initial request sent
        assert len(mock.transmitted_commands) == 1

        # Send various unrelated commands
        with patch('time.time', return_value=1000.5):
            mock.simulate_received_command("01:90:00")  # TV power status
            mock.simulate_received_command("51:90:01")  # Soundbar power status
            mock.simulate_received_command("0F:87:00:E0:91")  # Vendor ID

        # Should not send any additional commands (still waiting for initial response or timeout)
        assert len(mock.transmitted_commands) == 1

        # Processor should still be active
        assert len(bus._processors) == 1

