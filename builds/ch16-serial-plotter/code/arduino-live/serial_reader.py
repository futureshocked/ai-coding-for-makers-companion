"""Thin wrapper around pyserial for reading Arduino sensor data over USB serial.

Design: wraps pyserial in a class with identical readline/close methods as
MockSerial, enabling polymorphic interchange via the USE_MOCK config flag.
Fails fast on port open — raises RuntimeError with diagnostic context rather
than propagating raw pyserial exceptions upstream.
"""

import serial

from config import BAUD_RATE, SERIAL_PORT


class SerialReader:
    """Blocking serial port reader that wraps pyserial Serial.

    Exposes readline() and close() methods matching the MockSerial interface,
    allowing polymorphic interchange via the USE_MOCK config flag.

    Attributes:
        _ser: Underlying pyserial.Serial instance.
    """

    def __init__(self):
        try:
            self._ser = serial.Serial(SERIAL_PORT, BAUD_RATE)
        except serial.SerialException as e:
            raise RuntimeError(
                f"Cannot open serial port '{SERIAL_PORT}': {e}. "
                "Check connection or update SERIAL_PORT in config.py"
            )

    def readline(self) -> bytes:
        return self._ser.readline()

    def close(self):
        self._ser.close()