"""Abstract base class defining the common interface for sensor data sources.

Design: All data source implementations (SerialSource, SimulatedSource) inherit
from DataSource. This enables polymorphic interchange — the rest of the
application interacts only with the DataSource interface, never with concrete
implementations.

Usage:
    from abc import ABC, abstractmethod

    class MySource(DataSource):
        def read(self) -> dict:
            # Block until one reading is available
            return {"temperature_c": 23.0, "humidity_pct": 65.0, "lux": 412}

        def close(self):
            # Optional cleanup
            pass
"""

from abc import ABC, abstractmethod


class DataSource(ABC):
    """Abstract base class for sensor data sources.

    Implementations must provide read() which blocks until a reading is
    available and optionally provide close() for cleanup.

    Methods:
        read(): Block until one reading is available. Returns dict of sensor
            values keyed by sensor name with float values.
        close(): Optional cleanup. Called on server shutdown.
    """

    @abstractmethod
    def read(self) -> dict:
        """Block until one reading is available. Returns dict of float values."""
        ...

    def close(self):
        """Optional cleanup. Called on server shutdown."""
        pass