"""Runtime configuration.

Two rules govern this file.

**Model IDs are pinned strings, never aliases.** An alias silently changes what produced an
observation, which makes `provenance{}` a lie and makes two runs incomparable without
announcing that they are incomparable. Pinning is what lets `diff_runs.py` mean anything.

**Temperature is not configurable.** It is 0, it is defined here, and it is recorded in
`provenance{}` on every observation. A run whose temperature came from the shell is not
reproducible, and a reproducibility claim that depends on the operator's environment is not
a claim.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------------------
# Models (KAR-301, KAR-503)
# ---------------------------------------------------------------------------------------
# The contest requires "Gemini 3.5 or newer". Both pinned models satisfy that bar.
#
# The PRD originally specified "Gemini 3.5 Pro" for analysis. That publisher model does not
# exist: the 3.5 family is Flash and Flash-Lite, and the newest Pro-tier model is
# gemini-3.1-pro-preview -- which is *older* than 3.5 and would fail the mandatory
# requirement. The full reasoning is in docs/DEVIATIONS.md D-001.
#
# scripts/preflight_models.py resolves every ID below against the live publisher catalogue
# and fails loudly on a miss, so a model renamed or withdrawn before judging shows up as a
# red check rather than as a broken demo.
MODEL_ANALYSIS: Final[str] = os.environ.get("KARANI_MODEL_ANALYSIS", "gemini-3.6-flash")
MODEL_VERIFY: Final[str] = os.environ.get("KARANI_MODEL_VERIFY", "gemini-3.5-flash-lite")
MODEL_TRIAGE: Final[str] = os.environ.get("KARANI_MODEL_TRIAGE", "gemma-3-4b-it")

# Not configurable. See the module docstring.
TEMPERATURE: Final[float] = 0.0

# Bumping this invalidates the response cache and is the only variable in KAR-403's
# exemplar-loop acceptance test. Treat it as part of the model identity.
PROMPT_VERSION: Final[str] = "p2"

# ---------------------------------------------------------------------------------------
# Citation geometry (KAR-104)
# ---------------------------------------------------------------------------------------
# The number of characters of context captured on each side of a quote. This is the
# positional-identity mechanism, not decoration: a quote that genuinely appears in two
# different spans is distinguished by what surrounds it, and 32 characters is enough
# context to separate two occurrences of a repeated phrase in prose while staying short
# enough that a model can reproduce it exactly.
CONTEXT_CHARS: Final[int] = 32

# ---------------------------------------------------------------------------------------
# Bounds (KAR-307, KAR-314)
# ---------------------------------------------------------------------------------------
MAX_ATTEMPTS: Final[int] = int(os.environ.get("KARANI_MAX_ATTEMPTS", "2"))
T_MAX_SECONDS: Final[int] = int(os.environ.get("KARANI_T_MAX_SECONDS", "1200"))
MAX_TOTAL_ATTEMPTS: Final[int] = int(os.environ.get("KARANI_MAX_TOTAL_ATTEMPTS", "400"))
MAX_WALL_CLOCK_SECONDS: Final[int] = int(os.environ.get("KARANI_MAX_WALL_CLOCK_SECONDS", "2400"))

# A student with more than this fraction of criteria in NEEDS_HUMAN gets one INSUFFICIENT
# sheet rather than six separate holes in the anomaly queue (KAR-314).
INSUFFICIENT_THRESHOLD: Final[float] = 0.5

# ---------------------------------------------------------------------------------------
# Versions that participate in the rendition hash (KAR-304)
# ---------------------------------------------------------------------------------------
# Bumping either of these changes every rendition_id, which is the point: a normalizer
# change means the frozen artifact is a different artifact, and pretending otherwise would
# let a citation silently re-point at different text.
NORMALIZER_VERSION: Final[str] = "n1"
EXTRACTOR_VERSIONS: Final[dict[str, str]] = {
    "md": "md1",
    "txt": "md1",
    "docx": "docx1",
    "pdf": "pdf1",
}

StoreBackend = Literal["local", "emulator", "firestore"]
ModelBackend = Literal["cache", "vertex"]


@dataclass(frozen=True)
class Settings:
    """Environment-derived settings. Everything with a default runs offline."""

    project: str = ""
    location: str = "global"
    store_backend: StoreBackend = "local"
    model_backend: ModelBackend = "cache"
    local_store_dir: Path = REPO_ROOT / ".karani" / "store"
    cache_dir: Path = REPO_ROOT / "fixtures" / "cache"
    source_dir: Path = REPO_ROOT / "fixtures"
    golden_log: Path = REPO_ROOT / "fixtures" / "recorded-run.jsonl"
    armor_template: str = ""
    delivery_drive_folder_id: str = ""
    delivery_mode: str = "local"

    @classmethod
    def from_env(cls) -> Settings:
        def _path(key: str, default: Path) -> Path:
            raw = os.environ.get(key)
            return Path(raw).expanduser() if raw else default

        store = os.environ.get("KARANI_STORE_BACKEND", "local")
        model = os.environ.get("KARANI_MODEL_BACKEND", "cache")
        if store not in ("local", "emulator", "firestore"):
            raise ValueError(
                f"KARANI_STORE_BACKEND must be local|emulator|firestore, got {store!r}"
            )
        if model not in ("cache", "vertex"):
            raise ValueError(f"KARANI_MODEL_BACKEND must be cache|vertex, got {model!r}")

        return cls(
            project=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
            store_backend=store,  # type: ignore[arg-type]
            model_backend=model,  # type: ignore[arg-type]
            local_store_dir=_path("KARANI_LOCAL_STORE_DIR", cls.local_store_dir),
            cache_dir=_path("KARANI_CACHE_DIR", cls.cache_dir),
            source_dir=_path("KARANI_SOURCE_DIR", cls.source_dir),
            golden_log=_path("KARANI_GOLDEN_LOG", cls.golden_log),
            armor_template=os.environ.get("KARANI_ARMOR_TEMPLATE", ""),
            delivery_drive_folder_id=os.environ.get("KARANI_DELIVERY_DRIVE_FOLDER_ID", ""),
            delivery_mode=os.environ.get("KARANI_DELIVERY_MODE", "local"),
        )
