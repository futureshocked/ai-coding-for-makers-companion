# Arduino Live — Coding Agent Spec

---

## Task

Build a local web application that reads sensor data from an Arduino over USB serial and streams it live to a browser as multiple real-time charts. The application must support switching between real hardware and a built-in simulator without code changes.

---

## Context

The Arduino emits one CSV line per second over USB serial at 9600 baud, in this exact column order:

```
timestamp_ms,temperature_c,humidity_pct,lux
```

Example line:

```
4823,23.4,65.1,412
```

- `timestamp_ms` is Arduino's `millis()` — milliseconds since boot. It is parsed for diagnostic purposes (dropped-sample detection) but is not forwarded to the browser.
- The host PC's wall-clock time (`datetime.now().isoformat()`) is used as the display timestamp in the browser.
- Column order is the schema. Parsing is positional. The parser must enforce exactly 4 fields per line and skip malformed lines with a console warning.

The server is a FastAPI application running on localhost only. The frontend is a single HTML file with no build step.

Full architecture is documented in `ARCHITECTURE.md`, which is included with this spec.

---

## Constraints

**Language and stack**
- Python 3.11+
- FastAPI + Uvicorn for the HTTP/WebSocket server
- `pyserial` for serial communication
- Plain HTML + vanilla JS + Chart.js 4.x (CDN) for the frontend — no npm, no bundler

**Data source abstraction**
- Define an abstract base class `DataSource` in `sources/base.py` with a single method `read(self) -> dict` and an optional `close(self)` method
- Implement `SerialSource` and `SimulatedSource` as concrete subclasses
- The rest of the application must only interact with the `DataSource` interface — it must not contain any `isinstance` checks or source-specific branching
- Active source is selected at startup via `--source serial` or `--source sim`; default is `sim`

**SerialSource behaviour**
- Retry port open every 3 seconds if unavailable (Arduino not yet connected); do not crash
- Skip and warn on: lines that do not split into exactly 4 fields; fields that fail float conversion
- `close()` must close the serial port

**SimulatedSource behaviour**
- Slow random walk within realistic bounds: temp 15–35 °C, humidity 20–90 %, lux 0–2000
- `read()` sleeps 1 second before returning, matching the Arduino sample rate

**Server**
- CLI arguments: `--source`, `--port` (default `/dev/ttyUSB0`), `--baud` (default `9600`), `--host` (default `0.0.0.0`), `--http-port` (default `8000`)
- Serial reading runs in a daemon thread; broadcasts to the asyncio event loop via `asyncio.run_coroutine_threadsafe`
- The reader thread adds `timestamp` (ISO 8601 host PC time) to each payload before broadcast
- WebSocket endpoint: `/ws`
- Static file endpoint: `GET /` serves `static/index.html`
- Dead WebSocket connections are removed silently from the active connection list

**Broadcast payload** (JSON, sent to all connected clients):
```json
{
  "temp": 23.4,
  "humidity": 65.1,
  "lux": 412,
  "timestamp": "2025-03-14T09:26:01.443"
}
```

**Frontend**
- Connects to `ws://[host]/ws` on load
- Creates one Chart.js line chart per numeric key in the first received message (excluding `timestamp`)
- Charts maintain a rolling window of 80 points; oldest points are dropped when the window is full
- `chart.update('none')` — no animation on update
- Each chart displays: current value, running min, running max
- `timestamp` from payload is displayed in the page header, updated each sample
- WebSocket auto-reconnect on disconnect, 2-second delay
- Dark theme; responsive 2-column grid layout
- No framework, no build step, no npm

**Arduino sketch**
- `Serial.begin(9600)` in `setup()`
- Emit one CSV line per second in `loop()` using `Serial.println()`
- Column order: `millis(),temp,humidity,lux`
- Floats to 1 decimal place; lux as integer
- Comment in the sketch: column order is the schema and must not be changed without updating the server parser

**Not in scope**
- Persistence of any kind
- Authentication
- External access
- HTTPS

---

## Output format

Deliver the project as a single directory `arduino-live/` with this exact structure:

```
arduino-live/
├── ARCHITECTURE.md          # provided — do not modify
├── requirements.txt
├── server.py
├── sources/
│   ├── __init__.py
│   ├── base.py
│   ├── serial_source.py
│   └── sim_source.py
├── static/
│   └── index.html
└── arduino/
    └── arduino_live.ino
```

`requirements.txt` must pin major versions:

```
fastapi>=0.111,<1.0
uvicorn[standard]>=0.29,<1.0
pyserial>=3.5,<4.0
```

The application must start and serve the simulator with a single command and no additional setup beyond `pip install -r requirements.txt`:

```bash
python server.py --source sim
```

Opening `http://localhost:8000` in a browser must immediately show live charts with no further configuration.
