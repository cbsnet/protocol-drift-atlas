"""Command-line interface for Protocol Drift Atlas.

Subcommands:

- ``demo``               run the full pipeline with the mock provider.
- ``run --config``       run the pipeline with a hosted provider (OpenAI).
- ``report``             rebuild a Stability Card from an existing run.
- ``list-perturbations`` print the declared perturbations.
- ``validate-manifest``  validate a manifest against the JSON Schema.

The CLI never performs network calls unless a non-mock provider is
explicitly selected. The default behavior is offline, local, and free.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .counterexamples import (
    counterexamples_to_jsonl,
    extract_counterexamples,
    write_counterexamples_csv,
)
from .models.manifests import build_manifest, sha256_hex
from .perturbations import (
    BASELINE_PROTOCOL_ID,
    BASELINE_TEMPLATE_ID,
    DEFAULT_REGISTRY_PATH,
    DEFAULT_REGISTRY_SCHEMA_PATH,
    load_perturbations,
    registry_hash,
    template_hash,
)
from .providers.mock import MockProvider
from .reporting import build_card, write_card
from .runner import execute_run, load_corpus
from .scorers import load_records


# Default paths relative to the repository root.
DEFAULT_CORPUS = Path("data") / "demo_corpus.jsonl"
DEFAULT_RESPONSE_SCHEMA = Path("schemas") / "judgment_response.schema.json"
DEFAULT_MANIFEST_SCHEMA = Path("schemas") / "execution_manifest.schema.json"
DEFAULT_OUTPUT_DIR = Path("outputs") / "runs" / "demo"


REPRODUCIBILITY_NOTE = (
    "Repeatability is measured rather than assumed. Temperature=0 and a "
    "requested seed, where supported, do not guarantee identical outputs "
    "across model versions, providers, runtimes, hardware, or time."
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Configuration file is not a mapping: {path}")
    return data


def _validate_manifest(manifest: dict[str, Any], schema_path: Path) -> None:
    from jsonschema import Draft202012Validator

    schema = _load_json(schema_path)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(manifest), key=lambda e: e.path)
    if errors:
        first = errors[0]
        location = "/".join(str(p) for p in first.path) or "<root>"
        raise ValueError(
            f"Manifest failed schema validation at {location}: {first.message}"
        )


def _build_manifest(
    *,
    summary: dict[str, Any],
    provider_id: str,
    adapter_id: str,
    adapter_version: str,
    endpoint_type: str | None,
    model_requested: str,
    model_returned: str | None,
    provider_extras: dict[str, Any],
    registry_path: Path,
    corpus_path: Path,
    schema_path: Path,
    perturbations_ids: list[str],
    execution_role: str,
    temperature: float | None,
    top_p: float | None,
    max_output_tokens: int,
    seed_requested: int | None,
    seed_supported: bool,
) -> dict[str, Any]:
    """Build the execution manifest for a completed run."""
    with open(corpus_path, "rb") as handle:
        dataset_hash = sha256_hex(handle.read())
    with open(schema_path, "rb") as handle:
        response_schema_hash_value = sha256_hex(handle.read())

    return build_manifest(
        toolkit_version=__version__,
        source_revision=os.environ.get("PDA_SOURCE_REVISION"),
        run_id=summary["run_id"],
        execution_role=execution_role,
        provider_id=provider_id,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        endpoint_type=endpoint_type,
        model_requested=model_requested,
        model_returned=model_returned,
        parameters={
            "temperature": temperature,
            "top_p": top_p,
            "max_output_tokens": max_output_tokens,
            "seed_requested": seed_requested,
            "seed_supported": seed_supported,
            "reproducibility_note": REPRODUCIBILITY_NOTE,
        },
        baseline_protocol_id=BASELINE_PROTOCOL_ID,
        prompt_template_id=BASELINE_TEMPLATE_ID,
        prompt_template_hash=template_hash(BASELINE_TEMPLATE_ID),
        perturbation_registry_hash=registry_hash(registry_path),
        perturbation_ids=perturbations_ids,
        dataset_id=corpus_path.stem,
        dataset_hash=dataset_hash,
        response_schema_hash=response_schema_hash_value,
        provider_extras=provider_extras,
    )


def _write_outputs(
    *,
    card: dict[str, Any],
    manifest: dict[str, Any],
    counterexamples: list[dict[str, Any]],
    output_dir: Path,
    plots: bool,
) -> dict[str, str]:
    """Write all run artifacts and return a mapping of artifact names to paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True, ensure_ascii=False)
    paths["manifest"] = str(manifest_path)

    card_md = output_dir / "stability_card.md"
    card_json = output_dir / "stability_card.json"
    write_card(card, markdown_path=card_md, json_path=card_json)
    paths["card_markdown"] = str(card_md)
    paths["card_json"] = str(card_json)

    if counterexamples:
        ce_csv = output_dir / "counterexamples.csv"
        ce_jsonl = output_dir / "counterexamples.jsonl"
        write_counterexamples_csv(counterexamples, ce_csv)
        counterexamples_to_jsonl(counterexamples, ce_jsonl)
        paths["counterexamples_csv"] = str(ce_csv)
        paths["counterexamples_jsonl"] = str(ce_jsonl)

    if plots:
        try:
            from .visualize import generate_all_plots

            figures = generate_all_plots(card, output_dir / "figures")
            if figures:
                paths["figures_dir"] = str(output_dir / "figures")
        except RuntimeError as exc:
            print(f"[plots] skipped: {exc}", file=sys.stderr)

    return paths


