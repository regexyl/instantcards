import os
import json
from typing import Dict, Any
import functions_framework
from google.cloud import storage
from google.cloud import speech_v1
import structlog

# Configure structured logging
logger = structlog.get_logger()

# Initialize clients
storage_client = storage.Client()
speech_client = speech_v1.SpeechClient()


def get_media_bucket() -> storage.Bucket:
    """Get the media storage bucket."""
    bucket_name = os.environ.get("MEDIA_BUCKET")
    if not bucket_name:
        raise ValueError("MEDIA_BUCKET environment variable not set")
    return storage_client.bucket(bucket_name)


def transcribe_audio(audio_path: str, job_id: str) -> Dict[str, Any]:
    """
    Transcribe audio file using Google Speech-to-Text.

    Args:
        audio_path: Path to audio file in Cloud Storage
        job_id: Unique job identifier

    Returns:
        Dictionary with transcription results
    """
    logger.info("transcribing_audio", audio_path=audio_path, job_id=job_id)

    # Get audio file from Cloud Storage
    bucket = get_media_bucket()
    blob = bucket.blob(audio_path)

    # Download audio content
    audio_content = blob.download_as_bytes()

    # Configure speech recognition
    audio = speech_v1.RecognitionAudio(content=audio_content)
    config = speech_v1.RecognitionConfig(
        encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="ja-JP",
        enable_word_time_offsets=True,
        enable_automatic_punctuation=True,
    )

    try:
        # Start long-running recognition operation
        operation = speech_client.long_running_recognize(config=config, audio=audio)

        logger.info(
            "waiting_for_operation",
            operation_id=operation.operation.name,
            job_id=job_id,
        )

        # Wait for operation to complete
        response = operation.result()

        # Process results into a more structured format with timing
        transcription = []
        for result in response.results:
            for word_info in result.alternatives[0].words:
                transcription.append(
                    {
                        "word": word_info.word,
                        "start_time": word_info.start_time.total_seconds(),
                        "end_time": word_info.end_time.total_seconds(),
                        "confidence": result.alternatives[0].confidence,
                    }
                )

        # Save transcription to GCS
        bucket = get_media_bucket()
        transcript_path = f"transcripts/{job_id}/transcript.json"
        blob = bucket.blob(transcript_path)

        blob.upload_from_string(
            json.dumps(
                {"job_id": job_id, "language": "ja-JP", "words": transcription},
                ensure_ascii=False,
            ),
            content_type="application/json",
        )

        logger.info(
            "transcription_complete",
            transcript_path=transcript_path,
            word_count=len(transcription),
        )

        return {
            "transcript_path": transcript_path,
            "word_count": len(transcription),
            "language": "ja-JP",
        }

    except Exception as e:
        logger.exception(
            "transcription_failed", error=str(e), audio_path=audio_path, job_id=job_id
        )
        raise


@functions_framework.http
def process_transcription(request) -> Dict[str, Any]:
    """
    Cloud Function entry point.

    Expected request body:
    {
        "audio_path": "audio/job-123/audio.wav",
        "job_id": "job-123"
    }
    """
    request_json = request.get_json()

    if not request_json:
        return {"error": "No request data provided"}, 400

    audio_path = request_json.get("audio_path")
    job_id = request_json.get("job_id")

    if not audio_path:
        return {"error": "audio_path is required"}, 400
    if not job_id:
        return {"error": "job_id is required"}, 400

    try:
        result = transcribe_audio(audio_path, job_id)

        return {"status": "success", **result}

    except Exception as e:
        logger.exception(
            "process_transcription_failed",
            error=str(e),
            audio_path=audio_path,
            job_id=job_id,
        )
        return {"error": str(e), "status": "error"}, 500
