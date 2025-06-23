from database.sqlalchemy_client import update_job_status
import os
import json
from typing import Dict, Any, Optional
import functions_framework
import requests
import structlog
from datetime import datetime
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure structured logging
logger = structlog.get_logger()

# Initialize clients
POSTMARK_API_TOKEN = os.environ["POSTMARK_API_TOKEN"]
POSTMARK_API_ENDPOINT = "https://api.postmarkapp.com/email"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to a human-readable string."""
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")

    return " ".join(parts)


def send_completion_email(email: str, stats: Dict[str, Any], job_id: str) -> None:
    """
    Send completion notification email using Postmark.

    Args:
        email: Recipient email address
        stats: Processing statistics
        job_id: Unique job identifier
    """
    logger.info("sending_email", email=email, job_id=job_id)

    # Update job status to completed
    try:
        update_job_status(job_id, "completed", stats)
    except Exception as e:
        logger.warning("failed_to_update_job_status",
                       job_id=job_id, error=str(e))

    # Format the processing time
    processing_time = format_duration(stats.get("processing_time", 0))

    # Create email content
    html_content = f"""
    <h2>Video Processing Complete</h2>
    <p>Your YouTube video has been processed and flashcards have been created!</p>
    
    <h3>Processing Statistics:</h3>
    <ul>
        <li><strong>Flashcards Created:</strong> {stats.get('cards_created', 0)}</li>
        <li><strong>New Vocabulary Words:</strong> {stats.get('new_words', 0)}</li>
        <li><strong>Processing Time:</strong> {processing_time}</li>
    </ul>
    
    <p>View your flashcards here: <a href="{os.environ.get('MOCHI_DECK_URL', '#')}">Open in Mochi</a></p>
    
    <p>Job ID: {job_id}</p>
    """

    # Prepare Postmark API request
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": POSTMARK_API_TOKEN,
    }

    payload = {
        "From": os.environ.get("SENDER_EMAIL", "noreply@instantcards.app"),
        "To": email,
        "Subject": "Your Flashcards are Ready! 🎉",
        "HtmlBody": html_content,
        "MessageStream": "outbound",  # Default transactional stream
        "TrackOpens": True,
        "Metadata": {"job_id": job_id},
    }

    try:
        response = requests.post(
            POSTMARK_API_ENDPOINT, headers=headers, json=payload)
        response.raise_for_status()

        logger.info(
            "email_sent",
            message_id=response.json().get("MessageID"),
            email=email,
            job_id=job_id,
        )

    except requests.exceptions.RequestException as e:
        logger.exception("email_send_failed", error=str(e),
                         email=email, job_id=job_id)
        raise


@functions_framework.http
def send_notification(request) -> tuple[Dict[str, Any], int]:
    """
    Cloud Function entry point.

    Expected request body:
    {
        "email": "user@example.com",
        "job_id": "job-123",
        "stats": {
            "cards_created": 42,
            "new_words": 38,
            "processing_time": 123.45
        }
    }
    """
    request_json = request.get_json()

    if not request_json:
        return {"error": "No request data provided"}, 400

    email = request_json.get("email")
    job_id = request_json.get("job_id")
    stats = request_json.get("stats", {})

    if not email:
        return {"error": "email is required"}, 400
    if not job_id:
        return {"error": "job_id is required"}, 400

    try:
        send_completion_email(email, stats, job_id)

        return {"status": "success", "message": f"Notification sent to {email}"}, 200

    except Exception as e:
        logger.exception(
            "notification_failed", error=str(e), email=email, job_id=job_id
        )
        return {"error": str(e), "status": "error"}, 500