def _print_summary(
    *,
    summary: dict[str, Any],
    output_dir: Path,
    artifact_paths: dict[str, str],
) -> None:
    print(f"Run ID: {summary['run_id']}")
    print(f"Records: {summary['records']}")
    print(f"Cache hits: {summary['cache_hits']}")
    print(f"Provider errors: {summary['provider_errors']}")
    print(f"Invalid outputs: {summary['invalid_outputs']}")
    print(f"Output directory: {output_dir}")
    for name, path in sorted(artifact_paths.items()):
        print(f"  {name}: {path}")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_demo(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry)
    corpus_path = Path(args.corpus)
    schema_path = Path(args.schema)
    output_dir = Path(args.output_dir)

    perturbations = load_perturbations(
        registry_path, schema_path=DEFAULT_REGISTRY_SCHEMA_PATH
    )
    response_schema = _load_json(schema_path)
    provider = MockProvider()

    summary = execute_run(
        corpus_path=corpus_path,
        perturbations=perturbations,
        provider=provider,
        model="mock",
        response_schema=response_schema,
        output_path=output_dir / "runs.jsonl",
        cache_dir=output_dir / "cache",
        runs=args.runs,
    )

    manifest = _build_manifest(
        summary=summary,
        provider_id=provider.provider_id,
        adapter_id=provider.adapter_id,
        adapter_version=provider.adapter_version,
        endpoint_type=provider.endpoint_type,
        model_requested="mock",
        model_returned="mock",
        provider_extras=dict(provider.manifest_extras()),
        registry_path=registry_path,
        corpus_path=corpus_path,
        schema_path=schema_path,
        perturbations_ids=[p.perturbation_id for p in perturbations],
        execution_role="custom",
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=50,
        seed_requested=None,
        seed_supported=False,
    )

    _validate_manifest(manifest, DEFAULT_MANIFEST_SCHEMA)

    records = load_records(output_dir / "runs.jsonl")
    card = build_card(manifest=manifest, records=records)
    counterexamples = extract_counterexamples(records)

    paths = _write_outputs(
        card=card,
        manifest=manifest,
        counterexamples=counterexamples,
        output_dir=output_dir,
        plots=not args.no_plots,
    )

    _print_summary(summary=summary, output_dir=output_dir, artifact_paths=paths)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run the pipeline with a hosted provider (OpenAI)."""
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Configuration not found: {config_path}", file=sys.stderr)
        return 2

    config = _load_yaml(config_path)
    provider_cfg = config.get("provider", {})
    model_cfg = config.get("model", {})
    exec_cfg = config.get("execution", {})
    paths_cfg = config.get("paths", {})
    params_cfg = config.get("parameters", {})

    provider_id = provider_cfg.get("provider_id", "openai")
    if provider_id != "openai":
        print(
            f"Unsupported provider in v0.1: {provider_id!r}. "
            "Only 'openai' is supported for hosted runs.",
            file=sys.stderr,
        )
        return 2

    api_key_env = provider_cfg.get("api_key_env", "OPENAI_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        print(
            f"Environment variable {api_key_env!r} is not set. "
            "Set it or use the mock demo instead.",
            file=sys.stderr,
        )
        return 2

    from .providers.openai_responses import OpenAIProvider

    provider = OpenAIProvider(
        api_key=api_key,
        base_url=provider_cfg.get("base_url") or None,
    )

    registry_path = Path(paths_cfg.get("registry", str(DEFAULT_REGISTRY_PATH)))
    corpus_path = Path(paths_cfg.get("corpus", str(DEFAULT_CORPUS)))
    schema_path = Path(paths_cfg.get("response_schema", str(DEFAULT_RESPONSE_SCHEMA)))
    output_dir = Path(paths_cfg.get("output_dir", "outputs/runs/hosted"))

    perturbations = load_perturbations(registry_path)
    response_schema = _load_json(schema_path)

    model_requested = model_cfg.get("requested", "gpt-4o-mini-2024-07-18")

    summary = execute_run(
        corpus_path=corpus_path,
        perturbations=perturbations,
        provider=provider,
        model=model_requested,
        response_schema=response_schema,
        output_path=output_dir / "runs.jsonl",
        cache_dir=output_dir / "cache",
        runs=exec_cfg.get("runs", 2),
        temperature=params_cfg.get("temperature", 0.0),
        top_p=params_cfg.get("top_p", 1.0),
        max_output_tokens=params_cfg.get("max_output_tokens", 50),
    )

    # Determine the model identifier actually returned by the provider.
    model_returned: str | None = None
    records = load_records(output_dir / "runs.jsonl")
    for record in records:
        if record.get("model_returned"):
            model_returned = record["model_returned"]
            break

    manifest = _build_manifest(
        summary=summary,
        provider_id=provider.provider_id,
        adapter_id=provider.adapter_id,
        adapter_version=provider.adapter_version,
        endpoint_type=provider.endpoint_type,
        model_requested=model_requested,
        model_returned=model_returned,
        provider_extras=dict(provider.manifest_extras()),
        registry_path=registry_path,
        corpus_path=corpus_path,
        schema_path=schema_path,
        perturbations_ids=[p.perturbation_id for p in perturbations],
        execution_role=exec_cfg.get("role", "reference_hosted"),
        temperature=params_cfg.get("temperature", 0.0),
        top_p=params_cfg.get("top_p", 1.0),
        max_output_tokens=params_cfg.get("max_output_tokens", 50),
        seed_requested=params_cfg.get("seed_requested"),
        seed_supported=False,
    )

    _validate_manifest(manifest, DEFAULT_MANIFEST_SCHEMA)

    card = build_card(manifest=manifest, records=records)
    counterexamples = extract_counterexamples(records)

    artifact_paths = _write_outputs(
        card=card,
        manifest=manifest,
        counterexamples=counterexamples,
        output_dir=output_dir,
        plots=not args.no_plots,
    )

    _print_summary(
        summary=summary, output_dir=output_dir, artifact_paths=artifact_paths
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Rebuild a Stability Card from an existing run file and manifest."""
    run_path = Path(args.input)
    manifest_path = Path(args.manifest)
    output_dir = Path(args.output_dir)

    if not run_path.exists():
        print(f"Run file not found: {run_path}", file=sys.stderr)
        return 2
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    manifest = _load_json(manifest_path)
    _validate_manifest(manifest, DEFAULT_MANIFEST_SCHEMA)
    records = load_records(run_path)
    card = build_card(manifest=manifest, records=records)
    counterexamples = extract_counterexamples(records)

    paths = _write_outputs(
        card=card,
        manifest=manifest,
        counterexamples=counterexamples,
        output_dir=output_dir,
        plots=not args.no_plots,
    )

    print(f"Card rebuilt from {run_path}")
    for name, path in sorted(paths.items()):
        print(f"  {name}: {path}")
    return 0


