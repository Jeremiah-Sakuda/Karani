"""Canonical serialization and hashing.

Everything in Karani that has to be *comparable* — event content hashes, rendition IDs,
artifact range hashes, the replay test's byte-stable snapshot — routes through this module.
One canonical form, used everywhere, or the comparisons quietly stop meaning anything.

The rules: keys sorted, no incidental whitespace, UTF-8 preserved rather than escaped, and
no floats where an equality comparison is intended.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Serialize to the one form Karani hashes and compares.

    `sort_keys` makes the output independent of dict construction order, which is what
    lets two processes that built the same payload by different code paths agree on its
    hash. `ensure_ascii=False` keeps a student's text as the characters they typed: escaping
    to \\uXXXX would make the hash depend on the serializer's escaping policy rather than on
    the content.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_fallback,
    )


def _fallback(obj: Any) -> Any:
    # Pydantic models and anything else that knows how to describe itself as data.
    for attr in ("model_dump", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            return fn(mode="json") if attr == "model_dump" else fn()
    if isinstance(obj, set | frozenset):
        return sorted(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"{type(obj).__name__} is not canonically serializable")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(payload: Any) -> str:
    """The hash used to decide whether two writes under the same event ID agree.

    This is the whole basis of `EventIdCollision` (KAR-105): identical payloads self-dedupe
    because a retried worker legitimately re-writes the same event, while differing payloads
    raise, because that means two different things claimed the same identity and silently
    keeping one of them would corrupt the log that every artifact is folded from.
    """
    return sha256_text(canonical_json(payload))
