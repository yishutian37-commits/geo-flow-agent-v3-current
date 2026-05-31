import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.tasks.celery_app import celery_app
from app.core.database import sync_engine
from app.models.monitoring import MonitoringRun

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def run_monitoring_task(self, monitoring_run_id: str):
    """
    Execute a monitoring run and calculate metrics.
    Skeleton implementation: updates run status and simulates sample collection.
    """
    logger.info(f"[Monitoring] Starting monitoring run {monitoring_run_id}")

    with Session(sync_engine) as db:
        run = db.query(MonitoringRun).filter(MonitoringRun.id == monitoring_run_id).first()
        if not run:
            logger.error(f"[Monitoring] Run {monitoring_run_id} not found")
            return {"status": "failed", "error": "Run not found", "monitoring_run_id": monitoring_run_id}
        run.status = "running"
        db.commit()

    try:
        # Step 1: Load questions
        self.update_state(state="PROGRESS", meta={"step": "loading_questions", "progress": 10})
        logger.info(f"[Monitoring] Loading questions for run {monitoring_run_id}")

        # Step 2: Query AI models (placeholder)
        self.update_state(state="PROGRESS", meta={"step": "querying_ai", "progress": 40})
        logger.info(f"[Monitoring] Querying AI models for run {monitoring_run_id}")

        # Step 3: Collect samples (placeholder)
        self.update_state(state="PROGRESS", meta={"step": "collecting_samples", "progress": 70})
        logger.info(f"[Monitoring] Collecting samples for run {monitoring_run_id}")

        # Step 4: Calculate metrics
        self.update_state(state="PROGRESS", meta={"step": "calculating_metrics", "progress": 90})
        logger.info(f"[Monitoring] Calculating metrics for run {monitoring_run_id}")

        # Mark run as completed
        with Session(sync_engine) as db:
            run = db.query(MonitoringRun).filter(MonitoringRun.id == monitoring_run_id).first()
            if run:
                run.status = "completed"
                run.ended_at = datetime.now(timezone.utc)
                db.commit()

        logger.info(f"[Monitoring] Completed monitoring run {monitoring_run_id}")
        return {"status": "completed", "monitoring_run_id": monitoring_run_id}

    except Exception as exc:
        logger.exception(f"[Monitoring] Failed run {monitoring_run_id}")
        with Session(sync_engine) as db:
            run = db.query(MonitoringRun).filter(MonitoringRun.id == monitoring_run_id).first()
            if run:
                run.status = "failed"
                db.commit()
        raise self.retry(exc=exc, countdown=60)
