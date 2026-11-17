# Arduino Live — Architecture

Live browser visualisation of Arduino sensor data over USB serial.
No persistence. Localhost only. Switchable between real hardware and a simulator.

---

## Goals

- Stream sensor readings from an Arduino (or a simulator) to a browser in real time
- Display three sensors — temperature (°C), humidity (%), lux — as independent live charts
- Show host PC wall-clock time on each sample; Arduino's own timer is not used for display
- Require no browser plugin, no build step, no external infrastructure
- Make swapping between hardware and simulated data a single CLI flag, with no code changes

---

## High-level architecture

```
┌─────────────────────┐        CSV line / 1 Hz        ┌──────────────────┐
│   Arduino (USB)     │ ──────────────────────────────▶│  SerialSource    │
│                     │                                └────────┬─────────┘
│  OR                 │                                         │ .read() → dict
│                     │        internal / 1 Hz        ┌────────▼─────────┐
│   SimulatedSource   │ ──────────────────────────────▶│  DataSource ABC  │
└─────────────────────┘                                └────────┬─────────┘
                                                                │
                                                    ┌───────────▼───────────┐
                                                    │   Background thread   │
                                                    │   (serial reader loop)│
                                                    └───────────┬───────────┘
                                                                │ run_coroutine_threadsafe
                                                    ┌───────────▼───────────┐
                                                    │   FastAPI + asyncio   │
                                                    │   event loop          │
                                                    └───────┬───────────────┘
                                                            │ WebSocket broadcast
                                                ┌───────────▼──────────────┐
                                                │   Browser (index.html)   │
                                                │   Chart.js, plain JS     │
                                                └──────────────────────────┘
```

---

## File structure

```
arduino-live/
├── ARCHITECTURE.md
├── requirements.txt
├── server.py                   # FastAPI app, WebSocket manager, startup
├── sources/
│   ├── __init__.py
│   ├── base.py                 # DataSource abstract base class
│   ├── serial_source.py        # Reads from USB serial port
│   └── sim_source.py           # Generates synthetic readings
├── static/
│   └── index.html              # Single-file frontend; no build step
└── arduino/
    └── arduino_live.ino        # Arduino sketch
```

---

## Data flow

### 1. Arduino → server (serial)

The Arduino emits one CSV line per second on `Serial` at 9600 baud:

```
timestamp_ms,temperature_c,humidity_pct,lux
```

Example:

```
4823,23.4,65.1,412
```

Rules:
- **Column order is the schema.** Parsing is positional; reordering columns silently corrupts readings.
- No header row is emitted in the data stream. The header above is documentation only.
- Lines that do not split into exactly 4 fields, or that fail numeric conversion on any field, are skipped with a warning printed to the server console.

### 2. Source → server (internal)

Both `SerialSource` and `SimulatedSource` expose a single method:

```python
def read(self) -> dict:
    ...
```

Return value is always:

```python
{"temp": float, "humidity": float, "lux": float}
```

`timestamp_ms` (column 0 from the Arduino) is parsed and available for diagnostics (e.g. detecting dropped samples), but is not included in the returned dict. It is not forwarded to the browser.

### 3. Server → browser (WebSocket)

The background reader thread calls `source.read()` in a blocking loop. On each successful reading, it:

1. Adds a `timestamp` field — ISO 8601 wall-clock time from the host PC (`datetime.now().isoformat()`)
2. Serialises the enriched dict to JSON
3. Schedules a broadcast to all connected WebSocket clients via `asyncio.run_coroutine_threadsafe`

Payload example:

```json
{
  "temp": 23.4,
  "humidity": 65.1,
  "lux": 412,
  "timestamp": "2025-03-14T09:26:01.443"
}
```

### 4. Browser rendering

The browser connects to `ws://localhost:8000/ws`. On each message:

- The `timestamp` field updates the header display
- The remaining numeric fields each map to their own Chart.js line chart
- Charts maintain a rolling window of 80 points; older points are dropped
- Each chart also displays current value, running min, and running max
- On WebSocket disconnect, the frontend retries every 2 seconds

