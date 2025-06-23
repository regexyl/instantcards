#!/usr/bin/env python3
"""
Simple test for YouTube processor function
"""

import sys
import os
import json
from flask import Flask, request

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

from functions.youtube_processor.main import process_video

app = Flask(__name__)


def test_youtube_processor():
    """Test the YouTube processor function."""
    print("🧪 Testing YouTube Processor...")

    with app.test_request_context(
        '/',
        method='POST',
        data=json.dumps({
            "video_url": "https://www.youtube.com/shorts/ZiIBb3g03kE",
            "job_id": "test-123",
        }),
        content_type='application/json'
    ):
        try:
            result = process_video(request)
            print(f"✅ Success: {result}")
            return True
        except Exception as e:
            print(f"❌ Failed: {e}")
            return False


if __name__ == "__main__":
    test_youtube_processor()
