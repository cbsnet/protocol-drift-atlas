"""Shared fixtures for the Protocol Drift Atlas test suite.

All fixtures are pure: they read files or build in-memory objects. No
network calls, no API keys, no external services. The test suite must
run offline in a clean environment.

Paths are resolved relative to the repository root, computed from the
location of this file, so that pytest works regardless of the current
working directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest


# Repository root: tests/conftest.py -> tests -> repository root.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = REPOSITORY_ROOT / "data"
SCHEMAS_DIR = REPOSITORY_ROOT / "schemas"
EXAMPLES_DIR = REPOSITORY_ROOT / "examples"
SRC_DIR = REPOSITORY_ROOT / "src"
PROMPTS_DIR = SRC_DIR / "protocol_drift_atlas" / "prompts"


# ---------------------------------------------------------------------------
# Path fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def repository_root() -> Path:
    return REPOSITORY_ROOT


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture(scope="session")
def schemas_dir() -> Path:
    return SCHEMAS_DIR


@pytest.fixture(scope="session")
def examples_dir() -> Path:
    return EXAMPLES_DIR


@pytest.fixture(scope="session")
def prompts_dir() -> Path:
    return PROMPTS_DIR


@pytest.fixture(scope="session")
def registry_path() -> Path:
    return DATA_DIR / "perturbation_registry.yaml"


@pytest.fixture(scope="session")
def registry_schema_path() -> Path:
    return SCHEMAS_DIR / "perturbation_registry.schema.json"


@pytest.fixture(scope="session")
def manifest_schema_path() -> Path:
    return SCHEMAS_DIR / "execution_manifest.schema.json"


@pytest.fixture(scope="session")
def judgment_schema_path() -> Path:
    return SCHEMAS_DIR / "judgment_response.schema.json"


@pytest.fixture(scope="session")
def corpus_path() -> Path:
    return DATA_DIR / "demo_corpus.jsonl"


# ---------------------------------------------------------------------------
# Schema loaders
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def load_json_schema():
    """Return a function that reads a JSON Schema file into a dict."""
    import json

    def _load(path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    return _load


@pytest.fixture(scope="session")
def load_yaml_file():
    """Return a function that reads a YAML file into a dict."""
    import yaml

    def _load(path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    return _load


@pytest.fixture(scope="session")
def load_jsonl_file():
    """Return a function that reads a JSONL file into a list of dicts.

    Empty lines are ignored. Each non-empty line must be a JSON object.
    """
    import json

    def _load(path: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
        return records

    return _load


# ---------------------------------------------------------------------------
# Synthetic records
# ---------------------------------------------------------------------------


@pytest.fixture
def make_record():
    """Return a factory that builds synthetic run records.

    The factory produces dicts that match the shape of the records
    written by the runner, so that tests of scorers, counterexamples,
    and reporting can operate on realistic inputs without any network
    calls.

    Defaults are chosen so that a single call produces a minimal but
    valid record. Override individual fields via keyword arguments.
    """

    def _make(
        *,
        item_id: str = "ITEM_001",
        run_index: int = 0,
        condition_id: str = "BASELINE_V0_1",
        status: str = "completed",
        verdict: str | None = "safe",
        normalized_verdict: str | None = None,
        risk_bucket: str | None = "test_bucket",
        provider_id: str = "mock",
        adapter_version: str = "0.1.0",
        model_requested: str = "mock",
        model_returned: str | None = "mock",
        request_hash: str | None = None,
        raw_text: str | None = None,
        cache_hit: bool = False,
    ) -> dict[str, Any]:
        # When a verdict is supplied but the caller does not pass an
        # explicit normalized verdict, mirror the verdict. When the
        # status is not completed, the normalized verdict must be None.
        if normalized_verdict is None and status == "completed":
            normalized_verdict = verdict
        if status != "completed":
            normalized_verdict = None
            verdict = None

        if raw_text is None:
            raw_text = (
                f'{{"verdict": "{verdict}"}}'
                if verdict is not None
                else ""
            )

        if request_hash is None:
            request_hash = (
                f"sha256:{'0' * 60}{run_index:02d}{condition_id[-1:]}"
            )

        return {
            "run_id": "test-run",
            "run_index": run_index,
            "timestamp_utc": "2026-10-04T00:00:00+00:00",
            "item_id": item_id,
            "risk_bucket": risk_bucket,
            "condition_id": condition_id,
            "prompt_template_id": "baseline.jinja2",
            "prompt_template_hash": "sha256:" + "a" * 64,
            "request_hash": request_hash,
            "cache_hit": cache_hit,
            "status": status,
            "verdict": verdict,
            "normalized_verdict": normalized_verdict,
            "brief_rationale": None,
            "raw_text": raw_text,
            "provider_id": provider_id,
            "adapter_version": adapter_version,
            "model_requested": model_requested,
            "model_returned": model_returned,
            "request_id": None,
            "input_tokens": None,
            "output_tokens": None,
            "latency_ms": None,
        }

    return _make


# ---------------------------------------------------------------------------
# Manifest helper
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_manifest() -> Mapping[str, Any]:
    """Return a minimal but schema-valid execution manifest.

    This is a plain dict, not produced by build_manifest, so that
    tests of the reporting layer can run independently of the manifest
    builder. A separate test ensures that build_manifest produces
    manifests that validate against the same schema.
    """
    return {
        "schema_version": "0.1.0",
        "toolkit": {
            "name": "protocol-drift-atlas",
            "version": "0.1.0",
            "source_revision": None,
        },
        "execution": {
            "run_id": "test-run-0001",
            "timestamp_utc": "2026-10-04T00:00:00+00:00",
            "execution_role": "custom",
        },
        "provider": {
            "provider_id": "mock",
            "adapter_id": "mock",
            "adapter_version": "0.1.0",
            "endpoint_type": None,
        },
        "model": {
            "model_requested": "mock",
            "model_returned": "mock",
        },
        "parameters": {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_output_tokens": 50,
            "seed_requested": None,
            "seed_supported": False,
            "reproducibility_note": (
                "Repeatability is measured rather than assumed."
            ),
        },
        "protocol": {
            "baseline_protocol_id": "BASELINE_V0_1",
            "prompt_template_id": "baseline.jinja2",
            "prompt_template_hash": "sha256:" + "a" * 64,
            "perturbation_registry_hash": "sha256:" + "b" * 64,
            "perturbation_ids": [
                "P1_RUBRIC_PARAPHRASE",
                "P2_RESPONSE_POSITION",
                "P3_DECISION_LABEL_WORDING",
                "P4_AUDIT_FRAMING",
            ],
        },
        "artifacts": {
            "dataset_id": "pda_demo_corpus_v0_1",
            "dataset_hash": "sha256:" + "c" * 64,
            "response_schema_hash": "sha256:" + "d" * 64,
        },
        "provider_extras": {},
    }