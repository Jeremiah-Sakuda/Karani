"""Text normalization and the paragraph→offset map.

Everything downstream — span offsets, citation positions, the click-to-locus viewer, the
rendition hash — is defined against the output of this module. So it has exactly one
requirement, and it is absolute: **the same input must always produce the same output,
byte for byte, on every machine and in every Python process.**

That rules out a surprising amount. No dictionary iteration order. No locale-dependent case
folding. No regex that depends on the Unicode database version in a way that could shift
between releases. No "clean up whatever looks wrong" heuristics, which are exactly the kind
of thing that behaves differently on a colleague's laptop.

Changing anything here changes every `rendition_id` in existence, which is why the
normalizer carries a version string that participates in the hash. That is not a
formality — it is the mechanism by which a normalizer change announces itself instead of
silently re-pointing every stored citation at slightly different text.
"""

from __future__ import annotations

import re
import unicodedata

# Three or more consecutive newlines collapse to exactly two. Word processors and PDF
# extractors emit runs of blank lines that carry no meaning; leaving them in would make the
# paragraph map depend on which tool produced the file rather than on what the file says.
_BLANK_RUN = re.compile(r"\n{3,}")
_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)
# Non-breaking spaces, zero-width characters, and the BOM. These are invisible to a reader
# and would otherwise make two visually identical documents hash differently.
_INVISIBLE = re.compile(r"[ ​‌‍﻿]")


def normalize(raw: str) -> str:
    """Produce the canonical text form. Deterministic, idempotent, version-pinned."""
    # NFC first: composed and decomposed forms of the same accented character are visually
    # identical and would otherwise produce different hashes and different offsets.
    text = unicodedata.normalize("NFC", raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _INVISIBLE.sub(" ", text)
    text = _TRAILING_WS.sub("", text)
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip()


def paragraph_offsets(text: str) -> list[tuple[int, int]]:
    """Map paragraphs to `(start, end)` character offsets in the normalized text.

    Offsets are into the normalized text and are the only coordinates any citation ever
    uses. They are computed by scanning rather than by `str.split`, because splitting
    discards the positions and reconstructing them by re-joining assumes the separator was
    uniform — an assumption that is false the moment a document mixes separators.

    Paragraphs are blank-line-delimited blocks. A composition essay's natural unit is the
    paragraph, and it is also the unit an instructor points at when they say "here". Span
    granularity finer than that would produce citations no human would make; coarser would
    make "the cited line" a page.
    """
    offsets: list[tuple[int, int]] = []
    position = 0
    length = len(text)

    while position < length:
        # Skip the blank space between paragraphs.
        while position < length and text[position] == "\n":
            position += 1
        if position >= length:
            break

        start = position
        # A paragraph runs until a blank line (two consecutive newlines) or end of text.
        while position < length:
            if text[position] == "\n" and position + 1 < length and text[position + 1] == "\n":
                break
            position += 1
        end = position

        # Trim trailing newline/whitespace so the span covers text, not the gap after it.
        while end > start and text[end - 1] in "\n \t":
            end -= 1

        if end > start:
            offsets.append((start, end))

    return offsets


def normalize_with_offsets(raw: str) -> tuple[str, list[tuple[int, int]]]:
    text = normalize(raw)
    return text, paragraph_offsets(text)
