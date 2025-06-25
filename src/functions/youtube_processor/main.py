import os
import tempfile
import yt_dlp
from typing import Dict, Tuple
import functions_framework
from google.cloud import storage
import structlog
from flask import Request
import random

from db.main import get_session
from db.sqlacodegen import Job

logger = structlog.get_logger()
storage_client = storage.Client()


def get_media_bucket() -> storage.Bucket:
    """Get the media storage bucket."""
    bucket_name = os.environ.get("MEDIA_BUCKET")
    if not bucket_name:
        raise ValueError("MEDIA_BUCKET environment variable not set")
    return storage_client.bucket(bucket_name)


def download_audio(video_url: str, job_id: str) -> Tuple[str, str]:
    """
    Download audio from YouTube video with bot detection handling.

    Args:
        video_url: YouTube video URL
        job_id: Unique job identifier

    Returns:
        Path to the downloaded audio file
    """
    logger.info("downloading_audio", video_url=video_url, job_id=job_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        output_template = os.path.join(temp_dir, f"{job_id}.%(ext)s")

        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

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
            "user_agent": random.choice(user_agents),
            "extractor_retries": 3,
            "retries": 3,
            "fragment_retries": 3,
            "ignoreerrors": False,
            "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-us,en;q=0.5",
                "Accept-Encoding": "gzip,deflate",
                "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                "DNT": "1",
            },
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

                info = ydl.extract_info(video_url)
                if not info:
                    logger.error("video_info_not_found", video_url=video_url)
                    raise Exception("Video info not found")

                video_title = info.get('title', 'Unknown Title')
                logger.info("video_title", video_title=video_title)

            output_file = f"{job_id}.wav"
            output_path = os.path.join(temp_dir, output_file)

            if not os.path.exists(output_path):
                raise FileNotFoundError(
                    f"Audio file not found at {output_path}")

            bucket = get_media_bucket()
            blob_name = f"audio/{job_id}/audio.wav"
            blob = bucket.blob(blob_name)

            blob.upload_from_filename(output_path)
            logger.info(
                "audio_uploaded",
                blob_name=blob_name,
                size_bytes=os.path.getsize(output_path),
            )

            session = get_session()
            with session.begin():
                job = session.query(Job).filter(
                    Job.workflow_id == job_id).first()
                if not job:
                    raise Exception("Job not found")
                job.name = video_title
                job.audio_url = blob_name

            return blob_name, video_title

        except Exception as e:
            logger.error(
                "audio_download_failed",
                error=str(e),
                video_url=video_url,
                job_id=job_id,
            )
            raise


@functions_framework.http
def process_video(request: Request) -> Tuple[Dict[str, str], int]:
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
        audio_path, name = download_audio(video_url, job_id)
        return {"status": "success", "audio_path": audio_path, "name": name, "job_id": job_id}, 200

    except Exception as e:
        logger.exception(
            "process_video_failed", error=str(e), video_url=video_url, job_id=job_id
        )
        return {"error": str(e), "status": "error"}, 500
