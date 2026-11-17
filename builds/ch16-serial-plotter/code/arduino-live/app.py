"""Flask web application that streams live Arduino sensor readings to browser clients via Server-Sent Events (SSE).

Design: single endpoint model — "/" serves the dashboard HTML, "/stream"
provides an SSE connection that parses raw serial CSV lines into JSON and
forwards them to both the browser and the CSV Logger. The mock/real serial
device is selected at import time by USE_MOCK, enabling hot-swap between
hardware and simulation without touching route logic.

Endpoints:
    GET  /              — Serves the main dashboard HTML (index.html template).
    GET  /stream        — SSE endpoint for live sensor streaming. Reads from the
        active serial device (MockSerial or SerialReader), parses CSV lines, logs
        to CSV, and streams JSON events to connected clients.
    GET  /stream/replay — SSE endpoint for replaying a previously recorded log
        file. Accepts query params: filename (required), speed (float, default 1.0).
        Streams readings at timing proportional to their original intervals.
    GET  /api/logs      — Returns a JSON list of available log files (filenames,
        human-readable labels, ISO timestamps).
    GET  /api/logs/<filename> — Returns full JSON data for a specific log file.

CSV format (positional): timestamp_ms,temperature_c,humidity_pct,lux
"""

import csv
import json
import os
import time

from datetime import datetime
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from config import LOG_DIR, USE_MOCK
from logger import Logger
from mock_serial import MockSerial
from serial_reader import SerialReader

app = Flask(__name__)

serial_dev = MockSerial() if USE_MOCK else SerialReader()
logger = Logger()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/logs")
def list_logs():
    """Return list of available log files with human-readable labels."""
    logs = []
    if not os.path.exists(LOG_DIR):
        return jsonify(logs)

    for fname in sorted(os.listdir(LOG_DIR), reverse=True):
        if not fname.endswith(".csv"):
            continue
        # Parse filename: YYYYMMDD_HHMMSS.csv
        try:
            dt = datetime.strptime(fname.replace(".csv", ""), "%Y%m%d_%H%M%S")
            label = dt.strftime("%Y-%m-%d %H:%M:%S")
            logs.append({
                "filename": fname,
                "label": label,
                "created_at": dt.isoformat()
            })
        except ValueError:
            continue

    return jsonify(logs)


@app.route("/api/logs/<filename>")
def get_log_data(filename):
    """Return full data from a specific log file."""
    # Security: prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"error": "Invalid filename"}), 400

    path = os.path.join(LOG_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": "Log file not found"}), 404

    readings = []
    try:
        with open(path, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    readings.append({
                        "timestamp_ms": int(row["timestamp_ms"]),
                        "temperature_c": float(row["temperature_c"]),
                        "humidity_pct": float(row["humidity_pct"]),
                        "lux": float(row["lux"]),
                    })
                except (ValueError, KeyError):
                    continue
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"filename": filename, "readings": readings})


@app.route("/stream/replay")
def stream_replay():
    """SSE endpoint that replays a log file at configurable speed."""
    filename = request.args.get("filename")
    speed = request.args.get("speed", "1", type=float)

    if not filename:
        def error_gen():
            yield f"data: {json.dumps({'error': 'filename required'})}\n\n"
        return Response(
            stream_with_context(error_gen()),
            content_type="text/event-stream"
        )

    # Security: prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        def error_gen():
            yield f"data: {json.dumps({'error': 'invalid filename'})}\n\n"
        return Response(
            stream_with_context(error_gen()),
            content_type="text/event-stream"
        )

    path = os.path.join(LOG_DIR, filename)
    if not os.path.exists(path):
        def error_gen():
            yield f"data: {json.dumps({'error': 'file not found'})}\n\n"
        return Response(
            stream_with_context(error_gen()),
            content_type="text/event-stream"
        )

    def generate_replay():
        readings = []
        try:
            with open(path, "r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        readings.append({
                            "timestamp_ms": int(row["timestamp_ms"]),
                            "temperature_c": float(row["temperature_c"]),
                            "humidity_pct": float(row["humidity_pct"]),
                            "lux": float(row["lux"]),
                        })
                    except (ValueError, KeyError):
                        continue
        except Exception:
            return

        if len(readings) < 2:
            for r in readings:
                yield f"data: {json.dumps(r)}\n\n"
            return

        # Stream with timing based on original intervals
        prev_ts = readings[0]["timestamp_ms"]
        for reading in readings[1:]:
            delta_ms = reading["timestamp_ms"] - prev_ts
            delay_s = (delta_ms / 1000.0) / max(speed, 0.1)
            time.sleep(min(delay_s, 0.5))  # cap max delay
            prev_ts = reading["timestamp_ms"]
            try:
                yield f"data: {json.dumps(reading)}\n\n"
            except GeneratorExit:
                return

    return Response(
        stream_with_context(generate_replay()),
        content_type="text/event-stream"
    )


@app.route("/stream")
def stream():
    def generate():
        logger.connect()
        try:
            while True:
                line = serial_dev.readline().decode("utf-8").strip()

                if not line:
                    continue

                parts = line.split(",")

                if len(parts) != 4:
                    continue

                if parts[0] == "timestamp_ms":
                    continue  # skip CSV header from Arduino

                try:
                    reading = {
                        "timestamp_ms":  int(parts[0]),
                        "temperature_c": float(parts[1]),
                        "humidity_pct":  float(parts[2]),
                        "lux":           float(parts[3]),
                    }
                except ValueError as e:
                    print(f"[stream] parse error: {e} — line: {line!r}")
                    continue

                logger.log(reading)

                try:
                    yield f"data: {json.dumps(reading)}\n\n"
                except GeneratorExit:
                    logger.disconnect()
                    return
        except Exception:
            pass
        finally:
            if logger.client_count > 0:
                logger.disconnect()

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
    )


if __name__ == "__main__":
    app.run(debug=True)