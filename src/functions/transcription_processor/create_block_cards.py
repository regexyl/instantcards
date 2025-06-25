import os
import time
import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def create_deck(
    deck_name: str,
    parent_deck_id: Optional[str] = None,
    base_url: str = "https://app.mochi.cards/api"
) -> Dict[str, Any]:
    """
    Create a deck using the Mochi API.

    Args:
        deck_name: Name for the new deck
        parent_deck_id: Parent deck ID (defaults to MOCHI_BLOCK_DECK_ID env var)
        base_url: Base URL for the Mochi API

    Returns:
        Created deck response from the API

    Raises:
        requests.RequestException: If API request fails
        ValueError: If required parameters are missing
    """
    mochi_api_key = os.getenv("MOCHI_API_KEY")
    if not mochi_api_key:
        raise ValueError("MOCHI_API_KEY is required")

    if not deck_name:
        raise ValueError("deck_name is required")

    if not parent_deck_id:
        parent_deck_id = os.getenv("MOCHI_BLOCK_DECK_ID")
        if not parent_deck_id:
            raise ValueError("MOCHI_BLOCK_DECK_ID environment variable is required")

    payload = {
        "name": deck_name,
        "parent-id": parent_deck_id,
        "show-sides": True
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        response = requests.post(
            f"{base_url}/decks/",
            headers=headers,
            auth=(mochi_api_key, ""),
            json=payload
        )

        response.raise_for_status()
        created_deck = response.json()

        logger.info(
            f"Successfully created deck '{deck_name}' with ID: {created_deck.get('id')}")
        return created_deck

    except requests.RequestException as e:
        logger.error(f"Failed to create deck '{deck_name}': {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating deck '{deck_name}': {e}")
        raise