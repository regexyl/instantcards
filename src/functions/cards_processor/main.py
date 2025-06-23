import os
import json
from typing import Dict, Any, List, Optional
import functions_framework
from google.cloud import storage
import structlog
import requests
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure structured logging
logger = structlog.get_logger()

# Initialize clients
storage_client = storage.Client()


def get_media_bucket() -> storage.Bucket:
    """Get the media storage bucket."""
    bucket_name = os.environ.get("MEDIA_BUCKET")
    if not bucket_name:
        raise ValueError("MEDIA_BUCKET environment variable not set")
    return storage_client.bucket(bucket_name)


def create_mochi_cards(translation_data: Dict[str, Any], job_id: str) -> Dict[str, Any]:
    """
    Create flashcards in Mochi.

    Args:
        translation_data: Translation and vocabulary data
        job_id: Unique job identifier

    Returns:
        Dictionary containing card creation results
    """
    logger.info("creating_cards", job_id=job_id)

    # Update job status to processing cards
    try:
        update_job_status(job_id, "processing", {"step": "cards_creation"})
    except Exception as e:
        logger.warning("failed_to_update_job_status",
                       job_id=job_id, error=str(e))

    try:
        # TODO: Implement Mochi API integration
        # This is a stub that will be implemented when we have the API details

        cards_created = len(translation_data.get("vocabulary", []))

        # Mock deck data for now
        cards_data = {
            "cards_created": cards_created,
            "deck_id": f"deck_{job_id}",
            "deck_url": f"https://app.mochi.cards/decks/deck_{job_id}"
        }

        # Store cards data in database
        try:
            store_cards_data(job_id, cards_data)
            update_job_status(job_id, "cards_complete", {
                "cards_created": cards_created,
                "deck_id": cards_data["deck_id"]
            })
        except Exception as e:
            logger.warning("failed_to_store_cards_in_db",
                           job_id=job_id, error=str(e))

        logger.info("cards_created", count=cards_created, job_id=job_id)

        return cards_data

    except Exception as e:
        # Update job status to failed
        try:
            update_job_status(job_id, "failed", {
                              "error": str(e), "step": "cards_creation"})
        except Exception as db_error:
            logger.warning("failed_to_update_job_status_on_error",
                           job_id=job_id, error=str(db_error))

        logger.exception("cards_creation_failed", error=str(e), job_id=job_id)
        raise


@functions_framework.http
def create_cards(request) -> tuple[Dict[str, Any], int]:
    """
    Cloud Function entry point.

    Expected request body:
    {
        "translation_data": {
            "original_text": "...",
            "translated_text": "...",
            "vocabulary": [...],
            "word_timings": [...]
        },
        "job_id": "job-123"
    }
    """
    request_json = request.get_json()

    if not request_json:
        return {"error": "No request data provided"}, 400

    translation_data = request_json.get("translation_data")
    job_id = request_json.get("job_id")

    if not translation_data:
        return {"error": "translation_data is required"}, 400
    if not job_id:
        return {"error": "job_id is required"}, 400

    try:
        result = create_mochi_cards(translation_data, job_id)

        return {"status": "success", **result}, 200

    except Exception as e:
        logger.exception("create_cards_failed", error=str(e), job_id=job_id)
        return {"error": str(e), "status": "error"}, 500
