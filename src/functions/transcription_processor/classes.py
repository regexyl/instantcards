from typing import List, Optional, Generator
from dataclasses import dataclass, field
from srt import Subtitle
import srt
import re


@dataclass
class Atom:
    """Represents a single vocabulary word or phrase from the transcription."""
    value: str
    base_form: str
    part_of_speech: str
    metadata: Optional[dict] = None
    card_id: Optional[str] = None

    def __post_init__(self):
        """Validate atom data after initialization."""
        if not self.value.strip():
            raise ValueError("Atom value cannot be empty")

    def __eq__(self, other):
        if not isinstance(other, Atom):
            return False
        return self.value == other.value

    def set_card_id(self, card_id: str) -> None:
        """Set the card ID for this atom."""
        self.card_id = card_id


@dataclass
class Block:
    """Represents a time-bounded segment of transcription with its atoms."""
    start_time: float
    end_time: float
    value: str
    card_id: Optional[str] = None
    atoms: List[Atom] = field(default_factory=list)
    translated_value: Optional[str] = None
    audio_url: Optional[str] = None

    def __post_init__(self):
        """Validate block data after initialization."""
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")
        if not self.value.strip():
            raise ValueError("Block value cannot be empty")

    def add_atom(self, atom: Atom) -> None:
        """Add an atom to this block."""
        self.atoms.append(atom)

    def get_atom_count(self) -> int:
        """Get the number of atoms in this block."""
        return len(self.atoms)

    def get_new_atoms(self) -> List[Atom]:
        """Get atoms that are not in the database."""
        return [atom for atom in self.atoms if not atom.card_id]


class Translation:
    """Main class for managing transcription and translation data."""

    def __init__(self, transcription_text: str):
        """
        Initialize Translation with SRT transcription text.

        Args:
            transcription_text: Raw SRT format text from transcription
        """
        self.transcription_text = transcription_text
        self.blocks: List[Block] = []
        self._parse_blocks()

    def _parse_blocks(self) -> None:
        """Parse SRT text into Block objects."""
        try:
            # Parse SRT and create blocks
            subtitle_generator: Generator[Subtitle, str, None] = srt.parse(
                self.transcription_text)

            for subtitle in subtitle_generator:
                start_time = subtitle.start.total_seconds()
                end_time = subtitle.end.total_seconds()

                block = Block(
                    start_time=start_time,
                    end_time=end_time,
                    value=subtitle.content
                )

                self.blocks.append(block)

        except Exception as e:
            raise ValueError(f"Failed to parse SRT text: {e}")

    @classmethod
    def decode_xml(cls, xml_text: str) -> List[str]:
        """Decode XML text into a list of strings."""
        pattern = r'<(\d+)>(.*?)</\1>'
        matches = re.findall(pattern, xml_text, re.DOTALL)
        sorted_matches = sorted(matches, key=lambda x: int(x[0]))

        return [match[1].strip() for match in sorted_matches]

    @classmethod
    def encode_xml(cls, text: str, index: int) -> str:
        """Encode text into XML format."""
        return f"<{index}>{text}</{index}>"

    def get_full_text(self, delimiter: str = " ") -> str:
        """Get the complete transcription text."""
        return delimiter.join(block.value for block in self.blocks)

    def get_full_text_with_xml(self) -> str:
        """Get the complete transcription text with XML tags."""
        return " ".join(self.encode_xml(block.value, i) for i, block in enumerate(self.blocks))

    def get_duration(self) -> float:
        """Get the total duration of the transcription in seconds."""
        if not self.blocks:
            return 0.0
        return self.blocks[-1].end_time - self.blocks[0].start_time

    def get_block_count(self) -> int:
        """Get the number of blocks."""
        return len(self.blocks)

    def get_total_atoms(self) -> int:
        """Get the total number of atoms across all blocks."""
        return sum(block.get_atom_count() for block in self.blocks)

    def get_new_atoms_count(self) -> int:
        """Get the count of atoms not in the database."""
        return sum(len(block.get_new_atoms()) for block in self.blocks)

    @property
    def atoms(self) -> Generator[Atom, None, None]:
        """Get all atoms across all blocks."""
        for block in self.blocks:
            for atom in block.atoms:
                yield atom

    def add_atoms_to_block(self, block_index: int, atoms: List[Atom]) -> None:
        """Add atoms to a specific block."""
        if block_index >= len(self.blocks) or block_index < 0:
            raise IndexError(f"Block index {block_index} out of range")

        for atom in atoms:
            self.blocks[block_index].add_atom(atom)

    def set_block_translation(self, block_index: int, translated_text: str) -> None:
        """Set the translated text for a specific block."""
        if block_index >= len(self.blocks):
            raise IndexError(f"Block index {block_index} out of range")

        self.blocks[block_index].translated_value = translated_text

    def get_translated_text(self) -> str:
        """Get the complete translated text."""
        return " ".join(
            block.translated_value or block.value
            for block in self.blocks
        )

    def get_blocks_with_audio(self) -> List[Block]:
        """Get blocks that have audio URLs set."""
        return [block for block in self.blocks if block.audio_url is not None]

    def get_audio_segments_count(self) -> int:
        """Get the number of blocks that have audio URLs."""
        return len(self.get_blocks_with_audio())

    def to_dict(self) -> dict:
        """Convert the translation to a dictionary for serialization."""
        return {
            "blocks": [
                {
                    "start_time": block.start_time,
                    "end_time": block.end_time,
                    "value": block.value,
                    "translated_value": block.translated_value,
                    "audio_url": block.audio_url,
                    "atoms": [
                        {
                            "value": atom.value,
                            "card_id": atom.card_id
                        }
                        for atom in block.atoms
                    ]
                }
                for block in self.blocks
            ],
            "total_blocks": self.get_block_count(),
            "total_atoms": self.get_total_atoms(),
            "new_atoms": self.get_new_atoms_count(),
            "duration": self.get_duration()
        }
