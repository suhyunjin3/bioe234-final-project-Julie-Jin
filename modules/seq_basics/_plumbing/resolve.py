"""Resolve heterogeneous sequence inputs to clean DNA/RNA strings.

This module handles the conversion of various input formats (resource names,
GenBank content, FASTA content, raw sequences) into clean sequence strings
that the business logic functions expect.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional

from Bio import SeqIO

# Valid characters after cleaning: DNA/RNA + IUPAC ambiguity codes
VALID_SEQUENCE_CHARS = set("ATUCGRSYKWMN")

# Resource registry: maps resource names to file paths
_RESOURCE_PATHS: dict[str, Path] = {}


def register_resource(name: str, path: Path) -> None:
    """Register a resource name -> file path mapping."""
    _RESOURCE_PATHS[name] = path


def get_resource_path(name: str) -> Optional[Path]:
    """Get the file path for a registered resource name."""
    return _RESOURCE_PATHS.get(name)


def list_resources() -> dict[str, Path]:
    """Return a copy of the resource registry."""
    return dict(_RESOURCE_PATHS)


def resolve_to_seq(input_value: str) -> str:
    """Convert any sequence representation to a clean DNA/RNA string.

    Accepts:
        - Resource name: "pBR322" -> looks up and parses file
        - GenBank content: "LOCUS pBR322..." -> parses with BioPython
        - FASTA content: ">seq1\\nATGC..." -> parses with BioPython
        - Raw sequence: "ATGCGATCGATCG" -> cleans and validates
        - Dirty sequence: "ATG CGA\\nTCG" -> strips whitespace, validates

    Returns:
        Uppercase string containing only valid sequence characters.

    Raises:
        ValueError: If the input cannot be resolved or contains invalid characters.
    """
    input_value = input_value.strip()

    if not input_value:
        raise ValueError("Empty sequence input.")

    # 1. Check if it's a registered resource name
    if input_value in _RESOURCE_PATHS:
        return _parse_file(_RESOURCE_PATHS[input_value])

    # 2. Check if it looks like GenBank format
    if input_value.startswith("LOCUS"):
        return _parse_genbank_string(input_value)

    # 3. Check if it looks like FASTA format
    if input_value.startswith(">"):
        return _parse_fasta_string(input_value)

    # 4. Assume it's a raw sequence string - clean it
    return _clean_sequence(input_value)


def _parse_file(path: Path) -> str:
    """Parse a sequence file (GenBank, FASTA, etc.) to string."""
    suffix = path.suffix.lower()

    if suffix in (".gb", ".gbk", ".genbank"):
        fmt = "genbank"
    elif suffix in (".fa", ".fasta", ".fna"):
        fmt = "fasta"
    else:
        # Try genbank first, then fasta
        try:
            record = SeqIO.read(path, "genbank")
            return str(record.seq).upper()
        except Exception:
            pass
        try:
            record = SeqIO.read(path, "fasta")
            return str(record.seq).upper()
        except Exception:
            raise ValueError(f"Could not parse file: {path}")

    record = SeqIO.read(path, fmt)
    return str(record.seq).upper()


def _parse_genbank_string(content: str) -> str:
    """Parse GenBank format from string."""
    try:
        record = SeqIO.read(io.StringIO(content), "genbank")
        return str(record.seq).upper()
    except Exception as e:
        raise ValueError(f"Could not parse GenBank content: {e}") from e


def _parse_fasta_string(content: str) -> str:
    """Parse FASTA format from string."""
    try:
        record = SeqIO.read(io.StringIO(content), "fasta")
        return str(record.seq).upper()
    except Exception as e:
        raise ValueError(f"Could not parse FASTA content: {e}") from e


def _clean_sequence(seq: str) -> str:
    """Clean a raw sequence string.

    Removes whitespace and numbers, converts to uppercase, validates characters.
    """
    # Remove whitespace and numbers (from numbered sequence formats)
    cleaned = re.sub(r"[\s\d]+", "", seq).upper()

    if not cleaned:
        raise ValueError("Sequence is empty after cleaning.")

    # Validate characters
    invalid = set(cleaned) - VALID_SEQUENCE_CHARS
    if invalid:
        raise ValueError(
                        f"Invalid sequence characters detected: {sorted(invalid)}. "
                        "Valid DNA/RNA/IUPAC characters are: ATUCGRSYKWMN."
)

    return cleaned
