import os
import asyncio
from typing import Dict, Any, Optional
import functions_framework
from google.cloud import storage
from openai import NotGiven, OpenAI
import structlog
import srt
import tempfile
from .extract_atoms import extract_atoms
from .translate import translate
from .store_audio import store_audio
from .classes import Translation


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

            # Make SRT content legal
            srt.make_legal_content(transcription_text)

            logger.info("transcription_complete",
                        audio_path=audio_path,
                        text_length=len(transcription_text))

            return transcription_text

    finally:
        # Clean up the temporary file
        os.unlink(temp_file_path)


async def process_translation_parallel(translation: Translation, job_id: str, original_audio_path: str) -> Dict[str, Any]:
    """
    Execute the three processing functions in parallel.

    Args:
        translation: Translation object with transcription data
        job_id: Unique job identifier
        original_audio_path: Path to original audio file in Cloud Storage

    Returns:
        Combined results from all three functions
    """
    logger.info("starting_parallel_processing", job_id=job_id)

    # Create tasks for parallel execution
    store_audio_task = asyncio.create_task(
        asyncio.to_thread(store_audio, translation,
                          job_id, original_audio_path)
    )
    translate_task = asyncio.create_task(
        asyncio.to_thread(translate, translation, job_id)
    )
    extract_task = asyncio.create_task(
        asyncio.to_thread(extract_atoms, translation, job_id)
    )

    store_result, translate_result, extract_result = await asyncio.gather(
        store_audio_task, translate_task, extract_task, return_exceptions=True
    )

    results = {}
    for result, name in [(store_result, "store_audio"),
                         (translate_result, "translate"),
                         (extract_result, "extract_atoms")]:
        if isinstance(result, Exception):
            logger.error(f"{name}_failed", job_id=job_id, error=str(result))
            results[name] = {"error": str(result)}
        else:
            results[name] = result

    # Add combined translation data
    results["translation_data"] = translation.to_dict()

    logger.info("parallel_processing_complete",
                job_id=job_id,
                store_success=not isinstance(store_result, Exception),
                translate_success=not isinstance(translate_result, Exception),
                extract_success=not isinstance(extract_result, Exception))

    return results


async def transcribe_and_process_audio(audio_path: str, job_id: str, from_language: Optional[str] = None) -> Dict[str, Any]:
    """
    Main function: transcribe audio and process in parallel.

    Args:
        audio_path: Path to audio file in Cloud Storage
        job_id: Unique job identifier
        from_language: Optional language hint for transcription

    Returns:
        Complete processing results
    """
    logger.info("starting_transcription_and_processing",
                audio_path=audio_path, job_id=job_id, from_language=from_language)

    try:
        # Step 1: Transcribe audio
        transcription_text = await transcribe_audio(audio_path, from_language)

        # Step 2: Create Translation object
        translation = Translation(transcription_text)

        # Step 3: Process in parallel
        results = await process_translation_parallel(translation, job_id, audio_path)

        # Add metadata
        results["job_id"] = job_id
        results["audio_path"] = audio_path
        results["blocks_count"] = translation.get_block_count()
        results["duration"] = translation.get_duration()
        results["total_atoms"] = translation.get_total_atoms()
        results["new_atoms"] = translation.get_new_atoms_count()
        results["audio_segments_count"] = translation.get_audio_segments_count()

        logger.info("transcription_and_processing_complete",
                    job_id=job_id,
                    blocks_count=translation.get_block_count(),
                    total_atoms=translation.get_total_atoms())

        return results

    except Exception as e:
        logger.exception("transcription_and_processing_failed",
                         job_id=job_id, audio_path=audio_path, error=str(e))
        raise


@functions_framework.http
def process_transcription_and_translation(request) -> tuple[Dict[str, Any], int]:
    """
    Cloud Function entry point.

    Expected request body:
    {
        "audio_path": "audio/job-123/audio.wav",
        "job_id": "job-123",
        "from_language": "ja"  # Optional language hint
    }
    """
    request_json = request.get_json()

    if not request_json:
        return {"error": "No request data provided"}, 400

    audio_path = request_json.get("audio_path")
    job_id = request_json.get("job_id")
    from_language = request_json.get("from_language")

    if not audio_path:
        return {"error": "audio_path is required"}, 400
    if not job_id:
        return {"error": "job_id is required"}, 400

    try:
        # Run the async function
        result = asyncio.run(
            transcribe_and_process_audio(audio_path, job_id, from_language)
        )

        return {"status": "success", **result}, 200

    except Exception as e:
        logger.exception("process_transcription_and_translation_failed",
                         error=str(e), audio_path=audio_path, job_id=job_id)
        return {"error": str(e), "status": "error"}, 500
