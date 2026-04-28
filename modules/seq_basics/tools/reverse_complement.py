"""Example tool - Reverse Complement.

For students copying this as a template:
  1. Rename this file to describe your tool  (e.g. gc_content.py)
  2. Rename the class to match             (e.g. GcContent)
  3. Edit initiate() for any one-time setup (or leave it as `pass`)
  4. Put your biology logic in run()
  5. Fill in the companion JSON file       (e.g. gc_content.json)"""


class ReverseComplement:
    """
    Description:
        Computes the reverse complement of a DNA (or RNA) sequence.
        Supports standard bases and IUPAC ambiguity codes.
 
    Input:
        seq (str): DNA/RNA sequence.  Passed in already cleaned and
                   uppercased by the framework (resource name or raw string
                   are both accepted at the MCP layer).
 
    Output:
        str: Reverse complement of the input sequence, uppercase.
 
    Tests:
        - Case:
            Input: seq="ATGC"
            Expected Output: "GCAT"
            Description: Basic four-base sequence.
        - Case:
            Input: seq="ATRYSWKMN"
            Expected Output: (no error, valid IUPAC string returned)
            Description: Ambiguity codes must not raise an error.
        - Case:
            Input: seq="A"
            Expected Output: "T"
            Description: Single-base edge case.
        - Case:
            Input: seq="ATGB"
            Expected Exception: ValueError
            Description: 'B' is not a supported base.
    """
 
    #Class-level type annotation as required by the Python Function Spec
    _complement: dict[str, str]
 
    def initiate(self) -> None:
        """One-time setup: build the complement lookup table."""
        # [CHANGE] Setup moved from module-level constant into initiate(),
        # following the Function Object Pattern where class variables are
        # populated here and treated as immutable afterwards.
        self._complement = {
            "A": "T", "T": "A", "C": "G", "G": "C",
            "U": "A",           # RNA uracil → adenine
            "R": "Y", "Y": "R", # Purine / Pyrimidine
            "S": "S", "W": "W", # Strong / Weak (self-complementary)
            "K": "M", "M": "K", # Keto / Amino
            "N": "N",           # Any base
        }
 
    def run(self, seq: str) -> str:
        """Return the reverse complement of seq."""
        # seq is already cleaned + uppercased by resolve_to_seq in the framework,
        # but we uppercase defensively in case the function is called directly.
        seq = seq.upper()
        try:
            return "".join(self._complement[b] for b in reversed(seq))
        except KeyError as e:
            raise ValueError(f"Invalid base for complement: {e.args[0]}") from None
 
 
# ---------------------------------------------------------------------------
#Module-level alias so existing tests and direct imports still work.
#
#   from modules.seq_basics.tools.reverse_complement import reverse_complement
#
# The alias creates ONE shared instance (initiate is called once at import time)
# and exposes its run() method as a plain callable.  This is purely for
# convenience — the class is the canonical interface.
# ---------------------------------------------------------------------------
_instance = ReverseComplement()
_instance.initiate()
reverse_complement = _instance.run   # callable: reverse_complement(seq) -> str
 
 
# Standalone test
if __name__ == "__main__":
    print(reverse_complement("ATGCGATCG"))   # CGATCGCAT
    print(reverse_complement("ATRYSWKM"))