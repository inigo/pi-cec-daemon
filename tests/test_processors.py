from unittest.mock import patch, Mock
import pytest

from cec_comms import MockCECComms
from eventbus import CECEventBus
from processors import Addresses, SoundbarOnWithTvProcessor, SwitchStatusProcessor


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

        with patch('time.time', return_value=1000.0):
            bus.add_processor(SoundbarOnWithTvProcessor(bus, addresses))

        # Should send TV power status request
        assert len(mock.transmitted_commands) == 1
        assert mock.transmitted_commands[0] == "10:8F"  # Request TV power status

        # Simulate TV is ON
        with patch('time.time', return_value=1000.1):
            mock.simulate_received_command("01:90:00")  # TV reports ON

        # SoundbarOnWithTvProcessor should spawn TurnSoundbarOnProcessor
        # TurnSoundbarOnProcessor should send soundbar power status request
        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[1] == "15:8F"  # Request soundbar power status

        # Simulate soundbar is OFF (STANDBY)
        with patch('time.time', return_value=1000.2):
            mock.simulate_received_command("51:90:01")  # Soundbar reports STANDBY

        # Should send power toggle to soundbar
        assert len(mock.transmitted_commands) == 4
        assert mock.transmitted_commands[2] == "15:44:40"  # USER_CONTROL_PRESSED (POWER)
        assert mock.transmitted_commands[3] == "15:45"  # USER_CONTROL_RELEASE

        # SoundbarOnWithTvProcessor should still be active (long-running)
        # TurnSoundbarOnProcessor should be done
        assert len(bus._processors) == 1

    def test_tv_on_soundbar_already_on_does_nothing(self, addresses):
        """Test that nothing happens when both TV and soundbar are already on"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        with patch('time.time', return_value=1000.0):
            bus.add_processor(SoundbarOnWithTvProcessor(bus, addresses))

        # TV power status request
        assert mock.transmitted_commands[0] == "10:8F"

        # Simulate TV is ON
        with patch('time.time', return_value=1000.1):
            mock.simulate_received_command("01:90:00")

        # Soundbar power status request
        assert mock.transmitted_commands[1] == "15:8F"

        # Simulate soundbar is already ON
        with patch('time.time', return_value=1000.2):
            mock.simulate_received_command("51:90:00")  # Soundbar reports ON

        # Should NOT send power toggle
        assert len(mock.transmitted_commands) == 2

        # SoundbarOnWithTvProcessor should still be active (long-running)
        assert len(bus._processors) == 1

    def test_tv_off_does_nothing(self, addresses):
        """Test that nothing happens when TV is off"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        with patch('time.time', return_value=1000.0):
            bus.add_processor(SoundbarOnWithTvProcessor(bus, addresses))

        # TV power status request
        assert mock.transmitted_commands[0] == "10:8F"

        # Simulate TV is OFF (STANDBY)
        with patch('time.time', return_value=1000.1):
            mock.simulate_received_command("01:90:01")  # TV reports STANDBY

        # Should NOT request soundbar status or send any more commands
        assert len(mock.transmitted_commands) == 1

        # Processor should still be active (long-running)
        assert len(bus._processors) == 1

    def test_periodic_polling(self, addresses):
        """Test that TV is polled periodically every 500ms"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        # Start processor
        with patch('time.time', return_value=1000.0):
            bus.add_processor(SoundbarOnWithTvProcessor(bus, addresses))

        # Initial request
        assert len(mock.transmitted_commands) == 1
        assert mock.transmitted_commands[0] == "10:8F"

        # Respond to initial poll
        with patch('time.time', return_value=1000.1):
            mock.simulate_received_command("01:90:01")  # TV OFF

        # Advance time to trigger next poll (500ms interval)
        with patch('time.time', return_value=1000.6):
            mock.simulate_received_command("00:00")  # Unrelated event to trigger processing

        # Should have sent second poll
        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[1] == "10:8F"

        # Respond to second poll
        with patch('time.time', return_value=1000.7):
            mock.simulate_received_command("01:90:01")  # TV still OFF

        # Advance time for third poll
        with patch('time.time', return_value=1001.2):
            mock.simulate_received_command("00:00")  # Unrelated event

        # Should have sent third poll
        assert len(mock.transmitted_commands) == 3
        assert mock.transmitted_commands[2] == "10:8F"

    def test_tv_state_transition(self, addresses):
        """Test that processor tracks TV state changes"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        # Mock add_processor to prevent spawning TurnSoundbarOnProcessor
        original_add_processor = bus.add_processor
        mock_add_processor = Mock()

        # Start processor
        with patch('time.time', return_value=1000.0):
            bus.add_processor = original_add_processor
            bus.add_processor(SoundbarOnWithTvProcessor(bus, addresses))
            bus.add_processor = mock_add_processor

        # TV starts OFF
        with patch('time.time', return_value=1000.1):
            mock.simulate_received_command("01:90:01")  # TV OFF

        # No soundbar processor spawned
        assert mock_add_processor.call_count == 0

        # Advance time and poll again
        with patch('time.time', return_value=1000.6):
            mock.simulate_received_command("00:00")  # Trigger processing

        # TV now reports ON
        with patch('time.time', return_value=1000.7):
            mock.simulate_received_command("01:90:00")  # TV ON

        # Should have spawned TurnSoundbarOnProcessor
        assert mock_add_processor.call_count == 1

        # Advance time and poll again
        with patch('time.time', return_value=1001.2):
            mock.simulate_received_command("00:00")  # Trigger processing

        # TV still ON
        with patch('time.time', return_value=1001.3):
            mock.simulate_received_command("01:90:00")  # TV ON

        # Should spawn TurnSoundbarOnProcessor again (duplicate prevention in eventbus)
        assert mock_add_processor.call_count == 2

    def test_filters_unrelated_traffic(self, addresses):
        """Test that processor filters out unrelated CEC traffic"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        with patch('time.time', return_value=1000.0):
            bus.add_processor(SoundbarOnWithTvProcessor(bus, addresses))

        # TV power status request sent
        assert mock.transmitted_commands[0] == "10:8F"

        # Simulate unrelated traffic
        with patch('time.time', return_value=1000.1):
            mock.simulate_received_command("4F:82:10:00")  # Switch active source
            mock.simulate_received_command("0F:87:00:E0:91")  # TV vendor ID

        # Should still be waiting for TV response
        assert len(mock.transmitted_commands) == 1

        # Now send TV response
        with patch('time.time', return_value=1000.2):
            mock.simulate_received_command("01:90:00")  # TV ON

        # Should have spawned TurnSoundbarOnProcessor and requested soundbar status
        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[1] == "15:8F"


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
        """Test Switch turning off detected via 3 consecutive poll timeouts"""
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

        # === First poll and timeout ===
        # Advance time to trigger first poll (5 seconds after Switch turned on)
        with patch('time.time', return_value=1005.5):
            mock.simulate_received_command("01:90:00")  # Unrelated event to trigger processing

        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[1] == "14:8F"  # First poll

        # First timeout (no response) - should NOT trigger Chromecast switch yet
        with patch('time.time', return_value=1008.0):  # 2.5 seconds after poll
            mock.simulate_received_command("01:90:00")  # Unrelated event

        # Should NOT have sent Chromecast switch command (only 1 timeout)
        assert len(mock.transmitted_commands) == 2

        # === Second poll and timeout ===
        # Advance time to trigger second poll (5 seconds after first poll)
        with patch('time.time', return_value=1010.5):
            mock.simulate_received_command("01:90:00")  # Unrelated event

        assert len(mock.transmitted_commands) == 3
        assert mock.transmitted_commands[2] == "14:8F"  # Second poll

        # Second timeout - should NOT trigger Chromecast switch yet
        with patch('time.time', return_value=1013.0):
            mock.simulate_received_command("01:90:00")  # Unrelated event

        # Should NOT have sent Chromecast switch command (only 2 timeouts)
        assert len(mock.transmitted_commands) == 3

        # === Third poll and timeout ===
        # Advance time to trigger third poll (5 seconds after second poll)
        with patch('time.time', return_value=1015.5):
            mock.simulate_received_command("01:90:00")  # Unrelated event

        assert len(mock.transmitted_commands) == 4
        assert mock.transmitted_commands[3] == "14:8F"  # Third poll

        # Third timeout - NOW should trigger Chromecast switch
        with patch('time.time', return_value=1018.0):
            mock.simulate_received_command("01:90:00")  # Unrelated event

        # Should have sent Chromecast switch command (3 consecutive timeouts)
        assert len(mock.transmitted_commands) == 5
        assert mock.transmitted_commands[4] == "1F:86:30:00"  # SET_STREAM_PATH to Chromecast

    def test_switch_timeout_counter_resets_on_response(self, addresses):
        """Test that timeout counter resets when Switch responds"""
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

        # === First poll and timeout ===
        with patch('time.time', return_value=1005.5):
            mock.simulate_received_command("01:90:00")  # Trigger poll

        # First timeout
        with patch('time.time', return_value=1008.0):
            mock.simulate_received_command("01:90:00")

        # === Second poll and timeout ===
        with patch('time.time', return_value=1010.5):
            mock.simulate_received_command("01:90:00")  # Trigger second poll

        # Second timeout
        with patch('time.time', return_value=1013.0):
            mock.simulate_received_command("01:90:00")

        # === Third poll - but this time Switch responds! ===
        with patch('time.time', return_value=1015.5):
            mock.simulate_received_command("01:90:00")  # Trigger third poll

        # Switch responds - this should reset the timeout counter
        with patch('time.time', return_value=1016.0):
            mock.simulate_received_command("41:90:00")  # Switch reports ON

        # Now simulate 2 more timeouts - should NOT trigger Chromecast switch
        # because the counter was reset
        with patch('time.time', return_value=1021.0):
            mock.simulate_received_command("01:90:00")  # Trigger poll

        with patch('time.time', return_value=1024.0):
            mock.simulate_received_command("01:90:00")  # First timeout after reset

        with patch('time.time', return_value=1026.0):
            mock.simulate_received_command("01:90:00")  # Trigger another poll

        with patch('time.time', return_value=1029.0):
            mock.simulate_received_command("01:90:00")  # Second timeout after reset

        # Should NOT have sent Chromecast switch command (only 2 timeouts since reset)
        # Count the Chromecast commands
        chromecast_commands = [cmd for cmd in mock.transmitted_commands if cmd == "1F:86:30:00"]
        assert len(chromecast_commands) == 0

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
