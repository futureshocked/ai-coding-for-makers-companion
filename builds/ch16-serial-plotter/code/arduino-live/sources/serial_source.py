"""Serial data source implementation — reads CSV sensor data from USB serial port.

Design: Implements the DataSource ABC to read lines from a pyserial Serial
port, parse CSV fields into a dict of sensor values. Skips malformed lines
with warnings. Retries port open on failure rather than crashing.

CSV format (positional): timestamp_ms,temperature_c,humidity_pct,lux

Usage:
    source = SerialSource(port="/dev/ttyACM0", baudrate=9600)
    try:
        while True:
            data = source.read()  # blocks until line available
            print(data)
    finally:
        source.close()
"""

import serial
import time

from sources.base import DataSource


class SerialSource(DataSource):
    """DataSource implementation that reads CSV sensor data from USB serial.

    Opens a serial port at construction, retries if unavailable. Each call
    to read() returns one parsed reading dict. Malformed lines are logged
    and skipped.

    Args:
        port: Serial port path (e.g. /dev/ttyACM0, COM3).
        baudrate: Serial baud rate (default 9600).

    Attributes:
        _port: Configured serial port path.
        _baudrate: Configured baud rate.
        _ser: Active pyserial.Serial instance or None.
    """

    def __init__(self, port: str = "/dev/ttyACM0", baudrate: int = 9600):
        self._port = port
        self._baudrate = baudrate
        self._ser = None
        self._open_retry = 3  # seconds

    def _open(self):
        """Open serial port, retrying every _open_retry seconds on failure."""
        while self._ser is None or not self._ser.is_open:
            try:
                self._ser = serial.Serial(self._port, self._baudrate)
                print(f"[SerialSource] Opened {self._port} @ {self._baudrate}")
            except (serial.SerialException, OSError) as e:
                print(f"[SerialSource] Port unavailable: {e}. Retrying in {self._open_retry}s...")
                time.sleep(self._open_retry)

    def read(self) -> dict:
        """Block until one reading is available from serial port.

        Returns:
            dict with keys: temperature_c, humidity_pct, lux (all float).

        Raises:
            RuntimeError: If serial port cannot be opened after retries.
        """
        if self._ser is None or not self._ser.is_open:
            self._open()

        while True:
            line = self._ser.readline()
            if not line:
                continue

            text = line.decode("utf-8", errors="replace").strip()

            if not text or text.startswith("timestamp_ms"):
                continue  # skip empty lines and CSV header

            parts = text.split(",")
            if len(parts) != 4:
                print(f"[SerialSource] Skipping malformed line ({len(parts)} fields): {text!r}")
                continue

            try:
                return {
                    "temperature_c": float(parts[1]),
                    "humidity_pct": float(parts[2]),
                    "lux": float(parts[3]),
                }
            except ValueError as e:
                print(f"[SerialSource] Parse error: {e} — line: {text!r}")
                continue

    def close(self):
        """Close the serial port."""
        if self._ser and self._ser.is_open:
            self._ser.close()
            print("[SerialSource] Closed serial port")