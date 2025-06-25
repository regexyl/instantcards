from typing import Dict, Any, List, NamedTuple, Optional
import structlog
import MeCab
from .classes import Block, Translation, Atom

logger = structlog.get_logger()


class MeCabToken(NamedTuple):
    """Structured representation of a MeCab token."""
    surface: str  # 表層形 (surface form)
    pos: str  # 品詞 (part of speech)
    pos_details: Optional[list[str]]  # 品詞細分類
    conjugation_type: Optional[str]  # 活用型
    conjugation_form: Optional[str]  # 活用形
    conjugation_form_number: Optional[str]  # 活用形番号
    base_form: str  # 原形 (base form)
    reading: str  # 読み (reading/pronunciation)
    pronunciation: str  # 発音 (pronunciation)

    def get_metadata(self) -> dict:
        return {
            "pos_details": self.pos_details,
            "conjugation_type": self.conjugation_type,
            "conjugation_form": self.conjugation_form,
            "reading": self.reading,
            "pronunciation": self.pronunciation
        }


def extract_atoms(translation: Translation, job_id: str) -> Dict[str, Any]:
    """
    Extract vocabulary words from transcription using Japanese tokenizer and create Atom objects.
    Processes each block individually to maintain context.

    Args:
        translation: Translation object containing transcription data
        job_id: Unique job identifier

    Returns:
        Dictionary with atom extraction results
    """
    logger.info("extracting_atoms", job_id=job_id,
                block_count=translation.get_block_count())

    try:
        total_atoms = 0
        blocks_with_atoms = 0
        unique_atoms = set()

        # Process each block individually
        for block_index, block in enumerate(translation.blocks):
            block_atoms = _extract_atoms_from_block(block, block_index, job_id)

            if block_atoms:
                translation.add_atoms_to_block(block_index, block_atoms)
                total_atoms += len(block_atoms)
                blocks_with_atoms += 1
                for atom in block_atoms:
                    unique_atoms.add(atom.value)

        result_data = {
            "atoms_extracted": total_atoms,
            "unique_atoms_count": len(unique_atoms),
            "blocks_with_atoms": blocks_with_atoms,
            "total_blocks_processed": len(translation.blocks),
            "average_atoms_per_block": total_atoms / len(translation.blocks) if translation.blocks else 0
        }

        logger.info("atoms_extracted",
                    job_id=job_id,
                    atoms_count=total_atoms,
                    unique_atoms=len(unique_atoms),
                    blocks_with_atoms=blocks_with_atoms)

        return result_data

    except Exception as e:
        logger.exception("atoms_extraction_failed",
                         job_id=job_id, error=str(e))
        raise


def _extract_atoms_from_block(block: Block, block_index: int, job_id: str) -> List[Atom]:
    """
    Extract atoms from a single block of text.

    Args:
        block: Block object containing text to analyze
        block_index: Index of the block for logging
        job_id: Job identifier for logging

    Returns:
        List of Atom objects extracted from this block
    """
    if not block.value.strip():
        return []

    logger.debug("processing_block", job_id=job_id, block_index=block_index,
                 text_length=len(block.value))

    tokens = _parse_mecab_output(block.value)

    atoms = []
    seen_words = set()

    for token in tokens:
        word = token.surface
        base_form = token.base_form if token.base_form != '*' else word

        if word not in seen_words:
            atom = Atom(value=word, base_form=base_form,
                        part_of_speech=token.pos, metadata=token.get_metadata())
            atoms.append(atom)
            seen_words.add(word)

    logger.debug("block_atoms_extracted", job_id=job_id, block_index=block_index,
                 atoms_count=len(atoms))

    return atoms


def _parse_mecab_output(text: str) -> List[MeCabToken]:
    """
    Parse MeCab output into structured token objects.

    Args:
        text: Japanese text to analyze

    Returns:
        List of MeCabToken objects with parsed information
    """
    tagger = MeCab.Tagger()
    parsed = tagger.parse(text)

    tokens = []

    for line in parsed.split('\n'):
        if line == 'EOS' or not line.strip():
            continue

        # Parse MeCab output format:
        # 表層形\t読み\t発音\t原形\t品詞-品詞細分類1\t活用型\t活用形\t活用形詳細\t活用形番号
        # surface_form\treading\tpronunciation\tbase_form\tpart_of_speech-part_of_speech_detail1\tconjugation_type\tconjugation_form\tconjugation_form_detail\tconjugation_form_number
        parts = line.split('\t')
        # print(f"😸 {parts}")
        if len(parts) < 2:
            continue

        surface, reading, pronunciation, base_form, pos_info, conjugation_type, conjugation_form, conjugation_form_number = parts + \
            [None] * (8 - len(parts))
        pos_info = pos_info.split('-')
        pos = pos_info[0]
        pos_rest_of_details = pos_info[1:]
        pos_en = _map_part_of_speech(pos, surface)

        if pos_en in ['symbol', 'auxiliary_symbol']:
            continue

        token = MeCabToken(
            surface=surface,
            pos=pos_en,
            pos_details=pos_rest_of_details,
            conjugation_type=conjugation_type,
            conjugation_form=conjugation_form,
            conjugation_form_number=conjugation_form_number,
            base_form=base_form,
            reading=reading,
            pronunciation=pronunciation
        )

        tokens.append(token)

    return tokens


def _map_part_of_speech(mecab_pos: str, word: str) -> str:
    """Map MeCab part-of-speech to English equivalents."""
    pos_mapping = {
        '名詞': 'noun',
        '動詞': 'verb',
        '形容詞': 'adjective',
        '形容動詞': 'adjectival_verb',
        '副詞': 'adverb',
        '助詞': 'particle',
        '助動詞': 'auxiliary_verb',
        '接続詞': 'conjunction',
        '代名詞': 'pronoun',
        '連体詞': 'determiner',
        '感動詞': 'interjection',
        '記号': 'symbol',
        '接頭詞': 'prefix',
        "接頭辞": "prefix",
        '接尾辞': 'suffix',
        "補助記号": "auxiliary_symbol",
        'フィラー': 'filler',
        'その他': 'other',
        '未知語': 'unknown',
    }

    mapped_pos = pos_mapping.get(mecab_pos, 'other')

    if mapped_pos == 'other' and mecab_pos not in pos_mapping:
        logger.error("part_of_speech_mapping_failed",
                     word=word,
                     mecab_pos=mecab_pos,
                     mapped_to=mapped_pos)

    return mapped_pos
