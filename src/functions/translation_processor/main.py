import os
import json
from typing import Dict, Any, List
import functions_framework
from google.cloud import storage
from google.cloud import translate_v2
import google.cloud.aiplatform as aiplatform
from vertexai.language_models import TextGenerationModel
import structlog
import MeCab

logger = structlog.get_logger()
storage_client = storage.Client()
translate_client = translate_v2.Client()

# Initialize MeCab tokenizer
_tokenizer = MeCab.Tagger("-Ochasen")


def get_media_bucket() -> storage.Bucket:
    """Get the media storage bucket."""
    bucket_name = os.environ.get("MEDIA_BUCKET")
    if not bucket_name:
        raise ValueError("MEDIA_BUCKET environment variable not set")
    return storage_client.bucket(bucket_name)


def extract_vocabulary(text: str) -> List[Dict[str, Any]]:
    """
    Extract vocabulary words from text using Japanese tokenizer.

    Args:
        text: Text to analyze

    Returns:
        List of vocabulary words with metadata
    """
    logger.info("extracting_vocabulary", text_length=len(text))

    # Tokenize the text
    parsed = _tokenizer.parse(text)

    # Filter and process tokens
    vocabulary_items = []
    seen_words = set()

    for line in parsed.split('\n'):
        if line == 'EOS' or not line.strip():
            continue

        # Parse MeCab output: 表層形\t品詞,品詞細分類1,品詞細分類2,品詞細分類3,活用型,活用形,原形,読み,発音
        parts = line.split('\t')
        if len(parts) < 2:
            continue

        surface = parts[0]  # 表層形 (surface form)
        features = parts[1].split(',')  # 品詞情報 (part of speech info)

        if len(features) < 8:
            continue

        # Skip punctuation, numbers, and very short tokens
        if (len(surface) < 2 or
            features[0] in ['記号', '助詞', '助動詞'] or
            features[0] == '接尾辞' or
                surface in seen_words):
            continue

        word = surface
        seen_words.add(word)

        # Get reading (pronunciation) - 読み field
        reading = features[7] if len(
            features) > 7 and features[7] != '*' else word

        # Determine part of speech
        pos = _map_part_of_speech(features[0])

        vocab_item = {
            "word": word,
            "reading": reading,
            "part_of_speech": pos,
        }

        vocabulary_items.append(vocab_item)

    logger.info("vocabulary_extracted", count=len(vocabulary_items))
    return vocabulary_items


def _map_part_of_speech(mecab_pos: str) -> str:
    """Map MeCab part-of-speech to English equivalents."""
    pos_mapping = {
        '名詞': 'noun',
        '動詞': 'verb',
        '形容詞': 'adjective',
        '副詞': 'adverb',
        '接続詞': 'conjunction',
        '代名詞': 'pronoun',
        '連体詞': 'determiner',
        '感動詞': 'interjection'
    }
    return pos_mapping.get(mecab_pos, 'other')


def translate_text(text: str) -> str:
    """
    Translate text to target language.

    Args:
        text: Text to translate
        target_language: Target language code

    Returns:
        Translated text
    """
    logger.info(
        "translating_text", text_length=len(text)
    )

    result = translate_client.translate(text, target_language="en")
    return result["translatedText"]


def process_transcript(
    transcript_path: str, job_id: str
) -> Dict[str, Any]:
    """
    Process transcript and extract vocabulary.

    Args:
        transcript_path: Path to transcript file
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
        translated = translate_text(sentence)
        translated_sentences.append(
            {"original": sentence, "translated": translated, "timestamp": timestamp}
        )

    # Extract vocabulary from the full text
    full_text = " ".join([word for word, _ in word_timings])
    vocabulary = extract_vocabulary(full_text)

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
def process_translation(request) -> tuple[Dict[str, str], int]:
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
    job_id = request_json.get("job_id")

    if not transcript_path:
        return {"error": "transcript_path is required"}, 400
    if not job_id:
        return {"error": "job_id is required"}, 400

    try:
        result = process_transcript(transcript_path, job_id)

        return {"status": "success", **result}, 200

    except Exception as e:
        logger.exception(
            "process_translation_failed",
            error=str(e),
            transcript_path=transcript_path,
            job_id=job_id,
        )
        return {"error": str(e), "status": "error"}, 500
