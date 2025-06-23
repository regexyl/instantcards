import os
import json
import tempfile
import subprocess
from typing import Dict, Any
from google.cloud import storage
import structlog
from classes import Translation

logger = structlog.get_logger()
storage_client = storage.Client()


def get_media_bucket() -> storage.Bucket:
    """Get the media storage bucket."""
    bucket_name = os.environ.get("MEDIA_BUCKET")
    if not bucket_name:
        raise ValueError("MEDIA_BUCKET environment variable not set")
    return storage_client.bucket(bucket_name)


def trim_audio_segment(input_path: str, output_path: str, start_time: float, end_time: float) -> bool:
    """
    Trim audio file to specific time segment using ffmpeg.

    Args:
        input_path: Path to input audio file
        output_path: Path to output audio file
        start_time: Start time in seconds
        end_time: End time in seconds

    Returns:
        True if successful, False otherwise
    """
    try:
        duration = end_time - start_time

        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-ss', str(start_time),
            '-t', str(duration),
            '-c', 'copy',  # Copy without re-encoding for speed
            '-y',  # Overwrite output file
            output_path
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            logger.error("ffmpeg_failed",
                         error=result.stderr,
                         start_time=start_time,
                         end_time=end_time)
            return False

        return True

    except subprocess.TimeoutExpired:
        logger.error("ffmpeg_timeout", start_time=start_time,
                     end_time=end_time)
        return False
    except Exception as e:
        logger.error("ffmpeg_error", error=str(
            e), start_time=start_time, end_time=end_time)
        return False


def store_audio(translation: Translation, job_id: str, original_audio_path: str) -> Dict[str, Any]:
    """
    Extract audio segments for each block and store them in Cloud Storage.

    Args:
        translation: Translation object containing transcription data
        job_id: Unique job identifier
        original_audio_path: Path to original audio file in Cloud Storage

    Returns:
        Dictionary with storage results
    """
    logger.info("extracting_audio_segments", job_id=job_id,
                blocks_count=translation.get_block_count())

    bucket = get_media_bucket()

    try:
        blob = bucket.blob(original_audio_path)

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio_file:
            blob.download_to_file(temp_audio_file)
            temp_audio_path = temp_audio_file.name

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                successful_segments = 0

                for i, block in enumerate(translation.blocks):
                    try:
                        segment_filename = f"block_{i:03d}_{block.start_time:.2f}_{block.end_time:.2f}.wav"
                        temp_segment_path = os.path.join(
                            temp_dir, segment_filename)

                        if trim_audio_segment(temp_audio_path, temp_segment_path, block.start_time, block.end_time):
                            cloud_segment_path = f"audio_segments/{job_id}/{segment_filename}"
                            segment_blob = bucket.blob(cloud_segment_path)

                            with open(temp_segment_path, 'rb') as segment_file:
                                segment_blob.upload_from_file(
                                    segment_file, content_type='audio/wav')

                            block.audio_url = f"gs://{bucket.name}/{cloud_segment_path}"
                            successful_segments += 1

                            logger.debug("audio_segment_created",
                                         block_index=i,
                                         segment_path=cloud_segment_path,
                                         duration=block.end_time - block.start_time)
                        else:
                            logger.error("failed_to_trim_audio_segment",
                                           block_index=i,
                                           start_time=block.start_time,
                                           end_time=block.end_time)

                    except Exception as e:
                        logger.error("failed_to_process_audio_segment",
                                     block_index=i,
                                     error=str(e))

                translation_path = f"transcripts/{job_id}/translation_data.json"
                blob = bucket.blob(translation_path)
                blob.upload_from_string(
                    json.dumps(translation.to_dict(), ensure_ascii=False),
                    content_type="application/json"
                )

                result = {
                    "translation_path": translation_path,
                    "blocks_count": translation.get_block_count(),
                    "successful_segments": successful_segments,
                    "duration": translation.get_duration(),
                    "audio_segments_folder": f"audio_segments/{job_id}/"
                }

                logger.info("audio_segments_extracted",
                            job_id=job_id,
                            successful_segments=successful_segments,
                            total_blocks=translation.get_block_count())

                return result

        finally:
            os.unlink(temp_audio_path)

    except Exception as e:
        logger.exception("failed_to_extract_audio_segments",
                         job_id=job_id, error=str(e))
        raise
