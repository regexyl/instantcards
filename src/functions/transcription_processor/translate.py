import os
from typing import Dict, Any
from google.cloud import translate_v2
from openai import OpenAI
import structlog
from .classes import Translation

logger = structlog.get_logger()
translate_client = translate_v2.Client()
openai_client = OpenAI()


def translate(translation: Translation, job_id: str) -> Dict[str, Any]:
    """
    Translate the transcription text to English.

    Args:
        translation: Translation object containing transcription data
        job_id: Unique job identifier

    Returns:
        Dictionary with translation results
    """
    logger.info("translating_text", job_id=job_id,
                xml_text_length=len(translation.get_full_text_with_xml()))

    try:
        xml_text = translation.get_full_text_with_xml()

        response = openai_client.responses.create(
            model="gpt-4.1",
            input=f"""You are a professional translator. Translate the following text to English. Maintain the original meaning and tone. Only return the translated text in the same XML format, nothing else.\n\n
            {xml_text}"""
        )

        try:
            translated_text = Translation.decode_xml(response.output_text)
        except Exception as e:
            logger.error("failed_to_decode_xml", error=str(e))
            raise

        for i in range(translation.get_block_count()):
            translation.set_block_translation(i, translated_text[i])

        result_data = {
            "translated_text": translated_text,
            "blocks_translated": translation.get_block_count(),
        }

        logger.info("translation_complete",
                    job_id=job_id,
                    blocks_translated=translation.get_block_count(),
                    )

        return result_data

    except Exception as e:
        logger.exception("translation_failed", job_id=job_id, error=str(e))
        raise
