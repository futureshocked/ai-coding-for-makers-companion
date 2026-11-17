"""Standalone scheduler process for the production `scheduler` Docker service.

Runs APScheduler in its own container so multi-worker gunicorn doesn't fire
reminder emails N times. In development, leave RUN_SCHEDULER unset and the
in-process scheduler in app/__init__.py handles reminders.
"""
import logging
import os
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from app import create_app
from app.services.reminders import send_due_reminders


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("scheduler")

    config_name = os.environ.get("FLASK_CONFIG", "production")
    app = create_app(config_name)
    hours = app.config["REMINDER_INTERVAL_HOURS"]

    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(
        send_due_reminders,
        "interval",
        hours=hours,
        args=[app],
        id="booking_reminders",
        replace_existing=True,
        next_run_time=None,
    )

    def _shutdown(signum, _frame):
        log.info("Received signal %s, shutting down scheduler.", signum)
        sched.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info("Scheduler starting; interval=%sh", hours)
    sched.start()


if __name__ == "__main__":
    main()
