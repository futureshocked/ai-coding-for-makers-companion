"""Simulates Arduino serial sensor data for development/testing without hardware.

Design: mirrors the pyserial Serial interface (readline/close) so the mock can
be swapped with a real SerialReader at the USE_MOCK flag with zero changes to
downstream code. Uses deterministic stateful generators (random-walk temperature,
inverse-correlated humidity, sine-wave lux) to produce realistic multi-sensor
streams rather than pure random noise.
"""

import math
import random
import time

from config import BAUD_RATE


class MockSerial:
    """Mock serial port that simulates Arduino sensor data.

    Exposes the same interface as a pyserial Serial object:
    __init__(port, baudrate) -> readline() -> bytes -> close()
    """

    def __init__(self, port: str = "", baudrate: int = BAUD_RATE):
        self._first_call = True
        self._port = port
        self._baudrate = baudrate
        self._call_count = 0
        self._temp = 23.0
        self._closed = False


    def readline(self) -> bytes:
        """Return one simulated sensor line as bytes."""
        time.sleep(0.5)

        if self._first_call:
            self._first_call = False
            return b"timestamp_ms,temperature_c,humidity_pct,lux\n"
    

        if self._closed:
            return b""

        ts_ms = self._call_count * 1000

        # Temperature: slow random walk ±0.3°C per step, bounded 18–30°C
        delta = random.uniform(-0.3, 0.3)
        self._temp = max(18.0, min(30.0, self._temp + delta))
        temperature_c = self._temp

        # Humidity: loosely inverse to temperature, range 40–80%
        base_hum = 60.0 - (temperature_c - 23.0) * 5.0
        noise = random.uniform(-3.0, 3.0)
        humidity_pct = max(40.0, min(80.0, base_hum + noise))

        # Lux: sine-wave base with random spikes, range 0–2000
        sine_base = 800.0 + 600.0 * math.sin(2 * math.pi * self._call_count / 120.0)
        spike = random.uniform(0, 400) if random.random() < 0.1 else 0
        lux = max(0, min(2000, sine_base + spike + random.uniform(-100, 100)))

        self._call_count += 1

        line = f"{ts_ms:.0f},{temperature_c:.1f},{humidity_pct:.1f},{lux:.0f}\n"
        return line.encode("ascii")

    def close(self):
        """Close the mock serial port (no-op)."""
        self._closed = True