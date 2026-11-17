"""Alternative entry point using waitress WSGI server for production deployment.

Design: app.py uses Flask's built-in development server (flask run or python app.py)
which is single-threaded blocking for SSE connections. This module serves the same
Flask app via waitress, enabling concurrent SSE client handling in production.

Usage:
    python server.py          # Starts waitress on host 0.0.0.0, port 5000
"""

from waitress import serve

from app import app

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=5000)