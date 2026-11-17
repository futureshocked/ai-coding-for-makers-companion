#!/usr/bin/env bash
set -e

# Change to script's directory, then into arduino-live/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/arduino-live"

# Activate Python virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
  source "venv/bin/activate"
fi

# Start app.py in the background
python app.py &
APP_PID=$!

# Wait for server to start
sleep 2

# Check if process is still running
if ! kill -0 "$APP_PID" 2>/dev/null; then
  echo "ERROR: app.py failed to start"
  exit 1
fi

# Detect OS and open browser in new tab
OS_NAME="$(uname)"
if [ "$OS_NAME" = "Darwin" ]; then
  open "http://localhost:5000"
elif [ "$OS_NAME" = "Linux" ]; then
  (xdg-open "http://localhost:5000" 2>/dev/null || \
    google-chrome --new-tab "http://localhost:5000" 2>/dev/null || \
    firefox --new-tab "http://localhost:5000" 2>/dev/null) &
else
  echo "WARNING: Unknown OS. Manual URL: http://localhost:5000"
fi

# Wait for background process to keep script alive
wait "$APP_PID"