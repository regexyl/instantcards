from typing import Dict, Any, List, NamedTuple
import structlog
import MeCab
from classes import Block, Translation, Atom

logger = structlog.get_logger()


class MeCabToken(NamedTuple):
    """Structured representation of a MeCab token."""
    surface: str  # 表層形 (surface form)
    pos: str  # 品詞 (part of speech)
    pos_detail1: str  # 品詞細分類1
    pos_detail2: str  # 品詞細分類2
    pos_detail3: str  # 品詞細分類3
    conjugation_type: str  # 活用型
    conjugation_form: str  # 活用形
    base_form: str  # 原形 (base form)
    reading: str  # 読み (reading/pronunciation)
    pronunciation: str  # 発音 (pronunciation)

    def get_metadata(self) -> dict:
        return {
            "pos_detail1": self.pos_detail1,
            "pos_detail2": self.pos_detail2,
            "pos_detail3": self.pos_detail3,
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

        # Process each block individually
        for block_index, block in enumerate(translation.blocks):
            block_atoms = _extract_atoms_from_block(block, block_index, job_id)

            if block_atoms:
                translation.add_atoms_to_block(block_index, block_atoms)
                total_atoms += len(block_atoms)
                blocks_with_atoms += 1

        result_data = {
            "atoms_extracted": total_atoms,
            "blocks_with_atoms": blocks_with_atoms,
            "total_blocks_processed": len(translation.blocks)
        }

        logger.info("atoms_extracted",
                    job_id=job_id,
                    atoms_count=total_atoms,
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
    tagger = MeCab.Tagger("0chasen")
    parsed = tagger.parse(text)

    tokens = []

    for line in parsed.split('\n'):
        if line == 'EOS' or not line.strip():
            continue

        # Parse MeCab output format:
        # 表層形\t品詞,品詞細分類1,品詞細分類2,品詞細分類3,活用型,活用形,原形,読み,発音
        parts = line.split('\t')
        if len(parts) < 2:
            continue

        surface = parts[0]
        features = parts[1].split(',')
        pos = _map_part_of_speech(features[0])

        token = MeCabToken(
            surface=surface,
            pos=pos,
            pos_detail1=features[1] if len(features) > 1 else '',
            pos_detail2=features[2] if len(features) > 2 else '',
            pos_detail3=features[3] if len(features) > 3 else '',
            conjugation_type=features[4] if len(features) > 4 else '',
            conjugation_form=features[5] if len(features) > 5 else '',
            base_form=features[6] if len(features) > 6 else '',
            reading=features[7] if len(features) > 7 else '',
            pronunciation=features[8] if len(features) > 8 else ''
        )

        tokens.append(token)

    return tokens


def _map_part_of_speech(mecab_pos: str) -> str:
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
        '接尾辞': 'suffix',
        'フィラー': 'filler',
        'その他': 'other',
        '未知語': 'unknown'
    }

    mapped_pos = pos_mapping.get(mecab_pos, 'other')

    if mapped_pos == 'other' and mecab_pos not in pos_mapping:
        logger.error("part_of_speech_mapping_failed",
                     mecab_pos=mecab_pos,
                     mapped_to=mapped_pos)

    return mapped_pos
