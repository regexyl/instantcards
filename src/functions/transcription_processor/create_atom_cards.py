from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import time
import requests
import logging
from typing import Dict, Any, Optional

from db.main import get_session
from db.sqlacodegen import Atom
from functions.transcription_processor.classes import Translation

logger = logging.getLogger(__name__)


def create_single_card_with_retry(
    name_value: str,
    template_id: Optional[str] = None,
    deck_id: Optional[str] = None,
    base_url: str = "https://app.mochi.cards/api",
    max_retries: int = 3,
    retry_delay: float = 1.0
) -> Dict[str, Any]:
    """
    Create a single card with retry logic.

    Args:
        name_value: Value for the 'name' field of the card
        template_id: Template ID to use for the card
        deck_id: Deck ID where card will be created
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
            return create_single_card(name_value, template_id, deck_id, base_url)
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"Attempt {attempt + 1} failed for value '{name_value}': {e}. "
                    f"Retrying in {retry_delay} seconds..."
                )
                time.sleep(retry_delay)
                # Exponential backoff: increase delay for subsequent retries
                retry_delay *= 2
            else:
                logger.error(
                    f"All {max_retries + 1} attempts failed for value '{name_value}': {e}"
                )
                raise

    # This should never be reached, but just in case
    raise RuntimeError(
        f"Failed to create card for value '{name_value}' after {max_retries + 1} attempts")


def create_single_card(
    name_value: str,
    template_id: Optional[str] = None,
    deck_id: Optional[str] = None,
    base_url: str = "https://app.mochi.cards/api"
) -> Dict[str, Any]:
    """
    Create a single card using the Mochi API.

    Args:
        api_key: Mochi API key for authentication
        name_value: Value for the 'name' field of the card
        template_id: Template ID to use for the card (default: NC3jpmKk)
        deck_id: Deck ID where card will be created (default: uI43C0Lx)
        base_url: Base URL for the Mochi API (default: https://app.mochi.cards/api)

    Returns:
        Created card response from the API

    Raises:
        requests.RequestException: If API request fails
        ValueError: If required parameters are missing
    """
    mochi_api_key = os.getenv("MOCHI_API_KEY")
    if not mochi_api_key:
        raise ValueError("MOCHI_API_KEY is required")

    if not name_value:
        raise ValueError("name_value is required")

    if not template_id:
        template_id = os.getenv("MOCHI_ATOM_TEMPLATE_ID")

    if not deck_id:
        deck_id = os.getenv("MOCHI_DECK_ID")

    payload = {
        "deck-id": deck_id,
        "template-id": template_id,
        # Ensures atom cards come before their respective block cards
        "pos": int(time.time()),
        "review-reversed": True,
        "fields": {
            "name": {
                "id": "name",
                "value": name_value
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
            f"Successfully created atom card with ID: {created_card.get('id')}")
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


def create_atom_cards(translation: Translation) -> Dict[str, Any]:
    """
    Create cards for each atom in the translation using efficient batching and parallel processing.

    Returns:
        Dictionary with creation statistics including new and existing card counts
    """
    unique_values = set()
    for atom in translation.atoms:
        unique_values.add(atom.value)

    with get_session() as session:
        existing_atoms = session.query(Atom).filter(
            Atom.value.in_(unique_values)
        ).all()

        existing_card_ids = {}
        for atom in existing_atoms:
            if atom.card and atom.card.destination_id:
                existing_card_ids[atom.value] = atom.card.destination_id

    values_to_create = [
        value for value in unique_values if value not in existing_card_ids]

    new_card_ids = {}
    creation_errors = []

    if values_to_create:
        logger.info(f"Creating {len(values_to_create)} new cards in parallel")

        with ThreadPoolExecutor(max_workers=6) as executor:
            future_to_value = {
                executor.submit(create_single_card_with_retry, value): value
                for value in values_to_create
            }

            for future in as_completed(future_to_value):
                value = future_to_value[future]
                try:
                    card = future.result()
                    new_card_ids[value] = card['id']
                    logger.info(
                        f"Created atom card (ID: {card['id']}) for value: {value}")
                except Exception as e:
                    logger.error(
                        f"Failed to create card for value '{value}': {e}")
                    creation_errors.append({"value": value, "error": str(e)})
                    continue

    all_card_ids = {**existing_card_ids, **new_card_ids}

    for atom in translation.atoms:
        atom.set_card_id(all_card_ids[atom.value])

    return {
        "atom_cards_created_count": len(new_card_ids),
        "atom_cards_existing_count": len(existing_card_ids),
        "atom_cards_total_count": len(all_card_ids),
        "atom_cards_creation_errors": creation_errors,
    }
