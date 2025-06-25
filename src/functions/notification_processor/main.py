import os
import smtplib
from typing import Dict, Any
import functions_framework
import structlog
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from db.main import get_session
from db.sqlacodegen import Job

logger = structlog.get_logger()


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
    Send completion notification email using SMTP.

    Args:
        email: Recipient email address
        stats: Processing statistics
        job_id: Unique job identifier
    """
    logger.info("sending_email", email=email, job_id=job_id)

    processing_time = format_duration(stats.get("processing_time", 0))
    sender_email = os.environ.get("SENDER_EMAIL")
    sender_password = os.environ.get("SENDER_PASSWORD")

    if not sender_email:
        raise ValueError("SENDER_EMAIL environment variable is required")
    if not sender_password:
        raise ValueError("SENDER_PASSWORD environment variable is required")

    session = get_session()
    with session.begin():
        job = session.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job with id {job_id} not found")

    html_content = f"""
    <h2>instantcards: {job.name}</h2>
    <p>Some stats:</p>
    
    <ul>
        <li><strong>Flashcards Created:</strong> {stats.get('cards_created', 0)}</li>
        <li><strong>New Vocabulary Words:</strong> {stats.get('new_words', 0)}</li>
        <li><strong>Processing Time:</strong> {processing_time}</li>
    </ul>
    
    <p>View your flashcards here: <a href="{os.environ.get('MOCHI_DECK_URL', '#')}">Open in Mochi</a></p>
    
    <p>Job ID: {job_id}</p>
    """

    message = MIMEMultipart('alternative')
    message['From'] = sender_email
    message['To'] = email
    message['Subject'] = "Your Flashcards are Ready! 🎉"

    html_part = MIMEText(html_content, 'html')
    message.attach(html_part)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)

        text = message.as_string()
        server.sendmail(sender_email, email, text)
        server.quit()

        logger.info(
            "email_sent",
            email=email,
            job_id=job_id,
        )

    except Exception as e:
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
