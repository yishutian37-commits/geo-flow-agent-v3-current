import logging
import asyncio
from urllib.parse import urlencode
from uuid import UUID

from app.tasks.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.services.report_service import ReportService

logger = logging.getLogger(__name__)


async def _generate_report_payload(project_id: str, report_type: str) -> dict:
    async with AsyncSessionLocal() as db:
        service = ReportService(db)
        parsed_project_id = UUID(project_id)
        if report_type == "internal":
            return await service.generate_internal_report(parsed_project_id)
        return await service.generate_client_report(parsed_project_id)


def _markdown_url(project_id: str, report_type: str) -> str:
    return "/api/v1/reports/markdown?" + urlencode({
        "project_id": project_id,
        "report_type": report_type,
    })


@celery_app.task(bind=True)
def generate_report(self, project_id: str, report_type: str = "client"):
    """
    Generate client or internal report using the same service as the HTTP report endpoints.
    """
    logger.info(f"[Report] Starting {report_type} report generation for project {project_id}")
    if report_type not in {"client", "internal"}:
        return {"status": "failed", "error": "Invalid report type", "project_id": project_id, "report_type": report_type}

    try:
        # Step 1: Gather data
        self.update_state(state="PROGRESS", meta={"step": "gathering_data", "progress": 20})
        logger.info(f"[Report] Gathering data for project {project_id}")

        # Step 2: Aggregate metrics
        self.update_state(state="PROGRESS", meta={"step": "aggregating_metrics", "progress": 50})
        logger.info(f"[Report] Aggregating metrics for project {project_id}")

        # Step 3: Generate document
        self.update_state(state="PROGRESS", meta={"step": "generating_document", "progress": 80})
        logger.info(f"[Report] Generating document for project {project_id}")
        report = asyncio.run(_generate_report_payload(project_id, report_type))
        if "error" in report:
            logger.error(f"[Report] {report['error']} for project {project_id}")
            return {"status": "failed", "error": report["error"], "project_id": project_id, "report_type": report_type}

        logger.info(f"[Report] Completed {report_type} report for project {project_id}")
        return {
            "status": "completed",
            "project_id": project_id,
            "report_type": report_type,
            "download_url": _markdown_url(project_id, report_type),
            "report": report,
        }

    except Exception as exc:
        logger.exception(f"[Report] Failed to generate report for project {project_id}")
        raise self.retry(exc=exc, countdown=60)
