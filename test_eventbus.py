"""
Tests for CEC Event Bus using MockCECComms

Run with: pytest test_eventbus.py -v
"""

import pytest
from cec_comms import MockCECComms, CECCommand
from cec_delegate import CECEventBus


class TestCECCommand:
    """Test CECCommand class"""

    def test_parse_command_string(self):
        """Test parsing a received command string"""
        cmd = CECCommand("01:90:00")

        assert cmd.command_string == "01:90:00"
        assert cmd.initiator == 0
        assert cmd.destination == 1
        assert cmd.opcode == 0x90
        assert cmd.parameters == b'\x00'

    def test_parse_command_with_multiple_parameters(self):
        """Test parsing command with multiple parameter bytes"""
        cmd = CECCommand("4F:82:10:00")

        assert cmd.initiator == 4
        assert cmd.destination == 0x0F
        assert cmd.opcode == 0x82
        assert cmd.parameters == b'\x10\x00'

    def test_parse_command_no_parameters(self):
        """Test parsing command without parameters"""
        cmd = CECCommand("10:36")

        assert cmd.initiator == 1
        assert cmd.destination == 0
        assert cmd.opcode == 0x36
        assert cmd.parameters == b''

    def test_build_command(self):
        """Test building a command for transmission"""
        cmd = CECCommand.build(destination=0, opcode=0x8F)

        assert cmd.command_string == "10:8F"
        assert cmd.initiator == 1
        assert cmd.destination == 0
        assert cmd.opcode == 0x8F
        assert cmd.parameters == b''

    def test_build_command_with_parameters(self):
        """Test building a command with parameters"""
        cmd = CECCommand.build(destination=0x0F, opcode=0x82, parameters=b'\x10\x00')

        assert cmd.command_string == "1F:82:10:00"
        assert cmd.initiator == 1
        assert cmd.destination == 0x0F
        assert cmd.opcode == 0x82
        assert cmd.parameters == b'\x10\x00'

    def test_str_representation(self):
        """Test string representation of command"""
        cmd = CECCommand("01:90:00")
        assert str(cmd) == "01:90:00"

    def test_invalid_command_string(self):
        """Test that invalid command strings raise ValueError"""
        with pytest.raises(ValueError):
            CECCommand("10")  # Too short


class TestMockCECComms:
    """Test MockCECComms class"""

    def test_init(self):
        """Test initialization"""
        mock = MockCECComms()
        callback_called = False

        def callback(cmd_string):
            nonlocal callback_called
            callback_called = True
            return 0

        assert mock.init(callback) is True
        assert callback_called is False  # Callback not called yet

    def test_transmit_records_commands(self):
        """Test that transmit records commands"""
        mock = MockCECComms()
        mock.init(lambda s: 0)

        cmd1 = CECCommand.build(destination=0, opcode=0x8F)
        cmd2 = CECCommand.build(destination=5, opcode=0x36)

        assert mock.transmit(cmd1) is True
        assert mock.transmit(cmd2) is True

        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[0] == "10:8F"
        assert mock.transmitted_commands[1] == "15:36"

    def test_transmit_before_init_fails(self):
        """Test that transmit fails before initialization"""
        mock = MockCECComms()
        cmd = CECCommand.build(destination=0, opcode=0x8F)

        assert mock.transmit(cmd) is False

    def test_simulate_received_command(self):
        """Test simulating received commands"""
        mock = MockCECComms()
        received_commands = []

        def callback(cmd_string):
            received_commands.append(cmd_string)
            return 0

        mock.init(callback)
        mock.simulate_received_command("01:90:00")
        mock.simulate_received_command("4F:82:10:00")

        assert len(received_commands) == 2
        assert received_commands[0] == "01:90:00"
        assert received_commands[1] == "4F:82:10:00"

    def test_close(self):
        """Test closing the mock"""
        mock = MockCECComms()
        mock.init(lambda s: 0)

        cmd = CECCommand.build(destination=0, opcode=0x8F)
        assert mock.transmit(cmd) is True

        mock.close()

        # After close, transmit should fail
        assert mock.transmit(cmd) is False


class TestCECEventBus:
    """Test CECEventBus class"""

    def test_init(self):
        """Test initialization"""
        mock = MockCECComms()
        bus = CECEventBus(mock)

        assert bus.init() is True

    def test_transmit_creates_command(self):
        """Test that transmit creates and sends a command"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        bus.transmit(destination=0, opcode=0x8F)
        bus.transmit(destination=5, opcode=0x36, params=b'\x01')

        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[0] == "10:8F"
        assert mock.transmitted_commands[1] == "15:36:01"

    def test_callback_receives_commands(self):
        """Test that callbacks receive commands"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        received_commands = []

        def callback(cmd: CECCommand):
            received_commands.append(cmd)

        bus.add_callback(callback)

        # Simulate receiving commands
        mock.simulate_received_command("01:90:00")
        mock.simulate_received_command("4F:82:10:00")

        assert len(received_commands) == 2
        assert received_commands[0].command_string == "01:90:00"
        assert received_commands[1].command_string == "4F:82:10:00"

    def test_multiple_callbacks(self):
        """Test that multiple callbacks all receive commands"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        callback1_commands = []
        callback2_commands = []

        def callback1(cmd: CECCommand):
            callback1_commands.append(cmd)

        def callback2(cmd: CECCommand):
            callback2_commands.append(cmd)

        bus.add_callback(callback1)
        bus.add_callback(callback2)

        mock.simulate_received_command("01:90:00")

        assert len(callback1_commands) == 1
        assert len(callback2_commands) == 1
        assert callback1_commands[0].command_string == "01:90:00"
        assert callback2_commands[0].command_string == "01:90:00"

    def test_callback_exception_handling(self):
        """Test that exceptions in callbacks don't break the bus"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        good_callback_called = False

        def bad_callback(cmd: CECCommand):
            raise Exception("This callback always fails")

        def good_callback(cmd: CECCommand):
            nonlocal good_callback_called
            good_callback_called = True

        bus.add_callback(bad_callback)
        bus.add_callback(good_callback)

        # Should not raise exception
        mock.simulate_received_command("01:90:00")

        # Good callback should still be called
        assert good_callback_called is True

    def test_close(self):
        """Test closing the event bus"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        bus.close()

        # After close, transmit should fail (mock is closed)
        assert bus.transmit(destination=0, opcode=0x8F) is False
