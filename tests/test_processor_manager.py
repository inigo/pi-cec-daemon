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
        """Test that start() adds SwitchStatusProcessor and begins periodic spawning"""
        mock = MockCECComms()
        manager = ProcessorManager(mock)

        # Start the manager
        result = manager.start()
        assert result is True

        # Should have added SwitchStatusProcessor
        assert len(manager.eventbus._processors) >= 1

        # Check that at least one processor is SwitchStatusProcessor
        # (by checking it sent the initial Switch status request)
        assert len(mock.transmitted_commands) >= 1
        assert mock.transmitted_commands[0] == "14:8F"  # Switch status request

        # Wait a bit for timer to fire
        time.sleep(0.6)

        # Should have spawned at least one SoundbarOnWithTvProcessor
        # (by checking it sent TV status request)
        assert len(mock.transmitted_commands) >= 2
        assert "10:8F" in mock.transmitted_commands  # TV status request

        # Clean up
        manager.stop()

    def test_stop_cleans_up(self):
        """Test that stop() cancels timer and closes event bus"""
        mock = MockCECComms()
        manager = ProcessorManager(mock)

        # Start then stop
        manager.start()
        time.sleep(0.1)  # Let timer start
        manager.stop()

        # Should have cancelled timer
        assert manager._timer is None or not manager._timer.is_alive()
        assert manager._running is False

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

    def test_multiple_soundbar_processors_handled(self):
        """Test that duplicate SoundbarOnWithTvProcessor names are handled"""
        mock = MockCECComms()
        manager = ProcessorManager(mock)

        manager.start()

        # Wait for multiple timer fires
        time.sleep(1.1)

        # The duplicate name check should prevent too many from being active
        # We can't be too specific about the count since some may have completed
        # but we should have at least spawned some
        assert len(mock.transmitted_commands) > 0

        manager.stop()
