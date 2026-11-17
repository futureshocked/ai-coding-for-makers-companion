"""Thread-safe CSV logger for persisting streamed sensor readings to disk.

Design: uses reference counting to manage file lifetime — opens a timestamped
CSV file on first client connect and closes on last client disconnect, avoiding
file handle leaks and ensuring data flush. Thread-safe via threading.Lock to
handle concurrent Flask request threads and background streaming safely.
"""

import csv
import os
import threading
from datetime import datetime

from config import LOG_DIR


class Logger:
    """Thread-safe CSV logger for streamed sensor readings."""

    HEADER = ["timestamp_ms", "temperature_c", "humidity_pct", "lux"]

    def __init__(self, log_dir=None):
        self._log_dir = log_dir or LOG_DIR
        os.makedirs(self._log_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._file = None
        self._writer = None
        self._clients = 0

    @property
    def client_count(self) -> int:
        """Number of currently connected browser clients."""
        with self._lock:
            return self._clients

    # -- connection tracking --

    def connect(self):
        """Register a browser connection; open log file if first client."""
        with self._lock:
            self._clients += 1
            if self._clients == 1:
                self._open_file()

    def disconnect(self):
        """Unregister a browser connection; close log file if last client."""
        with self._lock:
            if self._clients > 0:
                self._clients -= 1
            if self._clients == 0:
                self._close_file()

    # -- file operations --

    def _open_file(self):
        """Open a new CSV file named with the current timestamp."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self._log_dir, f"{ts}.csv")
        self._file = open(path, "w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(self.HEADER)
        self._file.flush()

    def _close_file(self):
        """Safely close the current CSV file."""
        if self._file:
            try:
                self._file.flush()
                self._file.close()
            except OSError:
                pass
            finally:
                self._file = None
                self._writer = None

    # -- logging --

    def log(self, reading: dict):
        """Append one reading to the current log file (no-op if no clients)."""
        with self._lock:
            if self._writer is None:
                return
            row = [
                reading.get("timestamp_ms", ""),
                reading.get("temperature_c", ""),
                reading.get("humidity_pct", ""),
                reading.get("lux", ""),
            ]
            self._writer.writerow(row)
            if self._file:
                self._file.flush()
