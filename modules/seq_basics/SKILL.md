# seq_basics — Skill Guidance for Gemini

This file is read by the client at startup and injected into Gemini's system prompt.
Its purpose is to give Gemini the domain knowledge it needs to use the tools in this
module correctly and interpret their results meaningfully.

---

## What this module does

The `seq_basics` module provides fundamental DNA sequence analysis tools for working
with sequences stored as resources or provided as raw strings.

---

## Available resources

| Resource name | Description |
|---------------|-------------|
| `pBR322`      | E. coli cloning vector pBR322, 4361 bp, circular, double-stranded. A classic lab plasmid commonly used as a reference sequence. Contains genes for ampicillin resistance (bla) and tetracycline resistance (tet). |

When a user refers to "pBR322" or "the plasmid", use the resource name `"pBR322"` directly
as the sequence argument — do not ask the user to paste the sequence.

---

## Tools and when to use them

### `dna_reverse_complement`
Returns the reverse complement of a DNA or RNA sequence.

Use when the user asks for:
- "reverse complement of X"
- "complement of the bottom strand"
- "what does the antisense strand look like"
- "flip the sequence"

The result is the same length as the input. Uppercase output.

### `dna_translate`
Translates a DNA coding sequence to a protein sequence using the standard genetic code.

Use when the user asks to:
- "translate", "get the protein", "what protein does this encode"
- work with a specific reading frame (1, 2, or 3)
- translate a specific region using `start` / `end` coordinates (0-indexed, end is exclusive)

**Frame guidance:**
- Frame 1 — start reading from the first base (default)
- Frame 2 — skip 1 base, then read triplets
- Frame 3 — skip 2 bases, then read triplets

**Stop codons** appear as `*` in the output. **Unrecognised codons** appear as `X`.

**Coordinate example:** "translate bases 100 to 200" → `start=100, end=200`
"translate the first 60bp" → `start=0, end=60` (or omit start, set `end=60`)

---

## Interpreting results

- A protein sequence like `MSKGEEK...` starting with `M` (methionine) suggests you've
  found the correct reading frame for a real open reading frame.
- A sequence full of `*` stop codons or `X` unknowns usually means the wrong frame,
  wrong coordinates, or the sequence is not a coding region.
- When translating a full plasmid, most of the output will be non-coding — only specific
  coordinate ranges will give meaningful protein sequence.

---

## Sequence input rules (handled automatically)

You never need to paste the full sequence. The framework resolves these automatically:
- `"pBR322"` → full 4361 bp sequence
- A raw string like `"ATGCGATCG"` → used as-is
- A FASTA string starting with `>` → sequence extracted automatically
- A GenBank string starting with `LOCUS` → sequence extracted automatically
