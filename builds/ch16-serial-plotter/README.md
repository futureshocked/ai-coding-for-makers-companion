# Chapters 7–16: Arduino serial data plotter

A local web dashboard that reads temperature, humidity and light readings from an Arduino over USB serial and plots them live in the browser. It logs every session to CSV and can replay old logs. It runs on simulated data, so you don't need a board to try it.

Part II of the book (Chapters 7–13) teaches the workflow using this project as the running example, and Chapter 16 is the complete build.

## Read these first

| File | What it is |
|---|---|
| [`code/documentation/AGENT_SPEC.md`](code/documentation/AGENT_SPEC.md) | The specification given to the coding agent: task, context, constraints and output format |
| [`code/documentation/ARCHITECTURE.md`](code/documentation/ARCHITECTURE.md) | The architecture document the agent worked from |
| [`prompts.md`](prompts.md) | The build prompts from Chapter 16, in order |

## Folder layout

| Path | What it is |
|---|---|
| `code/arduino-live/` | The Flask application. Its own [`README.md`](code/arduino-live/README.md) documents every feature. |
| `code/arduino_sketches/serial_port_sim.ino` | Arduino sketch that sends simulated sensor readings, one CSV line per second, for testing with a real board. The prompt in the chapter asks for `serial_plotter_sim.ino`; this is the file that prompt produced. |
| `code/start.sh` | Starts the app and opens the browser (Linux and macOS). |

## Run it

You need Python 3.10 or newer ([install guide](../../setup/01-install-tools.md)).

```bash
cd code/arduino-live
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open <http://localhost:5000>. With `USE_MOCK = True` in `config.py` (the default), the charts fill with simulated data straight away.

On Linux or macOS you can use `./start.sh` from the `code/` folder instead, once the virtual environment exists.

`server.py` is an alternative entry point that uses the Waitress server for several browsers at once. It needs one extra package: `pip install waitress`.

## Use a real Arduino

1. Upload `code/arduino_sketches/serial_port_sim.ino` to your board with the Arduino IDE, and close the IDE's Serial Monitor (only one program can hold the port).
2. In `code/arduino-live/config.py`, set `USE_MOCK = False` and set `SERIAL_PORT` to your board's port. `config.py` holds the port from the book's build machine; yours will almost certainly differ. Run `python -m serial.tools.list_ports` to list the ports. On Windows the port looks like `COM3`; on macOS, `/dev/cu.usbmodem…`; on Linux, `/dev/ttyACM0`.
3. Restart the app.

To use your own sensors, keep the line format exactly as `timestamp_ms,temperature_c,humidity_pct,lux`. The column order is the format.
