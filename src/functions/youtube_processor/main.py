import os
import tempfile
import yt_dlp
from typing import Dict, Any, Union, Tuple
import functions_framework
from google.cloud import storage
import structlog
from flask import Request
import time
import random

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


def download_audio(video_url: str, job_id: str) -> str:
    """
    Download audio from YouTube video with bot detection handling.

    Args:
        video_url: YouTube video URL
        job_id: Unique job identifier

    Returns:
        Path to the downloaded audio file
    """
    logger.info("downloading_audio", video_url=video_url, job_id=job_id)

    # Create temp directory for download
    with tempfile.TemporaryDirectory() as temp_dir:
        output_template = os.path.join(temp_dir, f"{job_id}.%(ext)s")

        # User agents to rotate through
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

        # Configure yt-dlp options with bot detection handling
        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "192",
                }
            ],
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            # Bot detection handling
            "user_agent": random.choice(user_agents),
            "extractor_retries": 3,
            "retries": 3,
            "fragment_retries": 3,
            "ignoreerrors": False,
            # Additional headers to appear more human-like
            "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-us,en;q=0.5",
                "Accept-Encoding": "gzip,deflate",
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                "DNT": "1",
            },
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info("download_attempt", attempt=attempt +
                            1, max_retries=max_retries)

                # Download audio
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])

                # Get the output filename
                output_file = f"{job_id}.wav"
                output_path = os.path.join(temp_dir, output_file)

                if not os.path.exists(output_path):
                    raise FileNotFoundError(
                        f"Audio file not found at {output_path}")

                # Upload to Cloud Storage
                bucket = get_media_bucket()
                blob_name = f"audio/{job_id}/audio.wav"
                blob = bucket.blob(blob_name)

                blob.upload_from_filename(output_path)
                logger.info(
                    "audio_uploaded",
                    blob_name=blob_name,
                    size_bytes=os.path.getsize(output_path),
                )

                return blob_name

            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e)
                logger.warning(
                    "download_attempt_failed",
                    attempt=attempt + 1,
                    error=error_msg,
                    video_url=video_url,
                    job_id=job_id,
                )

                # If it's a bot detection error and we have more retries
                if "Sign in to confirm you're not a bot" in error_msg and attempt < max_retries - 1:
                    # Rotate user agent for next attempt
                    ydl_opts["user_agent"] = random.choice(user_agents)
                    # Add delay before retry
                    time.sleep(random.uniform(2, 5))
                    continue
                else:
                    # Final attempt failed or other error
                    raise

            except Exception as e:
                logger.error(
                    "audio_download_failed",
                    error=str(e),
                    video_url=video_url,
                    job_id=job_id,
                )
                raise

        # If we get here, all retries failed
        raise Exception(
            f"Failed to download audio after {max_retries} attempts")


@functions_framework.http
def process_video(request: Request) -> Union[Dict[str, Any], Tuple[Dict[str, str], int]]:
    """
    Cloud Function entry point.

    Expected request body:
    {
        "video_url": "https://youtube.com/watch?v=...",
        "job_id": "unique-job-id"
    }
    """
    request_json = request.get_json()

    if not request_json:
        return {"error": "No request data provided"}, 400

    video_url = request_json.get("video_url")
    job_id = request_json.get("job_id")

    if not video_url:
        return {"error": "video_url is required"}, 400
    if not job_id:
        return {"error": "job_id is required"}, 400

    try:
        audio_path = download_audio(video_url, job_id)

        return {"status": "success", "audio_path": audio_path, "job_id": job_id}

    except Exception as e:
        logger.exception(
            "process_video_failed", error=str(e), video_url=video_url, job_id=job_id
        )
        return {"error": str(e), "status": "error"}, 500
