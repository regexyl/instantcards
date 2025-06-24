#!/usr/bin/env python3
"""
Simple test for Transcription and Translation processor function
"""

from utils import mock_srt
import sys
import os
import json
from flask import Flask, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils import mock_srt
from functions.transcription_processor.main import process_transcription_and_translation
from functions.transcription_processor.extract_atoms import extract_atoms
from functions.transcription_processor.classes import Translation

app = Flask(__name__)


def test_extract_atoms():
    """Test the extract_atoms function with mock SRT data."""
    print("🧪 Testing extract_atoms function...")

    try:
        translation = Translation(mock_srt)

        result = extract_atoms(translation, "test-job-123")

        print(f"✅ extract_atoms completed successfully!")
        print(f"   - Atoms extracted: {result['atoms_extracted']}")
        print(f"   - Blocks with atoms: {result['blocks_with_atoms']}")
        print(
            f"   - Total blocks processed: {result['total_blocks_processed']}")

        # Show some sample atoms
        print(f"\n📝 Sample atoms extracted:")
        atom_count = 0
        for block in translation.blocks:
            for atom in block.atoms:
                if atom_count < 5:  # Show first 5 atoms
                    print(
                        f"   {atom.value} (base: {atom.base_form}) - {atom.part_of_speech}")
                    atom_count += 1
                else:
                    break
            if atom_count >= 5:
                break

        return True

    except Exception as e:
        print(f"❌ extract_atoms failed: {e}")
        import traceback
        traceback.print_exc()
        return False


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
    test_extract_atoms()
    print("\n" + "="*50 + "\n")
    # test_transcription_and_translation_processor()