def cmd_list_perturbations(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry)
    perturbations = load_perturbations(registry_path)
    for entry in perturbations:
        print(
            f"{entry.perturbation_id}\t{entry.perturbation_level}\t"
            f"{entry.status}\t{entry.prompt_template_id}"
        )
    return 0


def cmd_validate_manifest(args: argparse.Namespace) -> int:
    manifest_path = Path(args.input)
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return 2
    manifest = _load_json(manifest_path)
    try:
        _validate_manifest(manifest, DEFAULT_MANIFEST_SCHEMA)
    except ValueError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    print("VALID")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _add_plots_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip figure generation (matplotlib not required).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pda",
        description=(
            "Protocol Drift Atlas: an open toolkit for measuring protocol "
            "sensitivity in LLM safety judgments."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"pda {__version__}"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser(
        "demo",
        help="Run the full pipeline with the mock provider (offline, free).",
    )
    demo.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    demo.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    demo.add_argument("--schema", default=str(DEFAULT_RESPONSE_SCHEMA))
    demo.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    demo.add_argument("--runs", type=int, default=2)
    _add_plots_flag(demo)
    demo.set_defaults(func=cmd_demo)

    run = sub.add_parser(
        "run",
        help="Run the pipeline with a hosted provider (OpenAI).",
    )
    run.add_argument(
        "--config", required=True, help="Path to a YAML configuration file."
    )
    _add_plots_flag(run)
    run.set_defaults(func=cmd_run)

    report = sub.add_parser(
        "report",
        help="Rebuild a Stability Card from an existing run file and manifest.",
    )
    report.add_argument("--input", required=True, help="Path to a runs.jsonl file.")
    report.add_argument(
        "--manifest", required=True, help="Path to a manifest.json file."
    )
    report.add_argument("--output-dir", default="outputs/runs/report")
    _add_plots_flag(report)
    report.set_defaults(func=cmd_report)

    lp = sub.add_parser(
        "list-perturbations",
        help="Print the declared perturbations from the registry.",
    )
    lp.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    lp.set_defaults(func=cmd_list_perturbations)

    vm = sub.add_parser(
        "validate-manifest",
        help="Validate a manifest against the JSON Schema.",
    )
    vm.add_argument("--input", required=True)
    vm.set_defaults(func=cmd_validate_manifest)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())