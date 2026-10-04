"""Perturbation registry loading, validation, and prompt template rendering.

This module is the bridge between the versioned perturbation registry
(``data/perturbation_registry.yaml``) and the runner. It provides:

- a typed representation of a perturbation entry;
- schema validation for the registry as a whole;
- stable hashes for the registry and for each prompt template;
- a function that renders a prompt template with the required variables.

The registry is the authoritative source for perturbation metadata. The
Jinja2 templates are the authoritative source for prompt text. Neither is
allowed to introduce scope beyond what the schema and the templates
already declare.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from jsonschema import Draft202012Validator

from .models.manifests import sha256_hex


# Canonical identifiers used across the toolkit.
BASELINE_PROTOCOL_ID = "BASELINE_V0_1"
BASELINE_TEMPLATE_ID = "baseline.jinja2"

# Location of the Jinja2 prompt templates inside the package.
PROMPTS_DIR: Path = Path(__file__).parent / "prompts"

# Default registry path, relative to the repository root.
DEFAULT_REGISTRY_PATH: Path = Path("data") / "perturbation_registry.yaml"

# Default schema path, relative to the repository root.
DEFAULT_REGISTRY_SCHEMA_PATH: Path = (
    Path("schemas") / "perturbation_registry.schema.json"
)


@dataclass(frozen=True)
class Perturbation:
    """A single entry in the perturbation registry.

    Every field is required by the registry schema. ``status`` is frozen to
    ``declared_unvalidated`` in v0.1, and ``eligible_for_primary_claims`` is
    frozen to ``False``. Both constraints are enforced both by the schema
    and by the loader.
    """

    perturbation_id: str
    family: str
    perturbation_level: str
    status: str
    description: str
    expected_invariance_claim: str
    why_this_may_fail: str
    eligible_for_primary_claims: bool
    prompt_template_id: str
    positive_example: str
    negative_example: str


def load_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    """Load the perturbation registry as a plain dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
    """
    registry_path = Path(path)
    if not registry_path.exists():
        raise FileNotFoundError(f"Perturbation registry not found: {registry_path}")
    with open(registry_path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def validate_registry(
    registry: dict[str, Any],
    schema_path: str | Path = DEFAULT_REGISTRY_SCHEMA_PATH,
) -> None:
    """Validate the registry against its JSON Schema.

    Raises:
        jsonschema.ValidationError: If the registry does not conform.
        FileNotFoundError: If the schema file does not exist.
    """
    import json

    schema_file = Path(schema_path)
    if not schema_file.exists():
        raise FileNotFoundError(f"Registry schema not found: {schema_file}")
    with open(schema_file, "r", encoding="utf-8") as handle:
        schema = json.load(handle)

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(registry), key=lambda e: e.path)
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.path) or "<root>"
        raise ValueError(
            f"Perturbation registry failed schema validation at {location}: "
            f"{first.message}"
        )


def load_perturbations(
    path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    validate: bool = True,
    schema_path: str | Path = DEFAULT_REGISTRY_SCHEMA_PATH,
) -> list[Perturbation]:
    """Load and return the list of perturbation entries as dataclasses.

    When ``validate`` is True (the default), the registry is first checked
    against its JSON Schema. This is the recommended path for all code
    paths that consume the registry in production.

    Raises:
        ValueError: If the registry fails schema validation, or if any
            entry violates a v0.1 invariant.
    """
    registry = load_registry(path)

    if validate:
        validate_registry(registry, schema_path=schema_path)

    perturbations = [Perturbation(**entry) for entry in registry["perturbations"]]

    _assert_v01_invariants(perturbations)
    _assert_unique_ids(perturbations)

    return perturbations


def _assert_v01_invariants(perturbations: list[Perturbation]) -> None:
    """Enforce v0.1 invariants that the schema already guarantees.

    The schema is the first line of defense. This check is a second line,
    so that any accidental bypass of schema validation — for example by a
    caller passing ``validate=False`` — still fails loudly on the
    properties that define the epistemic position of v0.1.
    """
    for entry in perturbations:
        if entry.status != "declared_unvalidated":
            raise ValueError(
                f"Perturbation {entry.perturbation_id!r} has status "
                f"{entry.status!r}. In v0.1 every perturbation must be "
                f"'declared_unvalidated'."
            )
        if entry.eligible_for_primary_claims is not False:
            raise ValueError(
                f"Perturbation {entry.perturbation_id!r} is marked eligible "
                f"for primary claims. In v0.1 no perturbation may be "
                f"eligible for primary claims."
            )


def _assert_unique_ids(perturbations: list[Perturbation]) -> None:
    """Reject duplicate perturbation IDs.

    JSON Schema cannot enforce uniqueness of a field inside objects in an
    array, so this check is implemented explicitly.
    """
    ids = [entry.perturbation_id for entry in perturbations]
    if len(ids) != len(set(ids)):
        duplicates = sorted({pid for pid in ids if ids.count(pid) > 1})
        raise ValueError(
            f"Duplicate perturbation IDs in registry: {duplicates}"
        )


def registry_hash(path: str | Path = DEFAULT_REGISTRY_PATH) -> str:
    """Return ``sha256:<hex>`` of the raw registry file bytes.

    The hash covers the file as written on disk, not the parsed structure.
    This means that changing a comment or a blank line changes the hash.
    That is intentional: it makes drift in the registry visible even when
    the parsed content would be identical.
    """
    registry_path = Path(path)
    if not registry_path.exists():
        raise FileNotFoundError(f"Perturbation registry not found: {registry_path}")
    with open(registry_path, "rb") as handle:
        return sha256_hex(handle.read())


def template_hash(template_id: str) -> str:
    """Return ``sha256:<hex>`` of the raw prompt template bytes.

    Raises:
        FileNotFoundError: If the template does not exist.
    """
    template_path = PROMPTS_DIR / template_id
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    with open(template_path, "rb") as handle:
        return sha256_hex(handle.read())


def _build_environment() -> Environment:
    """Return the Jinja2 environment used for prompt rendering.

    ``StrictUndefined`` is enabled so that a missing variable raises an
    error instead of rendering an empty string. This is essential: a
    silently empty ``policy_text`` would produce a valid-looking but
    meaningless prompt, and every downstream metric would be unreliable.
    """
    return Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )


def render_template(
    *,
    template_id: str,
    policy_text: str,
    response_text: str,
) -> str:
    """Render a prompt template with the required variables.

    Args:
        template_id: Filename of the template (for example
            ``"baseline.jinja2"``).
        policy_text: The policy text to insert into the template.
        response_text: The response to be evaluated.

    Returns:
        The rendered prompt as a string.

    Raises:
        FileNotFoundError: If the template does not exist.
        jinja2.UndefinedError: If a required variable is missing.
    """
    environment = _build_environment()
    try:
        template = environment.get_template(template_id)
    except TemplateNotFound as exc:
        raise FileNotFoundError(
            f"Prompt template not found: {template_id}"
        ) from exc

    return template.render(
        policy_text=policy_text,
        response_text=response_text,
    )


def list_perturbation_ids(
    path: str | Path = DEFAULT_REGISTRY_PATH,
) -> list[str]:
    """Return the list of perturbation IDs in the registry, in file order."""
    perturbations = load_perturbations(path, validate=False)
    return [entry.perturbation_id for entry in perturbations]