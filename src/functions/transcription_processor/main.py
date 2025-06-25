import asyncio
from typing import Dict, Any, Optional
import functions_framework
from openai import NotGiven, OpenAI
import structlog

from functions.transcription_processor.create_block_cards import create_block_cards
from functions.transcription_processor.transcribe import transcribe_audio

from .create_atom_cards import create_atom_cards
from .extract_atoms import extract_atoms
from .translate import translate
from .store_audio import store_audio
from .classes import Translation


logger = structlog.get_logger()


async def process_translation_parallel(translation: Translation, name: str, job_id: str, original_audio_path: str) -> Dict[str, Any]:
    """
    Execute the three processing functions in parallel.

    Args:
        translation: Translation object with transcription data
        name: Name of the audio file
        job_id: Unique job identifier
        original_audio_path: Path to original audio file in Cloud Storage

    Returns:
        Combined results from all three functions
    """
    logger.info("starting_parallel_processing", job_id=job_id)

    store_audio_task = asyncio.create_task(
        asyncio.to_thread(store_audio, translation,
                          job_id, original_audio_path)
    )
    translate_task = asyncio.create_task(
        asyncio.to_thread(translate, translation, job_id)
    )

    def extract_and_create_atom_cards(translation: Translation, job_id: str) -> None:
        extract_atoms(translation, job_id)
        create_atom_cards(translation)

    extract_and_create_atom_cards_task = asyncio.create_task(
        asyncio.to_thread(extract_and_create_atom_cards, translation, job_id)
    )

    store_result, translate_result, extract_and_create_atom_cards_result = await asyncio.gather(
        store_audio_task, translate_task, extract_and_create_atom_cards_task, return_exceptions=True
    )

    create_block_cards(translation, name)

    results = {}
    for result, name in [(store_result, "store_audio"),
                         (translate_result, "translate"),
                         (extract_and_create_atom_cards_result, "extract_and_create_atom_cards")]:
        if isinstance(result, Exception):
            logger.error(f"{name}_failed", job_id=job_id, error=str(result))
            results[name] = {"error": str(result)}
        else:
            results[name] = result

    results["translation_data"] = translation.to_dict()

    logger.info("parallel_processing_complete",
                job_id=job_id,
                store_success=not isinstance(store_result, Exception),
                translate_success=not isinstance(translate_result, Exception),
                extract_success=not isinstance(extract_and_create_atom_cards_result, Exception))

    return results


async def transcribe_and_process_audio(audio_path: str, name: str, job_id: str, from_language: Optional[str] = None) -> Dict[str, Any]:
    """
    Main function: transcribe audio and process in parallel.

    Args:
        audio_path: Path to audio file in Cloud Storage
        name: Name of the audio file
        job_id: Unique job identifier
        from_language: Optional language hint for transcription

    Returns:
        Complete processing results
    """
    logger.info("starting_transcription_and_processing",
                audio_path=audio_path, job_id=job_id, from_language=from_language)

    try:
        transcription_text = await transcribe_audio(audio_path, from_language)
        translation = Translation(transcription_text)
        results = await process_translation_parallel(translation, name, job_id, audio_path)

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
    name = request_json.get("name")
    job_id = request_json.get("job_id")
    from_language = request_json.get("from_language")

    if not name:
        return {"error": "name is required"}, 400
    if not audio_path:
        return {"error": "audio_path is required"}, 400
    if not job_id:
        return {"error": "job_id is required"}, 400

    try:
        result = asyncio.run(
            transcribe_and_process_audio(
                audio_path, name, job_id, from_language)
        )

        return {"status": "success", **result}, 200

    except Exception as e:
        logger.exception("process_transcription_and_translation_failed",
                         error=str(e), audio_path=audio_path, job_id=job_id)
        return {"error": str(e), "status": "error"}, 500
