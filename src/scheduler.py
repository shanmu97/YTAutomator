from __future__ import annotations
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from src.config import get_config
from src.pipeline import run_pipeline_once


def run_scheduler():
    cfg = get_config()
    scheduler = BlockingScheduler(timezone=pytz.timezone(cfg.timezone))

    for hour in (9, 14, 19):
        scheduler.add_job(run_pipeline_once, CronTrigger(hour=hour, minute=0))

    print(f"Scheduler started in timezone {cfg.timezone} for 09:00, 14:00, 19:00.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")
