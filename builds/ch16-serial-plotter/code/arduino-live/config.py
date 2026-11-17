"""Central configuration for the serial plotter application.

Design: flat module-level constants rather than a config class or file,
keeping access simple (direct imports) and avoiding indirection. Separates
hardware concerns (SERIAL_PORT, BAUD_RATE) from operational toggles (USE_MOCK)
and storage settings (LOG_DIR) for quick development iteration.
"""

SERIAL_PORT = '/dev/ttyACM1'
BAUD_RATE = 9600
USE_MOCK = False
LOG_DIR = 'logs'
