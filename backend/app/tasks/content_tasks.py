import logging
from sqlalchemy.orm import Session

from app.tasks.celery_app import celery_app
from app.core.database import sync_engine
from app.models.content_task import ContentTask

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def generate_content_draft(self, content_task_id: str):
    """
    Generate content draft using LLM.
    Skeleton implementation: updates task status and simulates progress.
    """
    logger.info(f"[ContentTask] Starting draft generation for task {content_task_id}")

    # Mark task as in_progress
    with Session(sync_engine) as db:
        task = db.query(ContentTask).filter(ContentTask.id == content_task_id).first()
        if not task:
            logger.error(f"[ContentTask] Task {content_task_id} not found")
            return {"status": "failed", "error": "Task not found", "content_task_id": content_task_id}
        task.status = "in_progress"
        db.commit()

    try:
        # Step 1: Prepare facts
        self.update_state(state="PROGRESS", meta={"step": "preparing_facts", "progress": 20})
        logger.info(f"[ContentTask] Preparing brand facts for task {content_task_id}")

        # Step 2: Call LLM (placeholder)
        self.update_state(state="PROGRESS", meta={"step": "calling_llm", "progress": 50})
        logger.info(f"[ContentTask] Calling LLM for task {content_task_id}")

        # Step 3: Compliance check
        self.update_state(state="PROGRESS", meta={"step": "compliance_check", "progress": 80})
        logger.info(f"[ContentTask] Running compliance check for task {content_task_id}")

        # Mark task as completed
        with Session(sync_engine) as db:
            task = db.query(ContentTask).filter(ContentTask.id == content_task_id).first()
            if task:
                task.status = "completed"
                db.commit()

        logger.info(f"[ContentTask] Completed draft generation for task {content_task_id}")
        return {"status": "completed", "content_task_id": content_task_id}

    except Exception as exc:
        logger.exception(f"[ContentTask] Failed to generate draft for task {content_task_id}")
        with Session(sync_engine) as db:
            task = db.query(ContentTask).filter(ContentTask.id == content_task_id).first()
            if task:
                task.status = "failed"
                db.commit()
        raise self.retry(exc=exc, countdown=60)
