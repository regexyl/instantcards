import os
import json
from typing import Dict, Any, List
import functions_framework
from google.cloud import storage
from google.cloud import translate_v2
import google.cloud.aiplatform as aiplatform
from vertexai.language_models import TextGenerationModel
import structlog

# Configure structured logging
logger = structlog.get_logger()

# Initialize clients
storage_client = storage.Client()
translate_client = translate_v2.Client()


def get_media_bucket() -> storage.Bucket:
    """Get the media storage bucket."""
    bucket_name = os.environ.get("MEDIA_BUCKET")
    if not bucket_name:
        raise ValueError("MEDIA_BUCKET environment variable not set")
    return storage_client.bucket(bucket_name)


def extract_vocabulary(text: str, target_language: str) -> List[Dict[str, Any]]:
    """
    Extract vocabulary words from text using AI.

    Args:
        text: Text to analyze
        target_language: Target language for translation

    Returns:
        List of vocabulary words with translations
    """
    logger.info(
        "extracting_vocabulary", text_length=len(text), target_language=target_language
    )

    # Use Vertex AI to extract vocabulary
    aiplatform.init(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    model = TextGenerationModel.from_pretrained("text-bison@001")

    prompt = f"""
    Extract vocabulary words from this {target_language} text that would be useful for language learning.
    Focus on words that are:
    1. Common and frequently used
    2. Appropriate for intermediate learners
    3. Not too basic (like "the", "is", "and")
    
    Text: {text[:1000]}  # Limit to first 1000 chars for analysis
    
    Return a JSON array of objects with:
    - word: the vocabulary word
    - reading: pronunciation/reading (if applicable)
    - translation: English translation
    - part_of_speech: noun, verb, adjective, etc.
    - jlpt_level: estimated JLPT level (N5-N1)
    - example_jp: example sentence in {target_language}
    - example_en: example sentence in English
    
    Format as valid JSON array.
    """

    response = model.predict(prompt, max_output_tokens=1024, temperature=0.1)

    try:
        # Parse the response as JSON
        vocabulary = json.loads(response.text)
        logger.info("vocabulary_extracted", count=len(vocabulary))
        return vocabulary
    except json.JSONDecodeError:
        logger.warning("failed_to_parse_vocabulary", response=response.text)
        return []


def translate_text(text: str, target_language: str) -> str:
    """
    Translate text to target language.

    Args:
        text: Text to translate
        target_language: Target language code

    Returns:
        Translated text
    """
    logger.info(
        "translating_text", text_length=len(text), target_language=target_language
    )

    # For Japanese to English translation
    if target_language == "en":
        result = translate_client.translate(text, target_language="en")
        return result["translatedText"]
    else:
        # For other languages, translate to English
        result = translate_client.translate(text, target_language="en")
        return result["translatedText"]


def process_transcript(
    transcript_path: str, target_language: str, job_id: str
) -> Dict[str, Any]:
    """
    Process transcript and extract vocabulary.

    Args:
        transcript_path: Path to transcript file
        target_language: Target language for translation
        job_id: Unique job identifier

    Returns:
        Dictionary with processed results
    """
    logger.info("processing_transcript",
                transcript_path=transcript_path, job_id=job_id)

    # Load transcript from Cloud Storage
    bucket = get_media_bucket()
    blob = bucket.blob(transcript_path)
    transcript_data = json.loads(blob.download_as_text())

    # Extract words and their timings
    words = transcript_data.get("words", [])
    word_timings = [(word["word"], word["start_time"]) for word in words]

    # Combine words into sentences for translation
    sentences = []
    current_sentence = []

    for word, timestamp in word_timings:
        current_sentence.append(word)
        if word.endswith((".", "。", "!", "！", "?", "？")):
            sentences.append((" ".join(current_sentence), timestamp))
            current_sentence = []

    if current_sentence:
        sentences.append((" ".join(current_sentence), word_timings[-1][1]))

    # Translate sentences
    translated_sentences = []
    for sentence, timestamp in sentences:
        translated = translate_text(sentence, target_language)
        translated_sentences.append(
            {"original": sentence, "translated": translated, "timestamp": timestamp}
        )

    # Extract vocabulary from the full text
    full_text = " ".join([word for word, _ in word_timings])
    vocabulary = extract_vocabulary(full_text, target_language)

    # Save processed data
    processed_data = {
        "job_id": job_id,
        "original_text": full_text,
        "translated_text": " ".join([s["translated"] for s in translated_sentences]),
        "vocabulary": vocabulary,
        "word_timings": word_timings,
        "sentences": translated_sentences,
        "new_words": len(vocabulary),
    }

    # Save to Cloud Storage
    output_path = f"processed/{job_id}/translation_data.json"
    blob = bucket.blob(output_path)
    blob.upload_from_string(
        json.dumps(processed_data, ensure_ascii=False), content_type="application/json"
    )

    logger.info(
        "translation_complete",
        output_path=output_path,
        vocabulary_count=len(vocabulary),
    )

    return processed_data


@functions_framework.http
def process_translation(request) -> Dict[str, Any]:
    """
    Cloud Function entry point.

    Expected request body:
    {
        "transcript_path": "transcripts/job-123/transcript.json",
        "target_language": "en",
        "job_id": "job-123"
    }
    """
    request_json = request.get_json()

    if not request_json:
        return {"error": "No request data provided"}, 400

    transcript_path = request_json.get("transcript_path")
    target_language = request_json.get("target_language")
    job_id = request_json.get("job_id")

    if not transcript_path:
        return {"error": "transcript_path is required"}, 400
    if not target_language:
        return {"error": "target_language is required"}, 400
    if not job_id:
        return {"error": "job_id is required"}, 400

    try:
        result = process_transcript(transcript_path, target_language, job_id)

        return {"status": "success", **result}

    except Exception as e:
        logger.exception(
            "process_translation_failed",
            error=str(e),
            transcript_path=transcript_path,
            job_id=job_id,
        )
        return {"error": str(e), "status": "error"}, 500
