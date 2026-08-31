"""The cross-family second reader (KAR-417).

Layer 5: gemma3:4b, running locally, re-answers the entailment question for every citation
gemini-3.5-flash-lite accepted. The claim it buys — no single model's judgment turns a draft
into evidence — is only worth stating if the layer's honesty properties hold under test:

- disagreement escalates and is never retried
- unavailability is recorded as None, never as a pass
- the offline replay serves real recorded Gemma output, not a stub
- the layer is off by default, so every previously published number is untouched
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from karani.analysis.cache import CacheKey, ResponseCache
from karani.canon import sha256_text
from karani.config import MODEL_TRIAGE, PROMPT_VERSION, TEMPERATURE
from karani.render import render
from karani.store.local import read_jsonl_log
from karani.validate.second_reader import (
    check_second_reader,
    second_reader_enabled,
)

REPO = Path(__file__).resolve().parent.parent


def _key(claim: str, passage: str, submission: str = "") -> CacheKey:
    return CacheKey(
        rendition_id="rend-x",
        prompt_version=f"{PROMPT_VERSION}-second-reader",
        model_id=MODEL_TRIAGE,
        temperature=TEMPERATURE,
        attempt=0,
        feedback_hash=sha256_text(f"{claim}␟{passage}␟{submission}")[:32],
        criterion_scope="second-reader",
    )


@pytest.fixture
def cache(tmp_path: Path) -> ResponseCache:
    return ResponseCache(tmp_path / "cache")


def _check(cache: ResponseCache, claim="the claim", passage="the passage"):
    return check_second_reader(claim=claim, passage=passage, cache=cache, rendition_id="rend-x")


def test_off_by_default(monkeypatch):
    """Every published number from the main corpus predates this layer; the default must
    not silently change any of them."""
    monkeypatch.delenv("KARANI_SECOND_READER", raising=False)
    assert not second_reader_enabled()


def test_agreement_is_recorded_as_confirmed(cache, monkeypatch):
    monkeypatch.setenv("KARANI_OLLAMA_URL", "http://localhost:1")  # unreachable on purpose
    cache.put(_key("the claim", "the passage"), '{"supported": true, "reason": "it does"}')
    result = _check(cache)
    assert result.checked and result.confirmed and not result.disagreement


def test_disagreement_is_a_disagreement(cache, monkeypatch):
    monkeypatch.setenv("KARANI_OLLAMA_URL", "http://localhost:1")
    cache.put(_key("the claim", "the passage"), '{"supported": false, "reason": "it does not"}')
    result = _check(cache)
    assert result.checked and result.disagreement
    assert result.reason == "it does not"


def test_unavailable_is_not_run_never_a_pass(cache, monkeypatch):
    """The mutation this kills: `checked=False` -> `checked=True, confirmed=True` would let
    a missing Ollama silently approve everything."""
    monkeypatch.setenv("KARANI_OLLAMA_URL", "http://localhost:1")
    result = _check(cache)
    assert not result.checked
    assert not result.confirmed
    assert not result.disagreement  # not-run must not escalate either


def test_unparseable_is_not_run_not_failed(cache, monkeypatch):
    monkeypatch.setenv("KARANI_OLLAMA_URL", "http://localhost:1")
    cache.put(_key("the claim", "the passage"), "gemma got chatty instead of answering")
    result = _check(cache)
    assert not result.checked and not result.disagreement


def test_the_recorded_scholarship_run_carries_real_gemma_verdicts():
    """The bonus claim, checked against the committed artifact: every accepted citation on
    the scholarship run was confirmed by the second reader, and absence findings carry None
    -- Gemma never weighs in on a citation that does not exist."""
    rendered = render(
        "run-scholarship-p2", read_jsonl_log(REPO / "fixtures" / "scholarship-run.jsonl")
    )
    accepted = [o for o in rendered.claims if o["kind"] == "evidence"]
    absent = [o for o in rendered.claims if o["kind"] == "no_evidence"]
    assert len(accepted) >= 8 and len(absent) >= 1
    for o in accepted:
        assert o["verification"]["second_reader"] is True
    for o in absent:
        assert o["verification"]["second_reader"] is None


def test_the_gemma_responses_in_the_cache_are_real_recorded_output():
    """The committed cache holds actual gemma3:4b responses for this run -- with reasons,
    not bare booleans -- so `make demo-scholarship` replays a real second reader."""
    import glob

    entries = []
    for path in glob.glob(str(REPO / "fixtures" / "cache" / "**" / "*.json"), recursive=True):
        data = json.loads(Path(path).read_text())
        if data["key"].get("criterion_scope") == "second-reader":
            entries.append(data)
    assert len(entries) >= 8
    for entry in entries:
        assert entry["key"]["model_id"] == MODEL_TRIAGE
        parsed = json.loads(entry["response"])
        assert isinstance(parsed["supported"], bool)
        assert len(str(parsed.get("reason", ""))) > 10
