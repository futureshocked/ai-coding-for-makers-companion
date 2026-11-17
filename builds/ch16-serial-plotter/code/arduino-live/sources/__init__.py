"""Data source abstraction for sensor input.

Provides a common interface (DataSource ABC) for reading sensor data from
either a physical Arduino via serial (SerialSource) or a built-in simulator
(SimulatedSource). The active source is selected at import time.

Classes:
    DataSource: Abstract base class defining the read/close interface.
    SerialSource: Reads CSV lines from a USB serial port, parses to dict.
    SimulatedSource: Generates synthetic sensor data via random walks.
"""

from sources.base import DataSource
from sources.serial_source import SerialSource
from sources.sim_source import SimulatedSource

__all__ = ["DataSource", "SerialSource", "SimulatedSource"]