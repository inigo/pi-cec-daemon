import time

from cec_comms import MockCECComms
from processor_manager import ProcessorManager


class TestProcessorManager:
    """Test ProcessorManager"""

    def test_initialization(self):
        """Test that ProcessorManager initializes components correctly"""
        mock = MockCECComms()
        manager = ProcessorManager(mock)

        # Should have created eventbus and addresses
        assert manager.eventbus is not None
        assert manager.addresses is not None
        assert manager.comms is mock

    def test_start_adds_processors(self):
        """Test that start() adds both long-running processors"""
        mock = MockCECComms()
        manager = ProcessorManager(mock)

        # Start the manager
        result = manager.start()
        assert result is True

        # Should have added both processors
        assert len(manager.eventbus._processors) == 2

        # Should have sent initial status requests from both processors
        assert len(mock.transmitted_commands) == 2
        assert mock.transmitted_commands[0] == "14:8F"  # Switch status request
        assert mock.transmitted_commands[1] == "10:8F"  # TV status request

        # Clean up
        manager.stop()

    def test_stop_cleans_up(self):
        """Test that stop() closes event bus"""
        mock = MockCECComms()
        manager = ProcessorManager(mock)

        # Start then stop
        manager.start()
        manager.stop()

        # Event bus should be closed (mock CEC should be closed)
        assert not mock._initialized

    def test_start_without_comms_fails_gracefully(self):
        """Test that start() handles init failure gracefully"""
        mock = MockCECComms()

        # Make init fail
        original_init = mock.init
        mock.init = lambda callback: False

        manager = ProcessorManager(mock)
        result = manager.start()

        assert result is False

        # Restore
        mock.init = original_init
        manager.stop()

    def test_processors_remain_active(self):
        """Test that both processors remain active (long-running)"""
        mock = MockCECComms()
        manager = ProcessorManager(mock)

        manager.start()

        # Both processors should be active
        assert len(manager.eventbus._processors) == 2

        manager.stop()
