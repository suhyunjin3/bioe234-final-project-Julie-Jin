"""Example tool -- DNA to Protein Translation.
"""

from typing import Optional

from .._utils import CODON_TABLE


class Translate:
    """
    Description:
        Translates a DNA sequence to a protein sequence using the standard
        genetic code.  Supports optional coordinate slicing and reading
        frame selection.
 
    Input:
        seq   (str):           DNA sequence (resource name or raw string).
        start (int, optional): 0-indexed start position within the sequence.
                               Default: beginning of sequence.
        end   (int, optional): End position (exclusive).
                               Default: end of sequence.
        frame (int):           Reading frame — 1, 2, or 3.  Default: 1.
 
    Output:
        str: Protein sequence as single-letter amino acid codes.
             Stop codons are represented as '*'.
             Unrecognised codons are represented as 'X'.
 
    Tests:
        - Case:
            Input: seq="ATGGCT"
            Expected Output: "MA"
            Description: Basic two-codon sequence.
        - Case:
            Input: seq="AATGGCT", frame=2
            Expected Output: "MA"
            Description: Frame 2 skips the first base.
        - Case:
            Input: seq="AATGGCTAAA", start=1, end=None, frame=1
            Expected Output: "MAK"
            Description: Coordinate slicing combined with frame 1.
        - Case:
            Input: seq="ATGGCT", frame=0
            Expected Exception: ValueError
            Description: Frame 0 is invalid; only 1, 2, 3 are accepted.
        - Case:
            Input: seq="ATGGCT", frame=4
            Expected Exception: ValueError
            Description: Frame 4 is out of range.
    """
    codon_table: dict[str, str]

    def initiate(self) -> None:
        """One-time setup: load the codon table from shared utils."""
        # ::: CODON_TABLE is imported from _utils.py (shared module-level
        # constant).  We assign it here into an instance variable so the class
        # follows the initiate/run pattern properly — state is set in initiate
        # and treated as immutable during run().
        self.codon_table = CODON_TABLE
 
    def run(
        self,
        seq: str,
        start: Optional[int] = None,
        end:   Optional[int] = None,
        frame: int = 1,
    ) -> str:
        """Translate seq (or a slice of it) in the given reading frame."""
 
        # --- Input validation ---
        if start is not None and start < 0:
            raise ValueError("start must be >= 0")
        if end is not None and end < 0:
            raise ValueError("end must be >= 0")
        if frame not in (1, 2, 3):
            raise ValueError(f"Frame must be 1, 2, or 3 — got {frame}")
 
        # --- Apply coordinate slice ---
        if start is not None or end is not None:
            seq = seq[start:end]
 
        # --- Apply frame offset (frame 1 = no offset, 2 = skip 1, 3 = skip 2) ---
        if frame in (2, 3):
            seq = seq[frame - 1:]
 
        # --- Translate codon by codon ---
        protein = []
        for i in range(0, len(seq) - 2, 3):
            codon = seq[i:i + 3]
            protein.append(self.codon_table.get(codon, "X"))
 
        return "".join(protein)
 
 
# ---------------------------------------------------------------------------
#Module-level alias — keeps existing tests and direct imports working.
#
#   from modules.seq_basics.tools.translate import translate
#
# The alias creates ONE shared instance and exposes run() as a plain callable.
# ---------------------------------------------------------------------------
_instance = Translate()
_instance.initiate()
translate = _instance.run   # callable: translate(seq, start, end, frame) -> str
 
 
# Standalone test
if __name__ == "__main__":
    test = "ATGGCTAGCTAG"
    print(f"Frame 1: {translate(test, frame=1)}")
    print(f"Frame 2: {translate(test, frame=2)}")
    print(f"Frame 3: {translate(test, frame=3)}")