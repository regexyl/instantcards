from db.sqlacodegen import Job
from db.main import get_session
import os
from typing import Dict, Any, Optional
import functions_framework
import structlog
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = structlog.get_logger()


def create_job(job_id: str, video_url: str) -> Dict[str, Any]:
    """
    Create a new job record.

    Args:
        job_id: Unique job identifier (workflow_id)
        video_url: URL of the video being processed

    Returns:
        Created job record as dictionary
    """
    session = get_session()

    with session.begin():
        job = Job(
            workflow_id=job_id,
            source_url=video_url,
        )
        session.add(job)
        logger.info("job_created_in_db", job_id=job_id, db_id=job.id)
        return job.to_dict()


def get_job_with_details(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Get job details from database using SQLAlchemy.

    Args:
        job_id: Unique job identifier (workflow_id)

    Returns:
        Job details as dictionary or None if not found
    """
    session = get_session()

    with session.begin():
        job = session.query(Job).filter(Job.workflow_id == job_id).first()

        if not job:
            logger.info("job_not_found", job_id=job_id)
            return None

        logger.info("job_retrieved_from_db", job_id=job_id, db_id=job.id)
        return job.to_dict()


def get_job_status(job_id: str) -> tuple[Dict[str, Any], int]:
    """
    Get job status and details.

    Args:
        job_id: Unique job identifier

    Returns:
        Job details with status
    """
    logger.info("getting_job_status", job_id=job_id)

    try:
        job_details = get_job_with_details(job_id)
        if not job_details:
            return {"error": "Job not found"}, 404

        return {"status": "success", "job": job_details}, 200
    except Exception as e:
        logger.exception("failed_to_get_job_status",
                         job_id=job_id, error=str(e))
        return {"error": str(e)}, 500


@functions_framework.http
def manage_job(request) -> tuple[Dict[str, Any], int]:
    """
    Cloud Function entry point for job management.

    Expected request body for job creation:
    {
        "action": "create",
        "job_id": "job-123",
        "user_email": "user@example.com",
        "video_url": "https://youtube.com/watch?v=..."
    }

    Expected request body for job status:
    {
        "action": "status",
        "job_id": "job-123"
    }
    """
    request_json = request.get_json()

    if not request_json:
        return {"error": "No request data provided"}, 400

    action = request_json.get("action")

    if action == "create":
        job_id = request_json.get("job_id")
        video_url = request_json.get("video_url")

        if not all([job_id, video_url]):
            return {"error": "job_id and video_url are required for job creation"}, 400

        try:
            job_record = create_job(job_id, video_url)
            return {"status": "success", "job": job_record}, 201
        except Exception as e:
            logger.exception("job_creation_failed", error=str(e))
            return {"error": str(e), "status": "error"}, 500

    elif action == "status":
        job_id = request_json.get("job_id")

        if not job_id:
            return {"error": "job_id is required for status check"}, 400

        return get_job_status(job_id)

    else:
        return {"error": "Invalid action. Use 'create' or 'status'"}, 400
