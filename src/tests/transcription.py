#!/usr/bin/env python3
"""
Simple test for Transcription and Translation processor function
"""

from functions.transcription_processor.main import process_transcription_and_translation
import sys
import os
import json
from flask import Flask, request

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))


app = Flask(__name__)


def test_transcription_and_translation_processor():
    """Test the Transcription and Translation processor function."""
    print("🧪 Testing Transcription and Translation Processor...")

    with app.test_request_context(
        '/',
        method='POST',
        data=json.dumps({
            "audio_path": "audio/test-123/audio.wav",
            "job_id": "test-123",
        }),
        content_type='application/json'
    ):
        try:
            result = process_transcription_and_translation(request)
            if result[1] == 200:
                print(f"✅ Success: {result[0]}")
            else:
                print(f"❌ Failed: {result[0]}")
            return True
        except Exception as e:
            print(f"❌ Failed: {e}")
            return False


if __name__ == "__main__":
    test_transcription_and_translation_processor()
