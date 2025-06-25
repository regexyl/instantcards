from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import time
import requests
import logging
from typing import Dict, Any, Optional

from functions.transcription_processor.classes import Block, Translation

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
            raise ValueError(
                "MOCHI_BLOCK_DECK_ID environment variable is required")

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


def create_single_block_card(deck_id, block: Block, base_url: str = "https://app.mochi.cards/api", template_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Create block cards using the Mochi API.
    """
    mochi_api_key = os.getenv("MOCHI_API_KEY")
    if not mochi_api_key:
        raise ValueError("MOCHI_API_KEY is required")

    if not template_id:
        template_id = os.getenv("MOCHI_BLOCK_TEMPLATE_ID")
        if not template_id:
            raise ValueError("MOCHI_BLOCK_TEMPLATE_ID is required")

    payload = {
        "deck-id": deck_id,
        "template-id": template_id,
        "review-reversed": True,
        "fields": {
            "name": {
                "id": "name",
                "value": block.value
            },
            "IDK8GAaK": {  # audio path
                "id": "IDK8GAaK",
                "value": block.audio_url
            },
            "IGlbbOnH": {  # translation
                "id": "IDK8GAaK",
                "value": block.translated_value
            },
            "OgOtJHC6": {  # backlinks to atoms
                "id": "OgOtJHC6",
                "value": [f"[[{atom.card_id}]]" for atom in block.atoms]
            }
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        response = requests.post(
            f"{base_url}/cards/",
            headers=headers,
            auth=(mochi_api_key, ""),
            json=payload
        )

        response.raise_for_status()
        created_card = response.json()

        logger.info(
            f"Successfully created block card with ID: {created_card.get('id')}")
        return created_card

    except requests.RequestException as e:
        logger.error(f"Failed to create card: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating card: {e}")
        raise


def create_single_block_card_with_retry(
    deck_id: str,
    block: Block,
    template_id: Optional[str] = None,
    base_url: str = "https://app.mochi.cards/api",
    max_retries: int = 3,
    retry_delay: float = 1.0
) -> Dict[str, Any]:
    """
    Create a single block card with retry logic.

    Args:
        deck_id: Deck ID where card will be created
        block: Block object containing card data
        template_id: Template ID to use for the card
        base_url: Base URL for the Mochi API
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay: Delay between retries in seconds (default: 1.0)

    Returns:
        Created card response from the API

    Raises:
        Exception: If all retry attempts fail
    """
    for attempt in range(max_retries + 1):
        try:
            return create_single_block_card(deck_id, block, base_url, template_id)
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"Attempt {attempt + 1} failed for block '{block.value}': {e}. "
                    f"Retrying in {retry_delay} seconds..."
                )
                time.sleep(retry_delay)
                # Exponential backoff: increase delay for subsequent retries
                retry_delay *= 2
            else:
                logger.error(
                    f"All {max_retries + 1} attempts failed for block '{block.value}': {e}"
                )
                raise

    raise RuntimeError(
        f"Failed to create card for block '{block.value}' after {max_retries + 1} attempts")


def create_block_cards(translation: Translation, name: str, base_url: str = "https://app.mochi.cards/api", template_id: Optional[str] = None):
    """
    Create block cards using the Mochi API.
    """
    deck = create_deck(name)
    deck_id = deck.get('id')

    if not deck_id:
        raise ValueError("Failed to get deck ID from created deck")

    logger.info(f"Creating {len(translation.blocks)} block cards in parallel")

    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_block = {
            executor.submit(create_single_block_card_with_retry, deck_id, block, template_id, base_url): block
            for block in translation.blocks
        }

        for future in as_completed(future_to_block):
            block = future_to_block[future]
            try:
                card = future.result()
                block.card_id = card.get('id')
                logger.info(
                    f"Created block card (ID: {block.card_id}) for: {block.value}")
            except Exception as e:
                logger.error(
                    f"Failed to create block card for '{block.value}': {e}")
                continue

    logger.info(f"Completed creating block cards for deck: {name}")
