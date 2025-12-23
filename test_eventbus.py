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


class TestProcessors:
    """Test processor generator functionality"""

    def test_simple_processor(self):
        """Test a processor that sends one command and completes"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        response_received = [None]

        def simple_processor():
            # Send a power status request
            cmd = yield [CECCommand.build(destination=0, opcode=0x8F)]

            # Loop until we get the response we want
            while cmd.initiator != 0 or cmd.opcode != 0x90:
                cmd = yield []

            response_received[0] = cmd

            # Done - yield None to terminate
            yield None

        bus.add_processor(simple_processor())

        # Should have sent the initial command
        assert len(mock.transmitted_commands) == 1
        assert mock.transmitted_commands[0] == "10:8F"

        # Simulate unrelated traffic (should be ignored)
        mock.simulate_received_command("4F:82:10:00")
        assert response_received[0] is None

        # Simulate TV response
        mock.simulate_received_command("01:90:00")
        assert response_received[0] is not None
        assert response_received[0].opcode == 0x90

        # Processor should be complete and removed (no active processors)
        assert len(bus._processors) == 0

    def test_processor_sends_multiple_commands(self):
        """Test a processor that sends multiple commands in sequence"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        def multi_command_processor():
            # Send first command
            cmd = yield [CECCommand.build(destination=0, opcode=0x8F)]

            # Wait for TV response
            while cmd.initiator != 0 or cmd.opcode != 0x90:
                cmd = yield []

            # Send second command
            cmd = yield [CECCommand.build(destination=5, opcode=0x36)]

            # Wait for soundbar response
            while cmd.initiator != 5 or cmd.opcode != 0x90:
                cmd = yield []

            # Done
            yield None

        bus.add_processor(multi_command_processor())

        # Should have sent first command
        assert len(mock.transmitted_commands) == 1
        assert mock.transmitted_commands[0] == "10:8F"

        # Simulate first response
        mock.simulate_received_command("01:90:00")

        # Should have sent second command
        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[1] == "15:36"

        # Simulate second response
        mock.simulate_received_command("51:90:01")

        # Processor should be complete
        assert len(bus._processors) == 0

    def test_processor_sends_batch_commands(self):
        """Test a processor that sends multiple commands at once (e.g., user control pressed + released)"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        def batch_processor():
            # Send user control pressed + released together
            cmd = yield [
                CECCommand.build(destination=5, opcode=0x44, parameters=b'\x40'),  # Power button pressed
                CECCommand.build(destination=5, opcode=0x45)  # Button released
            ]

            # Wait for response
            while cmd.initiator != 5 or cmd.opcode != 0x90:
                cmd = yield []

            # Done
            yield None

        bus.add_processor(batch_processor())

        # Should have sent both commands
        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[0] == "15:44:40"
        assert mock.transmitted_commands[1] == "15:45"

        # Simulate response
        mock.simulate_received_command("51:90:00")

        # Processor should be complete
        assert len(bus._processors) == 0

    def test_processor_yields_empty_list(self):
        """Test a processor that yields [] to receive without transmitting"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        received_count = [0]

        def counting_processor():
            # Send initial command and receive first response
            cmd = yield [CECCommand.build(destination=0, opcode=0x8F)]
            received_count[0] += 1

            # Receive a few more commands without sending anything
            for _ in range(2):
                cmd = yield []
                received_count[0] += 1

            # Done
            yield None

        bus.add_processor(counting_processor())

        # Should have sent initial command
        assert len(mock.transmitted_commands) == 1

        # Simulate three responses
        mock.simulate_received_command("01:90:00")
        assert len(mock.transmitted_commands) == 1  # No new commands
        assert received_count[0] == 1

        mock.simulate_received_command("4F:82:10:00")
        assert len(mock.transmitted_commands) == 1
        assert received_count[0] == 2

        mock.simulate_received_command("01:90:01")
        assert len(mock.transmitted_commands) == 1
        assert received_count[0] == 3

        # Processor should be complete
        assert len(bus._processors) == 0

    def test_multiple_processors(self):
        """Test multiple processors running concurrently"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        processor1_done = [False]
        processor2_done = [False]

        def processor1():
            cmd = yield [CECCommand.build(destination=0, opcode=0x8F)]
            while cmd.initiator != 0 or cmd.opcode != 0x90:
                cmd = yield []
            processor1_done[0] = True
            yield None

        def processor2():
            cmd = yield [CECCommand.build(destination=5, opcode=0x36)]
            while cmd.initiator != 5 or cmd.opcode != 0x90:
                cmd = yield []
            processor2_done[0] = True
            yield None

        bus.add_processor(processor1())
        bus.add_processor(processor2())

        # Should have two processors active
        assert len(bus._processors) == 2

        # Should have sent both initial commands
        assert len(mock.transmitted_commands) == 2
        assert "10:8F" in mock.transmitted_commands
        assert "15:36" in mock.transmitted_commands

        # Simulate TV response (only processor1 should complete)
        mock.simulate_received_command("01:90:00")
        assert processor1_done[0] is True
        assert processor2_done[0] is False
        assert len(bus._processors) == 1

        # Simulate soundbar response (processor2 should complete)
        mock.simulate_received_command("51:90:01")
        assert processor2_done[0] is True
        assert len(bus._processors) == 0

    def test_processor_exception_handling(self):
        """Test that processor exceptions are handled gracefully"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        good_processor_done = [False]

        def bad_processor():
            cmd = yield [CECCommand.build(destination=0, opcode=0x8F)]
            raise Exception("Something went wrong")

        def good_processor():
            cmd = yield [CECCommand.build(destination=5, opcode=0x36)]
            while cmd.initiator != 5 or cmd.opcode != 0x90:
                cmd = yield []
            good_processor_done[0] = True
            yield None

        bus.add_processor(bad_processor())
        bus.add_processor(good_processor())

        # Should have two processors
        assert len(bus._processors) == 2

        # Simulate response - bad processor will crash and be removed
        mock.simulate_received_command("01:90:00")

        # Bad processor should be removed, good one should remain
        assert len(bus._processors) == 1

        # Good processor should still work
        mock.simulate_received_command("51:90:00")
        assert good_processor_done[0] is True
        assert len(bus._processors) == 0

    def test_processor_with_callbacks(self):
        """Test that processors and callbacks can coexist"""
        mock = MockCECComms()
        bus = CECEventBus(mock)
        bus.init()

        callback_commands = []
        processor_commands = []

        def callback(cmd):
            callback_commands.append(cmd.command_string)

        def processor():
            cmd = yield [CECCommand.build(destination=0, opcode=0x8F)]
            while cmd.initiator != 0 or cmd.opcode != 0x90:
                cmd = yield []
            processor_commands.append(cmd.command_string)
            yield None

        bus.add_callback(callback)
        bus.add_processor(processor())

        # Simulate unrelated command
        mock.simulate_received_command("4F:82:10:00")

        # Callback should receive it, processor ignores it
        assert len(callback_commands) == 1
        assert len(processor_commands) == 0

        # Simulate TV response
        mock.simulate_received_command("01:90:00")

        # Both callback and processor should have received the command
        assert len(callback_commands) == 2
        assert len(processor_commands) == 1
        assert callback_commands[1] == "01:90:00"
        assert processor_commands[0] == "01:90:00"
