"""Simulated data source — generates synthetic sensor data for development/testing.

Design: Implements the DataSource ABC to produce realistic multi-sensor
streams without requiring physical hardware. Uses deterministic stateful
generators: random-walk temperature, inverse-correlated humidity, sine-wave
lux with random spikes. Each read() call sleeps ~1 second to match the
Arduino sample rate.

Usage:
    source = SimulatedSource()
    while True:
        data = source.read()  # returns synthetic reading after 1s sleep
        print(data)
"""

import math
import random
import time

from sources.base import DataSource


class SimulatedSource(DataSource):
    """DataSource implementation that generates synthetic sensor data.

    Simulates three sensors with realistic behaviour:
    - Temperature: slow random walk, bounded 15-35°C
    - Humidity: loosely inverse to temperature, bounded 20-90%
    - Lux: sine-wave base with random spikes, bounded 0-2000

    Each read() call sleeps 1 second to match the Arduino sample rate.

    Attributes:
        _temp: Current simulated temperature value.
        _count: Number of readings generated (for sine phase).
    """

    def __init__(self):
        self._temp = 23.0
        self._count = 0

    def read(self) -> dict:
        """Block for ~1 second, then return a synthetic sensor reading.

        Returns:
            dict with keys: temperature_c, humidity_pct, lux (all float).
        """
        time.sleep(1.0)

        # Temperature: random walk ±0.3°C, bounded 15-35°C
        delta = random.uniform(-0.3, 0.3)
        self._temp = max(15.0, min(35.0, self._temp + delta))
        temperature_c = self._temp

        # Humidity: inverse correlation, bounded 20-90%
        base_hum = 60.0 - (temperature_c - 23.0) * 5.0
        noise = random.uniform(-3.0, 3.0)
        humidity_pct = max(20.0, min(90.0, base_hum + noise))

        # Lux: sine-wave with random spikes, bounded 0-2000
        phase = 2 * math.pi * self._count / 120.0
        sine_base = 800.0 + 600.0 * math.sin(phase)
        spike = random.uniform(0, 400) if random.random() < 0.1 else 0
        lux = max(0.0, min(2000.0, sine_base + spike + random.uniform(-100, 100)))

        self._count += 1

        return {
            "temperature_c": temperature_c,
            "humidity_pct": humidity_pct,
            "lux": lux,
        }

    def close(self):
        """No cleanup needed for simulated source."""
        pass