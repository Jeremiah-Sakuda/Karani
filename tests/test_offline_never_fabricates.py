"""The offline demo path refuses to invent a response (README's central promise).

`make demo` is the first thing in the README and the thing every judge will run. What makes
it trustworthy is not that it produces output — a stub would do that — but that the output
is a replay of responses a real model actually produced, and that a gap in the recording is
reported rather than papered over.

An adversarial review found **nothing in the suite asserting either half**. Two mutations
survived all 169 tests:

    cache.py     raise MissingCacheEntry(...)  ->  return '{"observations": []}'
    client.py    CacheOnlyClient.generate      ->  return an invented string, cache untouched

Under the first, a judge running `make demo` on an incomplete cache gets a clean run with
silently empty analysis. Under the second, the offline demo is a *different system* from the
one in the video — same interface, different provenance — which is precisely the substitution
this project exists to argue against. A loud miss is recoverable; a quiet fake is not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from karani.analysis.cache import CacheKey, MissingCacheEntry, ResponseCache
from karani.analysis.client import CacheOnlyClient, open_client

KEY = CacheKey(
    rendition_id="rend-absent",
    prompt_version="p2",
    model_id="gemini-3.6-flash",
    temperature=0.0,
    attempt=0,
)


@pytest.fixture
def empty_cache(tmp_path: Path) -> ResponseCache:
    return ResponseCache(tmp_path / "cache")


def test_a_missing_entry_raises_rather_than_returning_anything(empty_cache: ResponseCache):
    """The mutation `return '{"observations": []}'` must not survive."""
    with pytest.raises(MissingCacheEntry):
        empty_cache.require(KEY)


def test_the_miss_names_the_key_it_wanted(empty_cache: ResponseCache):
    """A miss has to be actionable, or the operator's next move is to guess."""
    with pytest.raises(MissingCacheEntry) as excinfo:
        empty_cache.require(KEY)
    message = str(excinfo.value)
    # Every component of the key that an operator would need in order to work out why the
    # entry is absent — not the digest, which is not something anyone can act on.
    assert KEY.rendition_id in message
    assert KEY.prompt_version in message
    assert KEY.model_id in message
    assert f"attempt {KEY.attempt}" in message
    assert str(empty_cache.root) in message


def test_the_offline_client_raises_on_a_miss(empty_cache: ResponseCache):
    """Same property, at the layer the pipeline actually calls."""
    client = CacheOnlyClient(empty_cache)
    with pytest.raises(MissingCacheEntry):
        client.generate(system="s", prompt="p", model_id="gemini-3.6-flash", key=KEY)


def test_the_offline_client_returns_the_recorded_bytes_verbatim(empty_cache: ResponseCache):
    """The mutation `return an invented string` must not survive.

    Asserts the response came *from the cache* — not merely that it is well-formed. A stub
    returning valid-looking JSON would pass a schema check and fail this.
    """
    recorded = '{"observations": [{"criterion_id": "c1", "marker": "3f9c1a-recorded"}]}'
    empty_cache.put(KEY, recorded)

    response = CacheOnlyClient(empty_cache).generate(
        system="s", prompt="p", model_id="gemini-3.6-flash", key=KEY
    )
    assert response.text == recorded
    assert response.cached is True


def test_the_offline_client_reads_the_cache_it_was_given(tmp_path: Path):
    """A client that ignored its cache entirely would pass the test above by luck.

    So: put a distinct value in a second cache, and require that the client handed the
    *first* one does not produce it.
    """
    real = ResponseCache(tmp_path / "real")
    decoy = ResponseCache(tmp_path / "decoy")
    real.put(KEY, '{"marker": "from-the-real-cache"}')
    decoy.put(KEY, '{"marker": "from-the-decoy"}')

    text = (
        CacheOnlyClient(real)
        .generate(system="s", prompt="p", model_id="gemini-3.6-flash", key=KEY)
        .text
    )
    assert text == '{"marker": "from-the-real-cache"}'


def test_the_offline_backend_never_constructs_a_vertex_client(empty_cache: ResponseCache):
    """`--offline` must be a different code path, not a flag a live client consults."""
    client = open_client("cache", empty_cache)
    assert isinstance(client, CacheOnlyClient)
    assert client.backend == "cache"


def test_a_cache_miss_is_counted_as_a_miss(empty_cache: ResponseCache):
    """The hit-rate figure the README publishes has to be measuring something real."""
    assert empty_cache.misses == 0
    with pytest.raises(MissingCacheEntry):
        empty_cache.require(KEY)
    assert empty_cache.misses == 1
    assert empty_cache.hits == 0
