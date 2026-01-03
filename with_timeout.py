import logging
import time


def with_timeout(seconds: float):
    """
    Decorator to add timeout handling to processor generators.

    Args:
        seconds: Timeout in seconds

    Returns:
        Decorator function

    Example:
        @with_timeout(5.0)
        def my_processor():
            cmd = yield [CECCommand.build(destination=0, opcode=0x8F)]
            while cmd.initiator != 0 or cmd.opcode != 0x90:
                cmd = yield []
            # Process response...
            yield [CECCommand.build(...), None]  # Terminate with None
    """
    def decorator(processor_func):
        def wrapper(*args, **kwargs):
            gen = processor_func(*args, **kwargs)  # Create the actual processor with arguments
            start_time = time.time()
            logger = logging.getLogger(f'Processor({processor_func.__name__})')

            try:
                # Start the generator and get first commands
                result = next(gen)

                while True:
                    # Check timeout before forwarding each event
                    elapsed = time.time() - start_time
                    if elapsed > seconds:
                        logger.warning(f"Processor '{processor_func.__name__}' timed out after {elapsed:.2f}s")
                        gen.close()
                        yield None  # Signal termination to event bus
                        return

                    # Act as proxy: receive event, forward to real processor
                    event = yield result
                    result = gen.send(event)

            except StopIteration:
                return

        # Preserve function name for logging
        wrapper.__name__ = processor_func.__name__
        return wrapper

    return decorator