---

## Components

### `sources/base.py` — DataSource ABC

```python
from abc import ABC, abstractmethod

class DataSource(ABC):
    @abstractmethod
    def read(self) -> dict:
        """Block until one reading is available. Return dict of float values."""
        ...

    def close(self):
        """Optional cleanup. Called on server shutdown."""
        pass
```

### `sources/serial_source.py` — SerialSource

- Opens the configured serial port at startup; retries every 3 s if the port is unavailable (Arduino not yet connected)
- Calls `ser.readline()`, decodes UTF-8, strips whitespace
- Splits on `,`; expects exactly 4 fields
- Field mapping by index: `[0]` → `timestamp_ms` (discarded), `[1]` → `temp`, `[2]` → `humidity`, `[3]` → `lux`
- Malformed lines: log warning, continue loop (do not crash)
- `close()` closes the serial port cleanly

### `sources/sim_source.py` — SimulatedSource

- Maintains internal state: `temp`, `humidity`, `lux`
- Each call to `read()` applies a small random walk to each value, within realistic bounds:
  - `temp`: 15–35 °C
  - `humidity`: 20–90 %
  - `lux`: 0–2000
- Sleeps 1 s before returning, matching the Arduino sample rate
- No external dependencies

### `server.py` — FastAPI application

Responsibilities:
- Parse CLI arguments: `--source {serial|sim}`, `--port`, `--baud`, `--host`, `--http-port`
- Instantiate the correct `DataSource` subclass
- On startup (FastAPI `lifespan`): launch the reader thread as a daemon
- Serve `static/index.html` at `GET /`
- Accept WebSocket connections at `/ws`; manage a list of active connections
- On shutdown: call `source.close()`

**WebSocket connection manager** handles connect, disconnect, and broadcast. Dead connections (send raises) are removed from the active list silently.

**Reader thread** runs a `while True` loop:

```python
data = source.read()          # blocks ~1 s
data["timestamp"] = datetime.now().isoformat()
asyncio.run_coroutine_threadsafe(manager.broadcast(data), loop)
```

### `static/index.html` — Frontend

Single file; no framework; no build step. Dependencies loaded from CDN:

- Chart.js 4.x (UMD build, jsdelivr)

Behaviour:
- On load: open WebSocket, show "Connecting…" status
- On first message: create one chart card per numeric key (excluding `timestamp`)
- On each subsequent message: push new data point, shift oldest if over `MAX_POINTS = 80`, call `chart.update('none')` (no animation)
- Timestamp from payload displayed in header, updated each sample
- Auto-reconnect on disconnect (2 s delay)
- Dark theme; 2-column responsive grid; min/max per chart

### `arduino/arduino_live.ino` — Arduino sketch

- `Serial.begin(9600)` in `setup()`
- In `loop()`: read sensors, emit one CSV line via `Serial.println()`, `delay(1000)`
- Column order matches the server parser: `millis(),temp,humidity,lux`
- Floats printed to 1 decimal place; lux as integer

---

## Startup

```bash
# Install dependencies
pip install -r requirements.txt

# Run with simulator (no Arduino needed)
python server.py --source sim

# Run with real Arduino
python server.py --source serial --port /dev/ttyUSB0 --baud 9600

# Open browser
http://localhost:8000
```

Find the Arduino's port if unknown:

```bash
ls /dev/ttyUSB* /dev/ttyACM*
# or
python -m serial.tools.list_ports
```

---

## What is explicitly deferred

| Capability | Where to add it when ready |
|---|---|
| Persistence (SQLite, Baserow) | `server.py` reader thread, after `source.read()`, before broadcast |
| External access | Expose FastAPI port via Cloudflare Tunnel; no structural changes |
| Additional sensors | Extend the CSV schema; parser and frontend are both schema-agnostic |
| Historical replay in browser | Requires persistence first; then a REST endpoint + frontend chart init |
