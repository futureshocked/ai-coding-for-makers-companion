# Arduino Sensor Visualiser

## Description

Real-time web dashboard that streams Arduino sensor data (temperature, humidity, light) via USB serial connection and visualises it live in the browser using Chart.js. Supports both hardware serial and mock data for development without physical devices.

## Features

- **Live Streaming** — Server-Sent Events (SSE) deliver readings to the browser in real time
- **Mock Data Mode** — Built-in simulator produces realistic sensor data (random-walk temperature, inverse-correlated humidity, sine-wave lux)
- **CSV Logging** — Automatic per-session CSV files with timestamped filenames
- **Log Replay** — Replay any previously recorded log at configurable speed (1x, 2x, 5x, 10x)
- **Live Statistics** — Current, min, max, and mean values per sensor
- **Multi-Axis Charts** — Each sensor on its own Y axis with smooth interpolation
- **Configurable Window** — 30s, 5m, or unlimited rolling chart
- **Sensor Toggles** — Show/hide individual sensor traces

## Requirements

- Python 3.8+
- `pip install -r requirements.txt`

## Running the App

```bash
# From the arduino-live/ directory:
python app.py
```

Then open **http://localhost:5000** in your browser.

For production deployment (concurrent SSE clients), use the Waitress server:

```bash
python server.py
```

## Switching to Real Hardware

1. Connect your Arduino to a USB serial port.
2. Open `config.py` and set:
   ```python
   USE_MOCK = False
   SERIAL_PORT = '/dev/ttyACM0'  # Update to your actual port
   ```
3. Restart the app.

To find your Arduino's port:
```bash
ls /dev/ttyUSB* /dev/ttyACM*
# or
python -m serial.tools.list_ports
```

## Replay Feature

The dashboard can replay any previously recorded CSV log file from the `logs/` directory:

1. Select a log file from the **Log** dropdown in the control bar.
2. Optionally adjust **Speed** (1x = original timing, 2x = 2× faster, etc.).
3. Click **Replay** to start. Charts and stats reset before playback.
4. Click **Live** to return to live streaming mode.

Replay preserves the original timing between readings (capped at 0.5s max delay per reading to avoid long waits). Path traversal is prevented in the filename parameter.

## Log Files

Session data is saved as timestamped CSV files in the `logs/` directory:

```
logs/
  20260519_093000.csv
  20260519_100000.csv
  ...
```

Each file contains:
```csv
timestamp_ms,temperature_c,humidity_pct,lux
4823,23.4,65.1,412
5824,23.5,64.8,420
```

- `timestamp_ms`: Arduino's `millis()` value (milliseconds since boot)
- `temperature_c`: Temperature in Celsius (1 decimal)
- `humidity_pct`: Relative humidity percentage (1 decimal)
- `lux`: Ambient light level in lux (integer)

## Project Structure

```
arduino-live/
├── app.py                  # Flask application: routes, SSE streaming, log API
├── config.py               # Configuration: port, baud, mock toggle, log dir
├── logger.py               # Thread-safe CSV logger for session persistence
├── mock_serial.py          # Simulated serial device for development
├── serial_reader.py        # pyserial wrapper for real hardware
├── server.py               # Production entry point (Waitress WSGI server)
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── arduino/
│   └── arduino_live.ino    # Arduino sketch for real sensor hardware
├── sources/
│   ├── __init__.py         # Source package exports
│   ├── base.py             # DataSource abstract base class
│   ├── serial_source.py    # Serial port DataSource implementation
│   └── sim_source.py       # Simulated DataSource implementation
├── templates/
│   └── index.html          # Main dashboard HTML template
└── static/
    ├── app.js              # Frontend: Chart.js, SSE, controls, replay
    └── style.css           # Dark theme dashboard styling
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serves the main dashboard HTML |
| GET | `/stream` | SSE endpoint for live sensor streaming |
| GET | `/stream/replay?filename=X&speed=Y` | SSE endpoint for log replay |
| GET | `/api/logs` | JSON list of available log files |
| GET | `/api/logs/<filename>` | JSON data for a specific log file |

## CSV Data Format

All sensor data uses positional CSV parsing (column order = schema):

```
timestamp_ms,temperature_c,humidity_pct,lux
```

**Warning:** Column order defines the schema. Reordering columns will silently corrupt readings.

## Architecture

```
┌──────────────┐     CSV lines     ┌───────────────┐
│  Arduino     │ ─────────────────▶│ SerialReader  │ (or MockSerial)
└──────────────┘                   └───────┬───────┘
                                           │ readline()
                                    ┌──────▼───────┐
                                    │    app.py    │
                                    │  (Flask SSE) │
                                    └──┬───────┬───┘
                                       │       │
                              ┌────────▼─┐  ┌──▼────────┐
                              │ Browser  │  │  Logger   │
                              │ (Chart)  │  │  (CSV)    │
                              └──────────┘  └───────────┘
```

Source selection is controlled by the `USE_MOCK` flag in `config.py`. The `sources/` package provides an alternative architecture using the `DataSource` ABC pattern for more complex deployments.