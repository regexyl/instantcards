import os
from google.cloud import storage
from openai import NotGiven, OpenAI
import srt
import tempfile
from typing import Optional
import structlog

logger = structlog.get_logger()

openai_client = OpenAI()

def get_media_bucket() -> storage.Bucket:
    """Get the media storage bucket."""
    bucket_name = os.environ.get("MEDIA_BUCKET")
    if not bucket_name:
        raise ValueError("MEDIA_BUCKET environment variable not set")
    storage_client = storage.Client()
    return storage_client.bucket(bucket_name)


async def transcribe_audio(audio_path: str, from_language: Optional[str] = None) -> str:
    """
    Transcribe audio file using OpenAI Whisper.

    Args:
        audio_path: Path to audio file in Cloud Storage
        from_language: Optional language hint for transcription

    Returns:
        SRT transcription text
    """
    logger.info("transcribing_audio", audio_path=audio_path,
                from_language=from_language)

    storage_client = storage.Client()
    bucket = storage_client.bucket(os.environ.get("MEDIA_BUCKET"))
    blob = bucket.blob(audio_path)

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
        blob.download_to_file(temp_file)
        temp_file_path = temp_file.name

    try:
        with open(temp_file_path, "rb") as audio_file:
            transcription_text = openai_client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-1",
                response_format="srt",
                language=from_language if from_language else NotGiven()
            )

            srt.make_legal_content(transcription_text)

            logger.info("transcription_complete",
                        audio_path=audio_path,
                        text_length=len(transcription_text))

            return transcription_text

    finally:
        os.unlink(temp_file_path)