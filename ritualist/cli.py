from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
import time
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from .actions.registry import create_default_registry
from .adapters.fake import FakeAdapters
from .adapters import create_default_adapters
from .app_setup import initialize_app
from .canvas import (
    CanvasRuntimeController,
    CanvasRuntimeContext,
    build_edit_plan,
    build_canvas_runtime_model,
    build_canvas_view_model,
    canvas_show_payload,
    canvas_performance_diagnostics,
    create_edit_session,
    create_default_canvases,
    create_mock_canvas,
    default_canvas_for_host,
    default_canvas_document,
    dispatch_canvas_action,
    list_canvases,
    load_bundled_canvas,
    load_canvas,
    resolve_canvas_host_config,
    save_canvas,
    validate_canvas,
    validate_canvas_document,
    validate_canvas_structure,
)
from .canvas_packs import (
    ImportedVisualPackRecord,
    VisualPackResult,
    export_canvas_pack,
    export_theme_pack,
    import_canvas_pack,
    import_theme_pack,
)
from .doctor import build_doctor_report
from .errors import RitualistError
from .executor import WorkflowExecutor
from .intent_planner import (
    build_plan_doctor_report,
    compile_plan_reference,
    plan_preview_payload,
)
from .learning_service import (
    FORBIDDEN_CAPABILITY_SUMMARY,
    LOCAL_ONLY_EXPLANATION,
    delete_learning_data,
    disable_learning,
    enable_learning,
    learning_journal_payload,
    learning_scan_payload,
    learning_sources_payload,
    learning_status_payload,
)
from .logging_setup import setup_logging
from .overlay import format_confirmation_request
from .packs import (
    ImportedPackRecord,
    enable_import,
    export_recipe_pack,
    import_pack as import_recipe_pack,
    list_imports as list_pack_imports,
    validate_imported_pack,
    validate_pack,
)
from .perf import PerformanceReport, measure_operation
from .paths import (
    app_data_dir,
    browser_profiles_dir,
    canvases_dir,
    config_dir,
    config_file,
    imported_canvas_packs_dir,
    imported_packs_dir,
    imported_packs_path,
    imported_suite_packs_dir,
    imported_theme_packs_dir,
    learning_journal_path,
    learning_suggestions_path,
    logs_dir,
    recipes_dir,
    runs_dir,
    themes_dir,
)
from .primitives import PrimitiveSpec, create_primitive_registry
from .primitive_runtime import run_read_only_primitive
from .policy import (
    PolicyFinding,
    PolicyProfile,
    PolicyReport,
    build_policy_report_for_recipe,
    build_policy_report_for_recipe_reference,
    explain_primitive_policy,
    policy_overview,
)
from .recipe_loader import discover_recipes, load_recipe_for_diagnostics, load_recipe_reference
from .run_logs import (
    RunLogWriter,
    RunbookSummary,
    append_operator_note,
    list_recent_runs,
    load_run,
    reconcile_running_runs,
    summarize_run_record,
    summarize_step_results,
)
from .rooms import room_list_payload, room_show_payload
from .runtime_control import RuntimeControl
from .suggestions.service import (
    delete_all_suggestions_payload,
    dismiss_suggestion_payload,
    list_suggestions_payload,
    scan_suggestions_payload,
    show_suggestion_payload,
)
from .suite_packs import (
    ImportedSuitePackRecord,
    SuitePackExportResult,
    export_suite_pack,
    import_suite_pack,
    list_suite_imports,
    validate_suite_pack,
)
from .target_resolution import (
    compile_target_start_plan,
    resolve_target,
    target_plan_payload,
)
from .themes import (
    list_themes,
    load_theme,
    theme_show_payload,
    validate_theme,
)

app = typer.Typer(help="Run local, inspectable desktop rituals.")
perf_app = typer.Typer(help="Measure Ritualist CLI operations without timing gates.")
pack_app = typer.Typer(help="Export, import, and review portable local recipe packs.")
primitive_app = typer.Typer(help="Inspect primitive kernel metadata.")
policy_app = typer.Typer(help="Inspect primitive policy and local pack governance.")
diagnostics_app = typer.Typer(help="Collect redacted local diagnostics artifacts.")
plan_app = typer.Typer(help="Preview deterministic intent-to-primitive plans.")
target_app = typer.Typer(help="Discover and preview local target start plans.")
learning_app = typer.Typer(help="Manage local, opt-in learning data.")
suggestions_app = typer.Typer(help="Review local, on-demand learning suggestions.")
canvas_app = typer.Typer(help="Inspect and validate local Ritualist Canvas documents.")
canvas_pack_app = typer.Typer(help="Export and import local visual Canvas packs.")
canvas_theme_app = typer.Typer(help="Export and import local visual theme packs.")
theme_app = typer.Typer(help="Inspect and validate safe declarative Ritualist themes.")
room_app = typer.Typer(help="Inspect starter Ritualist Rooms backed by Canvas templates.")
suite_app = typer.Typer(help="Export, import, and review quarantined whole-Room suite packs.")
app.add_typer(perf_app, name="perf")
app.add_typer(pack_app, name="pack")
app.add_typer(primitive_app, name="primitive")
app.add_typer(policy_app, name="policy")
app.add_typer(diagnostics_app, name="diagnostics")
app.add_typer(plan_app, name="plan")
app.add_typer(target_app, name="target")
app.add_typer(learning_app, name="learning")
app.add_typer(suggestions_app, name="suggestions")
app.add_typer(canvas_app, name="canvas")
app.add_typer(theme_app, name="theme")
app.add_typer(room_app, name="room")
app.add_typer(suite_app, name="suite")
canvas_app.add_typer(canvas_pack_app, name="pack")
canvas_app.add_typer(canvas_theme_app, name="theme")
console = Console()


@app.command()
def init() -> None:
    """Create Ritualist app directories and install bundled sample recipes."""
    report = initialize_app()
    console.print("[green]Ritualist initialized.[/]")
    _print_init_report(report)
    _print_paths(report.paths)


@app.command("list")
def list_recipes() -> None:
    """List recipes installed in the user recipes directory."""
    rows = discover_recipes()
    table = Table(title="Installed Recipes")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Path")
    table.add_column("Status")
    for path, recipe, error in rows:
        if recipe is None:
            table.add_row(path.stem, "", escape(str(path)), f"[red]{escape(error or 'invalid')}[/]")
        else:
            table.add_row(
                escape(recipe.id),
                escape(recipe.name),
                escape(str(path)),
                "[green]valid[/]",
            )
    console.print(table)
    if not rows:
        console.print("No recipes found. Run [bold]ritualist init[/] first.")


@app.command()
def paths() -> None:
    """Show Ritualist's local data directories."""
    _print_paths(
        {
            "app_data": app_data_dir(),
            "config": config_dir(),
            "config_file": config_file(),
            "recipes": recipes_dir(),
            "imported_packs": imported_packs_dir(),
            "canvases": canvases_dir(),
            "imported_canvas_packs": imported_canvas_packs_dir(),
            "themes": themes_dir(),
            "imported_theme_packs": imported_theme_packs_dir(),
            "imported_suite_packs": imported_suite_packs_dir(),
            "logs": logs_dir(),
            "runs": runs_dir(),
            "browser_profiles": browser_profiles_dir(),
            "learning_journal": learning_journal_path(),
            "learning_suggestions": learning_suggestions_path(),
        }
    )


@app.command()
def actions(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable action metadata."),
    ] = False,
) -> None:
    """List registered action metadata."""
    metadata_items = create_default_registry().metadata_items()
    if json_output:
        console.print_json(data=[metadata.to_dict() for metadata in metadata_items])
        return

    table = Table(title="Registered Actions")
    table.add_column("Action", no_wrap=True)
    table.add_column("Category")
    table.add_column("Side Effect", no_wrap=True)
    table.add_column("Confirmation", no_wrap=True)
    table.add_column("Imported", no_wrap=True)
    for metadata in metadata_items:
        table.add_row(
            escape(metadata.action_name),
            escape(metadata.category),
            escape(metadata.side_effect_level),
            escape(metadata.confirmation_policy),
            "yes" if metadata.allowed_in_imported_packs else "no",
        )
    console.print(table)


@app.command()
def primitives(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable primitive metadata."),
    ] = False,
) -> None:
    """List primitive kernel metadata derived from registered actions."""
    registry = create_primitive_registry()
    specs = registry.specs()
    if json_output:
        console.print_json(data=[spec.to_dict() for spec in specs])
        return

    table = Table(title="Primitive Kernel")
    table.add_column("Primitive", no_wrap=True)
    table.add_column("Action", no_wrap=True)
    table.add_column("Risk", no_wrap=True)
    table.add_column("Capabilities")
    table.add_column("Platforms")
    table.add_column("Imported", no_wrap=True)
    table.add_column("Adapter", no_wrap=True)
    for spec in specs:
        table.add_row(
            escape(spec.primitive_id),
            escape(spec.action_name or ""),
            escape(spec.risk.value),
            escape(", ".join(capability.value for capability in spec.required_capabilities) or "none"),
            escape(", ".join(spec.supported_platforms)),
            "yes" if spec.allowed_in_imported_packs else "no",
            escape(spec.adapter_binding.adapter_id),
        )
    console.print(table)


@primitive_app.command("show")
def primitive_show(
    primitive_id: Annotated[str, typer.Argument(help="Primitive id such as browser.session.open.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable primitive metadata."),
    ] = False,
) -> None:
    """Show one primitive by full family.verb id."""
    registry = create_primitive_registry()
    try:
        spec = registry.spec(primitive_id)
    except KeyError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    if json_output:
        console.print_json(data=spec.to_dict())
        return
    _print_primitive_spec(spec)


@primitive_app.command("families")
def primitive_families(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable primitive family names."),
    ] = False,
) -> None:
    """List primitive families currently represented by registered primitives."""
    families = create_primitive_registry().families()
    if json_output:
        console.print_json(data=families)
        return
    table = Table(title="Primitive Families")
    table.add_column("Family")
    for family in families:
        table.add_row(escape(family))
    console.print(table)


@primitive_app.command("run")
def primitive_run(
    primitive_id: Annotated[str, typer.Argument(help="Read-only primitive id to run.")],
    params: Annotated[
        list[str] | None,
        typer.Option("--param", "-p", help="Primitive parameter in KEY=VALUE form."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Describe the primitive without reading host state."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable execution result."),
    ] = False,
) -> None:
    """Run a read-only primitive directly."""
    try:
        result = run_read_only_primitive(
            primitive_id,
            parameters=_parse_primitive_params(params or []),
            dry_run=dry_run,
        )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=result.to_dict())
        return
    _print_primitive_result(result)
    if result.status == "failed":
        raise typer.Exit(1)


@learning_app.command("status")
def learning_status(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable Local Learning status."),
    ] = False,
) -> None:
    """Show Local Learning enablement, sources, and local data paths."""
    payload = learning_status_payload()
    if json_output:
        console.print_json(data=payload)
        return
    _print_learning_status(payload)


@learning_app.command("enable")
def learning_enable(
    source_ids: Annotated[
        list[str] | None,
        typer.Option(
            "--source",
            "-s",
            help="Explicitly select an allowed source: ritualist_journal, open_windows, or recent_items.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable Local Learning status."),
    ] = False,
) -> None:
    """Enable local-only learning for explicitly selected sources."""
    try:
        payload = enable_learning(source_ids or [])
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=payload)
        return
    console.print("[green]Local Learning enabled.[/]")
    _print_learning_status(payload)


@learning_app.command("disable")
def learning_disable(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable Local Learning status."),
    ] = False,
) -> None:
    """Disable future Local Learning writes while preserving existing data."""
    try:
        payload = disable_learning()
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=payload)
        return
    console.print("[green]Local Learning disabled.[/]")
    console.print("Existing local learning data was preserved.")
    _print_learning_status(payload)


@learning_app.command("sources")
def learning_sources(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable Local Learning source metadata."),
    ] = False,
) -> None:
    """List allowed Local Learning sources and current source consent state."""
    payload = learning_sources_payload()
    if json_output:
        console.print_json(data=payload)
        return
    _print_learning_sources(payload)


@learning_app.command("scan")
def learning_scan(
    limit: Annotated[
        int,
        typer.Option("--limit", min=0, help="Maximum on-demand activity signals to return."),
    ] = 50,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable on-demand scan results."),
    ] = False,
) -> None:
    """Run a one-shot Local Learning scan without starting background collection."""
    payload = learning_scan_payload(max_signals=limit)
    if json_output:
        console.print_json(data=payload)
        return
    _print_learning_scan(payload)


@learning_app.command("journal")
def learning_journal(
    limit: Annotated[
        int,
        typer.Option("--limit", min=0, help="Maximum Local Learning journal events to return."),
    ] = 100,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable journal events."),
    ] = False,
) -> None:
    """Show local Ritualist-owned learning journal events."""
    payload = learning_journal_payload(limit=limit)
    if json_output:
        console.print_json(data=payload)
        return
    _print_learning_journal(payload)


@learning_app.command("delete-data")
def learning_delete_data(
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Delete local learning data without an interactive prompt."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable deletion results."),
    ] = False,
) -> None:
    """Delete local journal and suggestion data files."""
    if not yes and not typer.confirm(
        "Delete local learning journal and suggestion data?",
        default=False,
    ):
        console.print("Cancelled.")
        raise typer.Exit(1)
    payload = delete_learning_data()
    if json_output:
        console.print_json(data=payload)
        return
    _print_learning_delete(payload)


@suggestions_app.command("scan")
def suggestions_scan(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview suggestions without persisting them."),
    ] = False,
    min_confidence: Annotated[
        float,
        typer.Option(
            "--min-confidence",
            min=0.0,
            max=1.0,
            help="Minimum suggestion confidence to return.",
        ),
    ] = 0.0,
    include_sensitive: Annotated[
        bool,
        typer.Option("--include-sensitive", help="Include suggestions marked sensitive."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable suggestion scan results."),
    ] = False,
) -> None:
    """Mine review-only suggestions from one on-demand Local Learning scan."""
    try:
        payload = scan_suggestions_payload(
            dry_run=dry_run,
            min_confidence=min_confidence,
            include_sensitive=include_sensitive,
        )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=payload)
        return
    _print_suggestions_scan(payload)


@suggestions_app.command("list")
def suggestions_list(
    min_confidence: Annotated[
        float,
        typer.Option(
            "--min-confidence",
            min=0.0,
            max=1.0,
            help="Minimum suggestion confidence to return.",
        ),
    ] = 0.0,
    include_sensitive: Annotated[
        bool,
        typer.Option("--include-sensitive", help="Include suggestions marked sensitive."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable stored suggestions."),
    ] = False,
) -> None:
    """List stored review-only suggestions."""
    try:
        payload = list_suggestions_payload(
            min_confidence=min_confidence,
            include_sensitive=include_sensitive,
        )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=payload)
        return
    _print_suggestions_list(payload, title="Stored Suggestions")


@suggestions_app.command("show")
def suggestions_show(
    suggestion_id: Annotated[str, typer.Argument(help="Suggestion id to inspect.")],
    include_sensitive: Annotated[
        bool,
        typer.Option("--include-sensitive", help="Show suggestions marked sensitive."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable suggestion details."),
    ] = False,
) -> None:
    """Show one stored suggestion without creating artifacts."""
    try:
        payload = show_suggestion_payload(
            suggestion_id,
            include_sensitive=include_sensitive,
        )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=payload)
        return
    _print_suggestion_show(payload)


@suggestions_app.command("dismiss")
def suggestions_dismiss(
    suggestion_id: Annotated[str, typer.Argument(help="Suggestion id to dismiss.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable dismissal result."),
    ] = False,
) -> None:
    """Dismiss one stored suggestion."""
    try:
        payload = dismiss_suggestion_payload(suggestion_id)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=payload)
        return
    console.print(f"[green]Dismissed suggestion:[/] {escape(suggestion_id)}")


@suggestions_app.command("delete-all")
def suggestions_delete_all(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Report stored suggestion deletion without deleting."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Delete stored suggestions without an interactive prompt.",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable deletion result."),
    ] = False,
) -> None:
    """Delete all stored suggestions without touching learning journal data."""
    if not dry_run and not yes and not typer.confirm(
        "Delete all stored suggestions?",
        default=False,
    ):
        console.print("Cancelled.")
        raise typer.Exit(1)
    try:
        payload = delete_all_suggestions_payload(dry_run=dry_run)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=payload)
        return
    _print_suggestions_delete_all(payload)


def _print_learning_status(payload: dict[str, object]) -> None:
    table = Table(title="Local Learning")
    table.add_column("Field", no_wrap=True)
    table.add_column("Value", overflow="fold")
    rows = {
        "enabled": payload.get("enabled"),
        "effective_enabled": payload.get("effective_enabled"),
        "selected_sources": ", ".join(str(item) for item in payload.get("selected_sources", [])) or "none",
        "enabled_sources": ", ".join(str(item) for item in payload.get("enabled_sources", [])) or "none",
        "consent_version": payload.get("consent_version") or "none",
        "consent_timestamp": payload.get("consent_timestamp") or "none",
        "local_only": payload.get("local_only"),
        "background_collection": payload.get("background_collection"),
        "config_path": payload.get("config_path"),
    }
    for key, value in rows.items():
        table.add_row(escape(key), escape(str(value)))
    data_paths = payload.get("data_paths")
    if isinstance(data_paths, dict):
        for name, item in data_paths.items():
            if not isinstance(item, dict):
                continue
            exists = "exists" if item.get("exists") else "missing"
            table.add_row(
                f"data:{escape(str(name))}",
                f"{escape(str(item.get('path', '')))} ({escape(exists)})",
            )
    console.print(table)
    console.print(escape(str(payload.get("local_only_explanation") or LOCAL_ONLY_EXPLANATION)))
    console.print(escape(str(payload.get("forbidden_capability_summary") or FORBIDDEN_CAPABILITY_SUMMARY)))


def _print_learning_sources(payload: dict[str, object]) -> None:
    table = Table(title="Local Learning Sources")
    table.add_column("Source", no_wrap=True)
    table.add_column("Enabled", no_wrap=True)
    table.add_column("Selected", no_wrap=True)
    table.add_column("Consented", no_wrap=True)
    table.add_column("Description", overflow="fold")
    sources = payload.get("sources")
    source_rows = sources if isinstance(sources, list) else []
    for source in source_rows:
        if not isinstance(source, dict):
            continue
        table.add_row(
            escape(str(source.get("id", ""))),
            "yes" if source.get("enabled") else "no",
            "yes" if source.get("selected") else "no",
            "yes" if source.get("consented") else "no",
            escape(str(source.get("description", ""))),
        )
    console.print(table)
    console.print("Sources are disabled by default and require explicit selection.")
    console.print(escape(LOCAL_ONLY_EXPLANATION))


def _print_learning_scan(payload: dict[str, object]) -> None:
    console.print("On-demand scan only; background collection remains disabled.")
    collection = payload.get("collection")
    if not isinstance(collection, dict):
        return
    signals = collection.get("signals")
    signal_rows = signals if isinstance(signals, list) else []
    if signal_rows:
        table = Table(title="Activity Signals")
        table.add_column("Kind", no_wrap=True)
        table.add_column("Source", no_wrap=True)
        table.add_column("Label", overflow="fold")
        table.add_column("Value", overflow="fold")
        for signal in signal_rows:
            if not isinstance(signal, dict):
                continue
            table.add_row(
                escape(str(signal.get("kind", ""))),
                escape(str(signal.get("source_id", ""))),
                escape(str(signal.get("label", ""))),
                escape(str(signal.get("value", ""))),
            )
        console.print(table)
    else:
        console.print("No activity signals collected.")

    warnings = collection.get("warnings")
    warning_rows = warnings if isinstance(warnings, list) else []
    if warning_rows:
        console.print("[bold]Warnings[/]")
        for warning in warning_rows:
            if isinstance(warning, dict):
                console.print(
                    "- "
                    f"{escape(str(warning.get('code', '')))}: "
                    f"{escape(str(warning.get('message', '')))}"
                )


def _print_learning_journal(payload: dict[str, object]) -> None:
    console.print(f"Journal: {escape(str(payload.get('path', '')))}")
    events = payload.get("events")
    event_rows = events if isinstance(events, list) else []
    if not event_rows:
        console.print("No local learning journal events found.")
        return
    table = Table(title=f"Journal Events ({len(event_rows)})")
    table.add_column("Event", no_wrap=True)
    table.add_column("Payload", overflow="fold")
    for event in event_rows:
        if not isinstance(event, dict):
            continue
        table.add_row(
            escape(str(event.get("event_type", ""))),
            escape(_format_metadata_value(event.get("payload", {}))),
        )
    console.print(table)


def _print_learning_delete(payload: dict[str, object]) -> None:
    table = Table(title="Deleted Local Learning Data")
    table.add_column("Name", no_wrap=True)
    table.add_column("Existed", no_wrap=True)
    table.add_column("Deleted", no_wrap=True)
    table.add_column("Path", overflow="fold")
    table.add_column("Error", overflow="fold")
    paths = payload.get("paths")
    path_rows = paths.items() if isinstance(paths, dict) else []
    for name, item in path_rows:
        if not isinstance(item, dict):
            continue
        table.add_row(
            escape(str(name)),
            "yes" if item.get("existed") else "no",
            "yes" if item.get("deleted") else "no",
            escape(str(item.get("path", ""))),
            escape(str(item.get("error", ""))),
        )
    console.print(table)


def _print_suggestions_scan(payload: dict[str, object]) -> None:
    console.print("On-demand suggestion scan only; no artifacts are created or executed.")
    console.print(
        "dry-run: "
        f"{'yes' if payload.get('dry_run') else 'no'} | "
        "persisted: "
        f"{escape(str(payload.get('persisted_count', 0)))}"
    )
    _print_suggestions_list(payload, title="Mined Suggestions")
    warnings = payload.get("warnings")
    warning_rows = warnings if isinstance(warnings, list) else []
    if warning_rows:
        console.print("[bold]Warnings[/]")
        for warning in warning_rows:
            if isinstance(warning, dict):
                console.print(
                    "- "
                    f"{escape(str(warning.get('code', '')))}: "
                    f"{escape(str(warning.get('message', '')))}"
                )


def _print_suggestions_list(payload: dict[str, object], *, title: str) -> None:
    suggestions = payload.get("suggestions")
    rows = suggestions if isinstance(suggestions, list) else []
    if not rows:
        console.print("No suggestions found.")
        return
    table = Table(title=title)
    table.add_column("ID", no_wrap=True)
    table.add_column("Kind", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Confidence", no_wrap=True)
    table.add_column("Privacy", no_wrap=True)
    table.add_column("Title", overflow="fold")
    for suggestion in rows:
        if not isinstance(suggestion, dict):
            continue
        table.add_row(
            escape(str(suggestion.get("id", ""))),
            escape(str(suggestion.get("kind", ""))),
            escape(str(suggestion.get("status", ""))),
            escape(f"{float(suggestion.get('confidence') or 0.0):.2f}"),
            escape(str(suggestion.get("privacy_level", ""))),
            escape(str(suggestion.get("title", ""))),
        )
    console.print(table)


def _print_suggestion_show(payload: dict[str, object]) -> None:
    suggestion = payload.get("suggestion")
    if not isinstance(suggestion, dict):
        console.print("No suggestion found.")
        return
    table = Table(title=f"Suggestion: {escape(str(suggestion.get('id', '')))}")
    table.add_column("Field", no_wrap=True)
    table.add_column("Value", overflow="fold")
    for key in (
        "kind",
        "status",
        "privacy_level",
        "confidence",
        "title",
        "description",
        "evidence_summary",
        "evidence_count",
        "sources",
        "missing_inputs",
    ):
        table.add_row(escape(key), escape(_format_metadata_value(suggestion.get(key, ""))))
    console.print(table)
    actions = suggestion.get("proposed_actions")
    action_rows = actions if isinstance(actions, list) else []
    if action_rows:
        action_table = Table(title="Review-Only Proposed Actions")
        action_table.add_column("Action", no_wrap=True)
        action_table.add_column("Details", overflow="fold")
        for action in action_rows:
            if isinstance(action, dict):
                action_table.add_row(
                    escape(str(action.get("action", ""))),
                    escape(_format_metadata_value(action)),
                )
        console.print(action_table)


def _print_suggestions_delete_all(payload: dict[str, object]) -> None:
    action = "Would delete" if payload.get("dry_run") else "Deleted"
    count_key = "would_delete_count" if payload.get("dry_run") else "deleted_count"
    console.print(
        f"{action} {escape(str(payload.get(count_key, 0)))} stored suggestion(s) "
        f"from {escape(str(payload.get('storage_path', '')))}."
    )


def _print_primitive_spec(spec: PrimitiveSpec) -> None:
    table = Table(title=f"Primitive: {escape(spec.primitive_id)}")
    table.add_column("Field", no_wrap=True)
    table.add_column("Value", overflow="fold")
    rows = {
        "display_name": spec.display_name,
        "description": spec.description,
        "action": spec.action_name or "",
        "risk": spec.risk.value,
        "confirmation_policy": spec.confirmation_policy,
        "allowed_in_imported_packs": "yes" if spec.allowed_in_imported_packs else "no",
        "capabilities": ", ".join(capability.value for capability in spec.required_capabilities) or "none",
        "platforms": ", ".join(spec.supported_platforms),
        "adapter": f"{spec.adapter_binding.adapter_id} ({spec.adapter_binding.binding_type})",
        "dry_run": spec.dry_run_behavior,
        "verification": spec.verification_behavior,
        "artifacts": spec.artifact_behavior,
    }
    for key, value in rows.items():
        table.add_row(escape(key), escape(value))
    console.print(table)
    if spec.parameters:
        parameter_table = Table(title="Parameters")
        parameter_table.add_column("Name")
        parameter_table.add_column("Required")
        parameter_table.add_column("Sensitive")
        for parameter in spec.parameters:
            parameter_table.add_row(
                escape(parameter.name),
                "yes" if parameter.required else "no",
                "yes" if parameter.sensitive else "no",
            )
        console.print(parameter_table)


def _print_primitive_result(result: object) -> None:
    console.print(f"status: {escape(str(result.status))}")
    console.print(f"message: {escape(str(result.message))}")
    if getattr(result, "details", None):
        console.print("[bold]details[/]")
        console.print_json(data=result.details)
    artifacts = getattr(result, "artifacts", ())
    if artifacts:
        table = Table(title="Artifacts")
        table.add_column("Type")
        table.add_column("Name")
        table.add_column("Path")
        table.add_column("Redacted")
        for artifact in artifacts:
            table.add_row(
                escape(str(artifact.artifact_type)),
                escape(str(artifact.name)),
                escape(str(artifact.path or "")),
                "yes" if artifact.redacted else "no",
            )
        console.print(table)


def _print_plan_preview(plan: object, doctor: object) -> None:
    table = Table(title=f"Plan Preview: {escape(str(plan.plan_id))}")
    table.add_column("Field", no_wrap=True)
    table.add_column("Value", overflow="fold")
    table.add_row("steps", str(len(plan.steps)))
    table.add_row("primitives", escape(", ".join(plan.required_primitives) or "none"))
    table.add_row("capabilities", escape(", ".join(plan.required_capabilities) or "none"))
    table.add_row("risks", escape(json.dumps(plan.risk_summary, sort_keys=True)))
    table.add_row("compatibility", escape(str(doctor.compatibility)))
    console.print(table)

    if plan.steps:
        step_table = Table(title="Plan Steps")
        step_table.add_column("#", justify="right")
        step_table.add_column("Primitive", no_wrap=True)
        step_table.add_column("Name")
        step_table.add_column("Risk", no_wrap=True)
        for index, step in enumerate(plan.steps, start=1):
            step_table.add_row(
                str(index),
                escape(step.primitive_id),
                escape(step.step_name or ""),
                escape(step.risk.value if step.risk else ""),
            )
        console.print(step_table)

    if plan.confirmations_needed:
        console.print("[bold]Confirmations needed[/]")
        for item in plan.confirmations_needed:
            console.print(f"- {escape(item)}")
    if plan.unresolved_questions:
        console.print("[bold]Unresolved[/]")
        for item in plan.unresolved_questions:
            console.print(f"- {escape(item)}")
    notable = [
        check
        for check in doctor.checks
        if check.status in {"error", "warn"}
        and check.section in {"Policy", "Primitives", "Variables"}
    ]
    if notable:
        console.print("[bold]Plan Doctor[/]")
        for check in notable:
            console.print(f"- {escape(check.section)}: {escape(check.message)}")


def _print_target_resolution(resolution: object) -> None:
    target = getattr(resolution, "target", None)
    title = f"Target: {getattr(target, 'display_name', None) or getattr(resolution, 'query', '')}"
    table = Table(title=escape(title))
    table.add_column("Field", no_wrap=True)
    table.add_column("Value", overflow="fold")
    table.add_row("state", escape(str(getattr(resolution, "state").value)))
    table.add_row("matched", escape(str(getattr(resolution, "matched_alias", "") or "")))
    table.add_row("candidates", str(len(getattr(resolution, "candidates", ()))))
    console.print(table)

    candidates = getattr(resolution, "candidates", ())
    if candidates:
        candidate_table = Table(title="Candidates")
        candidate_table.add_column("State", no_wrap=True)
        candidate_table.add_column("Provider", no_wrap=True)
        candidate_table.add_column("Label", overflow="fold")
        candidate_table.add_column("Path/Command", overflow="fold")
        for candidate in candidates:
            command = getattr(candidate, "command", None) or getattr(candidate, "path", None) or ""
            candidate_table.add_row(
                escape(candidate.state.value),
                escape(candidate.provider),
                escape(candidate.label),
                escape(str(command)),
            )
        console.print(candidate_table)

    diagnostics = getattr(resolution, "diagnostics", ())
    if diagnostics:
        console.print("[bold]Diagnostics[/]")
        for item in diagnostics:
            console.print(f"- {escape(str(item))}")
    suggestions = getattr(resolution, "suggestions", ())
    if suggestions:
        console.print("[bold]Suggestions[/]")
        for item in suggestions:
            console.print(f"- {escape(str(item))}")


def _print_canvas_document(document: object) -> None:
    title = getattr(document, "name", "")
    canvas_id = getattr(document, "id", "")
    table = Table(title=f"Canvas: {escape(str(title))} ({escape(str(canvas_id))})")
    table.add_column("ID", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Geometry", no_wrap=True)
    table.add_column("Binding", overflow="fold")
    for component in getattr(document, "components", ()):
        binding = getattr(component, "binding", None)
        table.add_row(
            escape(str(getattr(component, "id", ""))),
            escape(str(getattr(component, "type", ""))),
            escape(
                f"{getattr(component, 'x', 0):g},"
                f"{getattr(component, 'y', 0):g} "
                f"{getattr(component, 'width', 0):g}x"
                f"{getattr(component, 'height', 0):g} "
                f"z={getattr(component, 'z', 0)}"
            ),
            escape(_canvas_binding_label(binding)),
        )
    console.print(table)


def _print_canvas_validation(validation: object) -> None:
    data = validation if isinstance(validation, dict) else validation.to_dict()
    status = "valid" if data.get("valid") else "invalid"
    style = "green" if data.get("valid") else "red"
    console.print(
        f"[bold]Validation:[/] [{style}]{escape(status)}[/] "
        f"({int(data.get('component_count') or 0)} components)"
    )
    for message in data.get("errors", []):
        console.print(f"[red]error[/] {escape(str(message))}")
    for message in data.get("warnings", []):
        console.print(f"[yellow]warning[/] {escape(str(message))}")


def _print_theme_document(payload: dict[str, object]) -> None:
    theme = payload.get("theme", {})
    if not isinstance(theme, dict):
        theme = {}
    validation = payload.get("validation", {})
    title = str(theme.get("name") or "")
    theme_id = str(theme.get("id") or "")
    table = Table(title=f"Theme: {escape(title)} ({escape(theme_id)})")
    table.add_column("Token", no_wrap=True)
    table.add_column("Value", overflow="fold")
    tokens = theme.get("tokens", {})
    for name, value in sorted(tokens.items()) if isinstance(tokens, dict) else []:
        table.add_row(escape(str(name)), escape(str(value)))
    console.print(table)
    _print_theme_validation(validation)


def _print_theme_validation(validation: object) -> None:
    data = validation if isinstance(validation, dict) else validation.to_dict()
    status = "valid" if data.get("valid") else "invalid"
    style = "green" if data.get("valid") else "red"
    console.print(
        f"[bold]Theme validation:[/] [{style}]{escape(status)}[/] "
        f"({int(data.get('token_count') or 0)} tokens, "
        f"{int(data.get('asset_count') or 0)} assets)"
    )
    for message in data.get("errors", []):
        console.print(f"[red]error[/] {escape(str(message))}")
    for message in data.get("warnings", []):
        console.print(f"[yellow]warning[/] {escape(str(message))}")


def _print_canvas_runtime_model(model: dict[str, object]) -> None:
    table = Table(title=f"Canvas Runtime: {escape(str(model.get('canvas_id', '')))}")
    table.add_column("Component")
    table.add_column("Type")
    table.add_column("State")
    table.add_column("Actions")
    table.add_column("Message")
    for component in model.get("components", []):
        if not isinstance(component, dict):
            continue
        table.add_row(
            escape(str(component.get("component_id", ""))),
            escape(str(component.get("component_type", ""))),
            escape(str(component.get("state", ""))),
            escape(", ".join(str(item) for item in component.get("enabled_actions", []))),
            escape(str(component.get("message", ""))),
        )
    console.print(table)
    warnings = model.get("unresolved_binding_warnings", [])
    for warning in warnings if isinstance(warnings, list) else []:
        console.print(f"[yellow]warning[/] {escape(str(warning))}")


def _canvas_binding_label(binding: object | None) -> str:
    if binding is None:
        return ""
    kind = getattr(binding, "kind", "")
    reference = getattr(binding, "reference", "")
    return f"{kind}: {reference}" if reference else str(kind)


@target_app.command("discover")
def target_discover(
    target: Annotated[str, typer.Argument(help="Target id or alias, such as diablo_iv.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable target resolution."),
    ] = False,
) -> None:
    """Discover local ways a catalog target can be started without mutating state."""
    try:
        resolution = resolve_target(target)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=resolution.to_dict())
        return
    _print_target_resolution(resolution)


@target_app.command("plan")
def target_plan(
    target: Annotated[str, typer.Argument(help="Target id or alias, such as diablo_iv.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable target plan."),
    ] = False,
) -> None:
    """Compile a target start request into a side-effect-free primitive plan preview."""
    try:
        resolution = resolve_target(target)
        plan = compile_target_start_plan(target, resolution=resolution)
        doctor = build_plan_doctor_report(plan)
    except (RitualistError, ValueError) as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=target_plan_payload(resolution, plan, doctor))
        return
    _print_target_resolution(resolution)
    _print_plan_preview(plan, doctor)
    if doctor.compatibility == "incompatible":
        raise typer.Exit(1)


@room_app.command("list")
def room_list(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable starter Room list."),
    ] = False,
) -> None:
    """List starter Rooms backed by bundled Canvas templates."""
    payload = room_list_payload()
    if json_output:
        console.print_json(data=payload)
        return
    table = Table(title="Ritualist Rooms")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Canvas")
    table.add_column("Category")
    for row in payload["rooms"]:
        table.add_row(
            escape(str(row["id"])),
            escape(str(row["name"])),
            escape(str(row["canvas_id"])),
            escape(str(row["category"])),
        )
    console.print(table)


@room_app.command("show")
def room_show(
    room: Annotated[str, typer.Argument(help="Room id, e.g. gaming, project, or support_desk.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable Room template."),
    ] = False,
) -> None:
    """Show a starter Room without executing Canvas bindings."""
    try:
        payload = room_show_payload(room)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=payload)
        return
    console.print(f"Room: {escape(str(payload['room']['name']))}")
    console.print(f"Canvas: {escape(str(payload['room']['canvas_id']))}")
    _print_canvas_document(load_bundled_canvas(str(payload["room"]["canvas_id"])))
    _print_canvas_validation(payload["validation"])


@canvas_app.command("list")
def canvas_list(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable canvas list."),
    ] = False,
) -> None:
    """List user and bundled Canvas documents."""
    rows = list_canvases()
    if json_output:
        console.print_json(data=[row.to_dict() for row in rows])
        return
    table = Table(title="Ritualist Canvases")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Source")
    table.add_column("Path")
    for row in rows:
        table.add_row(
            escape(row.canvas_id),
            escape(row.name),
            escape(row.source),
            escape(str(row.path)),
        )
    console.print(table)
    if not rows:
        console.print("No canvases found. Run [bold]ritualist canvas init[/] first.")


@canvas_app.command("show")
def canvas_show(
    canvas: Annotated[str, typer.Argument(help="Canvas id or YAML path.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable canvas document."),
    ] = False,
) -> None:
    """Show a Canvas document without executing bindings."""
    try:
        document = load_canvas(canvas)
        payload = canvas_show_payload(document)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=payload)
        return
    _print_canvas_document(document)
    _print_canvas_validation(payload["validation"])


@canvas_app.command("validate")
def canvas_validate(
    canvas: Annotated[str, typer.Argument(help="Canvas id or YAML path.")],
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Treat validation warnings as errors."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable validation result."),
    ] = False,
) -> None:
    """Validate a Canvas document without executing actions or bindings."""
    try:
        result = validate_canvas(canvas, strict=strict)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=result.to_dict())
        if not result.valid:
            raise typer.Exit(1)
        return
    _print_canvas_validation(result.to_dict())
    if not result.valid:
        raise typer.Exit(1)


@canvas_app.command("init")
def canvas_init() -> None:
    """Create default user Canvas documents without overwriting existing files."""
    results = create_default_canvases()
    table = Table(title="Canvas Initialization")
    table.add_column("ID")
    table.add_column("Status")
    table.add_column("Path")
    for result in results:
        table.add_row(
            escape(result.canvas_id),
            "[green]created[/]" if result.changed else "[dim]exists[/]",
            escape(str(result.path)),
        )
    console.print(table)
    if not any(result.changed for result in results):
        console.print("Canvas initialization is already up to date.")


@canvas_app.command("create-default")
def canvas_create_default(
    output: Annotated[
        Path,
        typer.Option("--out", help="Output path for the generated Canvas YAML."),
    ],
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Overwrite an existing output file."),
    ] = False,
) -> None:
    """Write the bundled default Gaming Desktop canvas to a chosen path."""
    try:
        result = save_canvas(default_canvas_document(), output, overwrite=overwrite)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if not result.changed:
        console.print(f"[yellow]Skipped:[/] {escape(result.message)} at {escape(str(result.path))}")
        raise typer.Exit(1)
    console.print(f"[green]Created canvas[/] {escape(result.canvas_id)} at {escape(str(result.path))}")


@canvas_app.command("preview")
def canvas_preview(
    canvas: Annotated[
        str | None,
        typer.Argument(help="Canvas id or YAML path. Omit with --mock."),
    ] = None,
    mock: Annotated[
        bool,
        typer.Option("--mock", help="Preview a generated mock Canvas document."),
    ] = False,
    mock_components: Annotated[
        int,
        typer.Option("--mock-components", min=1, help="Mock component count."),
    ] = 24,
) -> None:
    """Text preview of Canvas components without executing bindings."""
    try:
        document = create_mock_canvas(mock_components) if mock else load_canvas(canvas or "")
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    _print_canvas_document(document)


@canvas_app.command("edit-model")
def canvas_edit_model(
    canvas: Annotated[str, typer.Argument(help="Canvas id or YAML path.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable Canvas Edit Mode model."),
    ] = False,
) -> None:
    """Build the side-effect-free Canvas Edit Mode model."""
    try:
        session = create_edit_session(canvas)
        payload = session.to_dict()
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=payload)
        return
    console.print(f"Canvas: {escape(str(payload['canvas']['id']))}")
    console.print(f"Source: {escape(str(payload['source']))}")
    console.print(f"Dirty: {escape(str(payload['dirty']))}")
    console.print(f"Palette entries: {len(payload['palette'])}")
    _print_canvas_validation(payload["validation"])


@canvas_app.command("edit-plan")
def canvas_edit_plan(
    canvas: Annotated[str, typer.Argument(help="Canvas id or YAML path.")],
    mock_change: Annotated[
        str,
        typer.Option(
            "--mock-change",
            help="In-memory change to plan: noop, move, resize, property, binding, create, duplicate, delete.",
        ),
    ] = "noop",
    component: Annotated[str, typer.Option("--component", help="Component id to edit.")] = "",
    x: Annotated[float | None, typer.Option("--x", help="Planned x position.")] = None,
    y: Annotated[float | None, typer.Option("--y", help="Planned y position.")] = None,
    width: Annotated[float | None, typer.Option("--width", help="Planned width.")] = None,
    height: Annotated[float | None, typer.Option("--height", help="Planned height.")] = None,
    prop: Annotated[
        str,
        typer.Option(
            "--prop",
            help="Safe component property name, or component type for --mock-change create.",
        ),
    ] = "",
    value: Annotated[str | None, typer.Option("--value", help="Safe component property value.")] = None,
    binding_kind: Annotated[str, typer.Option("--binding-kind", help="Binding kind to review/edit.")] = "",
    binding_reference: Annotated[str, typer.Option("--binding-reference", help="Binding reference text.")] = "",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable Canvas Edit Mode plan."),
    ] = False,
) -> None:
    """Plan a constrained Canvas edit without saving or executing bindings."""
    try:
        payload = build_edit_plan(
            canvas,
            mock_change=mock_change,
            component_id=component,
            x=x,
            y=y,
            width=width,
            height=height,
            prop=prop,
            value=value,
            binding_kind=binding_kind,
            binding_reference=binding_reference,
        )
    except (RitualistError, ValueError) as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=payload)
        return
    console.print(f"Canvas: {escape(str(payload['edit_model']['canvas']['id']))}")
    console.print(f"Mock change: {escape(str(payload['mock_change']))}")
    console.print(f"Saved: {escape(str(payload['saved']))}")
    console.print(f"Side effects: {escape(str(payload['side_effects']))}")
    _print_canvas_validation(payload["after_validation"])


@canvas_app.command("runtime")
def canvas_runtime(
    canvas: Annotated[str, typer.Argument(help="Canvas id or YAML path.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable Canvas runtime model."),
    ] = False,
) -> None:
    """Build a Canvas runtime model without executing component actions."""
    try:
        document = load_canvas(canvas)
        model = build_canvas_runtime_model(
            document,
            context=CanvasRuntimeContext(resolve_targets=True),
        )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=model.to_dict())
        return
    _print_canvas_runtime_model(model.to_dict())


@canvas_app.command("action")
def canvas_action(
    canvas: Annotated[str, typer.Argument(help="Canvas id or YAML path.")],
    component_id: Annotated[str, typer.Argument(help="Canvas component id.")],
    action_id: Annotated[str, typer.Argument(help="Supported Canvas action id.")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate dispatch without executing the action."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable action result."),
    ] = False,
) -> None:
    """Dispatch an explicit Canvas component action through existing safe services."""
    try:
        result = dispatch_canvas_action(
            canvas,
            component_id,
            action_id,
            dry_run=dry_run,
            controller=CanvasRuntimeController(),
        )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=result.to_dict())
        return
    console.print(f"{escape(result.component_id)}:{escape(result.action_id)} {escape(result.status)}")
    if result.message:
        console.print(escape(result.message))


@canvas_app.command("use")
def canvas_use(
    canvas: Annotated[
        str | None,
        typer.Argument(help="Canvas id or YAML path. Omit with --mock."),
    ] = None,
    mock: Annotated[
        bool,
        typer.Option("--mock", help="Launch Canvas Use Mode with generated mock components."),
    ] = False,
    mock_components: Annotated[
        int,
        typer.Option("--mock-components", min=1, help="Generated component count for --mock."),
    ] = 24,
    host: Annotated[
        str,
        typer.Option(
            "--host",
            help=(
                "Canvas host mode. Use 'desktop-work-area' for an opt-in "
                "work-area-sized desktop Canvas."
            ),
        ),
    ] = "windowed",
    taskbar_policy: Annotated[
        str,
        typer.Option(
            "--taskbar-policy",
            help="Taskbar policy for desktop hosts. Only 'respect' is currently implemented.",
        ),
    ] = "respect",
) -> None:
    """Launch Canvas Use Mode with the bundled typed renderer."""
    try:
        host_config = resolve_canvas_host_config(host, taskbar_policy=taskbar_policy)
        from ritualist.canvas.app import run_canvas_use

        run_canvas_use(
            default_canvas_for_host(canvas, host_config),
            mock=mock,
            mock_components=mock_components,
            host_config=host_config,
        )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc


@canvas_pack_app.command("export")
def canvas_pack_export(
    canvas: Annotated[str, typer.Argument(help="Canvas id or YAML path.")],
    out: Annotated[
        Path,
        typer.Option("--out", help="Output .ritualistcanvas archive path."),
    ],
    readme: Annotated[
        Path | None,
        typer.Option("--readme", help="Optional UTF-8 README file to include as README.md."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable export result."),
    ] = False,
) -> None:
    """Export a visual Canvas pack without recipes or execution state."""
    try:
        result = export_canvas_pack(canvas, out, readme_path=readme)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    _print_visual_pack_result(result, json_output=json_output)


@canvas_pack_app.command("import")
def canvas_pack_import(
    pack: Annotated[Path, typer.Argument(help="Path to a .ritualistcanvas archive.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable import record."),
    ] = False,
) -> None:
    """Import a local Canvas pack into disabled quarantine storage."""
    try:
        record = import_canvas_pack(pack)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    _print_visual_pack_import(record, json_output=json_output)


@canvas_theme_app.command("export")
def canvas_theme_export(
    theme: Annotated[str, typer.Argument(help="Theme id or YAML path; use 'default' for the built-in theme.")],
    out: Annotated[
        Path,
        typer.Option("--out", help="Output .ritualisttheme archive path."),
    ],
    readme: Annotated[
        Path | None,
        typer.Option("--readme", help="Optional UTF-8 README file to include as README.md."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable export result."),
    ] = False,
) -> None:
    """Export a visual theme pack; themes cannot contain actions or recipes."""
    try:
        result = export_theme_pack(theme, out, readme_path=readme)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    _print_visual_pack_result(result, json_output=json_output)


@canvas_theme_app.command("import")
def canvas_theme_import(
    pack: Annotated[Path, typer.Argument(help="Path to a .ritualisttheme archive.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable import record."),
    ] = False,
) -> None:
    """Import a local theme pack into disabled quarantine storage."""
    try:
        record = import_theme_pack(pack)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    _print_visual_pack_import(record, json_output=json_output)


@suite_app.command("export")
def suite_pack_export(
    canvas_pack: Annotated[
        Path,
        typer.Option("--canvas-pack", help="Nested .ritualistcanvas Room pack to include."),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", help="Output .ritualistsuite archive path."),
    ],
    suite_id: Annotated[
        str | None,
        typer.Option("--id", help="Optional safe suite id; defaults from the Canvas pack."),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", help="Optional suite display name."),
    ] = None,
    theme_pack: Annotated[
        Path | None,
        typer.Option("--theme-pack", help="Optional nested .ritualisttheme pack to include."),
    ] = None,
    ritual_pack: Annotated[
        list[Path] | None,
        typer.Option("--ritual-pack", help="Optional behavior-bearing .ritualistpack to include."),
    ] = None,
    readme: Annotated[
        Path | None,
        typer.Option("--readme", help="Optional UTF-8 README file to include as README.md."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable export result."),
    ] = False,
) -> None:
    """Export a suite wrapper around already validated nested packs."""
    try:
        result = export_suite_pack(
            canvas_pack=canvas_pack,
            theme_pack=theme_pack,
            ritual_packs=tuple(ritual_pack or ()),
            out=out,
            suite_id=suite_id,
            name=name,
            readme_path=readme,
        )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    _print_suite_pack_result(result, json_output=json_output)


@suite_app.command("validate")
def suite_pack_validate(
    suite: Annotated[Path, typer.Argument(help="Path to a .ritualistsuite archive.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable validation result."),
    ] = False,
) -> None:
    """Validate a suite and every nested pack without importing or enabling anything."""
    try:
        result = validate_suite_pack(suite)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    payload = result.to_dict()
    if json_output:
        console.print_json(data=payload)
        return
    console.print(f"[green]Suite pack is valid:[/] {escape(str(result.path))}")
    _print_suite_pack_summary(payload)


@suite_app.command("import")
def suite_pack_import(
    suite: Annotated[Path, typer.Argument(help="Path to a .ritualistsuite archive.")],
    visuals_only: Annotated[
        bool,
        typer.Option(
            "--visuals-only",
            help="Import only Canvas/theme packs and skip behavior-bearing ritual packs.",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable import record."),
    ] = False,
) -> None:
    """Import a suite into quarantine without enabling or running nested behavior."""
    try:
        record = import_suite_pack(suite, include_rituals=not visuals_only)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    _print_suite_pack_import(record, json_output=json_output)


@suite_app.command("list-imports")
def suite_pack_list_imports(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable suite import records."),
    ] = False,
) -> None:
    """List quarantined suite imports."""
    try:
        records = list_suite_imports()
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=[record.to_dict() for record in records])
        return
    table = Table(title="Imported Suite Packs")
    table.add_column("Import ID")
    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Status")
    table.add_column("Ritual Packs")
    table.add_column("Path")
    for record in records:
        table.add_row(
            escape(record.import_id),
            escape(record.name),
            escape(record.version),
            escape(record.status),
            escape(str(len(record.ritual_imports))),
            escape(str(record.root)),
        )
    console.print(table)
    if not records:
        console.print("No imported suite packs found.")


@theme_app.command("list")
def theme_list(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable theme list."),
    ] = False,
) -> None:
    """List bundled and user themes without loading executable code."""
    rows = list_themes()
    if json_output:
        console.print_json(data=[row.to_dict() for row in rows])
        return
    table = Table(title="Ritualist Themes")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Source")
    table.add_column("Path")
    for row in rows:
        table.add_row(
            escape(row.theme_id),
            escape(row.name),
            escape(row.source),
            escape(str(row.path)),
        )
    console.print(table)
    if not rows:
        console.print("No themes found.")


@theme_app.command("show")
def theme_show(
    theme: Annotated[str, typer.Argument(help="Theme id or theme.yaml path.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable theme document."),
    ] = False,
) -> None:
    """Show a safe declarative theme without executing behavior."""
    try:
        document = load_theme(theme)
        payload = theme_show_payload(document)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=payload)
        return
    _print_theme_document(payload)


@theme_app.command("validate")
def theme_validate(
    theme: Annotated[str, typer.Argument(help="Theme id or theme.yaml path.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable validation result."),
    ] = False,
) -> None:
    """Validate a theme as data-only visual tokens."""
    try:
        result = validate_theme(theme)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=result.to_dict())
        if not result.valid:
            raise typer.Exit(1)
        return
    _print_theme_validation(result.to_dict())
    if not result.valid:
        raise typer.Exit(1)


@diagnostics_app.command("collect")
def diagnostics_collect(
    preset: Annotated[
        str,
        typer.Option("--preset", help="Diagnostics preset: minimal, support, or gamer-crash."),
    ] = "minimal",
    output_dir: Annotated[
        Path | None,
        typer.Option("--out", help="Optional output directory for diagnostics artifacts."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Describe collection without writing artifacts."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable execution result."),
    ] = False,
) -> None:
    """Collect a redacted local diagnostics bundle."""
    preset_map = {
        "minimal": "diagnostics.bundle.collect_minimal",
        "support": "diagnostics.bundle.collect_support",
        "gamer-crash": "diagnostics.bundle.collect_gamer_crash",
        "gamer_crash": "diagnostics.bundle.collect_gamer_crash",
    }
    primitive_id = preset_map.get(preset.casefold())
    if primitive_id is None:
        console.print("[red]Error:[/] preset must be minimal, support, or gamer-crash")
        raise typer.Exit(1)
    parameters: dict[str, object] = {}
    if output_dir is not None:
        parameters["output_dir"] = str(output_dir)
    try:
        result = run_read_only_primitive(
            primitive_id,
            parameters=parameters,
            dry_run=dry_run,
        )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=result.to_dict())
        return
    _print_primitive_result(result)
    if result.status == "failed":
        raise typer.Exit(1)


@plan_app.command("preview")
def plan_preview(
    target: Annotated[
        str,
        typer.Argument(help="Intent kind/spec path, recipe id, or recipe YAML path."),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable plan preview."),
    ] = False,
) -> None:
    """Compile an intent or recipe into a side-effect-free primitive plan preview."""
    try:
        plan = compile_plan_reference(target)
        doctor = build_plan_doctor_report(plan)
    except (RitualistError, ValueError) as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=plan_preview_payload(plan, doctor))
        return
    _print_plan_preview(plan, doctor)
    if doctor.compatibility == "incompatible":
        raise typer.Exit(1)


@policy_app.command("show")
def policy_show(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable policy metadata."),
    ] = False,
) -> None:
    """Show local primitive policy categories, decisions, and profiles."""
    overview = policy_overview()
    if json_output:
        console.print_json(data=overview)
        return

    table = Table(title="Primitive Policy")
    table.add_column("Name", no_wrap=True)
    table.add_column("Value", overflow="fold")
    table.add_row("schema", escape(str(overview["schema_version"])))
    table.add_row("default_profile", escape(str(overview["default_profile"])))
    table.add_row("categories", escape(", ".join(overview["categories"])))  # type: ignore[arg-type]
    table.add_row("decisions", escape(", ".join(overview["decisions"])))  # type: ignore[arg-type]
    console.print(table)

    profile_table = Table(title="Policy Profiles")
    profile_table.add_column("Profile", no_wrap=True)
    profile_table.add_column("Description", overflow="fold")
    profiles = overview.get("profiles", {})
    if isinstance(profiles, dict):
        for name, description in profiles.items():
            profile_table.add_row(escape(str(name)), escape(str(description)))
    console.print(profile_table)


@policy_app.command("check")
def policy_check(
    target: Annotated[str, typer.Argument(help="Recipe id/path, imported pack dir, or .ritualistpack.")],
    profile: Annotated[
        str,
        typer.Option("--profile", help="Local policy profile to evaluate."),
    ] = PolicyProfile.CONSUMER_SAFE.value,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable policy report."),
    ] = False,
) -> None:
    """Evaluate primitive policy for a local recipe or recipe pack without running it."""
    try:
        report = _build_policy_report_for_target(target, profile=profile)
    except (RitualistError, ValueError) as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=report.to_dict())
    else:
        _print_policy_report(report)
    if not report.allowed:
        raise typer.Exit(1)


@policy_app.command("explain")
def policy_explain(
    primitive_id: Annotated[str, typer.Argument(help="Primitive id such as browser.session.open.")],
    profile: Annotated[
        str,
        typer.Option("--profile", help="Local policy profile to evaluate."),
    ] = PolicyProfile.CONSUMER_SAFE.value,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable policy finding."),
    ] = False,
) -> None:
    """Explain one primitive's imported-pack policy decision."""
    try:
        finding = explain_primitive_policy(primitive_id, profile=profile)
    except (KeyError, ValueError) as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if json_output:
        console.print_json(data=finding.to_dict())
        return
    _print_policy_finding(finding)


@pack_app.command("export")
def pack_export(
    recipe: Annotated[str, typer.Argument(help="Recipe id or YAML path.")],
    out: Annotated[
        Path,
        typer.Option("--out", help="Output .ritualistpack archive path."),
    ],
    readme: Annotated[
        Path | None,
        typer.Option("--readme", help="Optional UTF-8 README file to include as README.md."),
    ] = None,
) -> None:
    """Export a recipe into a portable .ritualistpack zip."""
    try:
        result = export_recipe_pack(recipe, out, readme_path=readme)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    console.print(f"[green]Exported pack:[/] {escape(str(result.output_path))}")
    console.print(f"recipe: {escape(result.recipe_id)}")
    console.print("contents:")
    for entry in result.entries:
        console.print(f"- {escape(entry)}")


@pack_app.command("import")
def pack_import(
    pack: Annotated[str, typer.Argument(help="Path to a .ritualistpack archive.")],
) -> None:
    """Import a local recipe pack into disabled quarantine storage."""
    try:
        record = import_recipe_pack(pack)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    console.print(
        f"[green]Imported pack {escape(record.import_id)} into quarantine; it is disabled.[/]"
    )
    _print_import_record(record)
    console.print("Review and configure the quarantined recipe, then run Doctor/dry-run:")
    for recipe in record.recipes:
        path = record.root / recipe.path
        console.print(f"- ritualist doctor {escape(str(path))}")
        console.print(f"- ritualist dry-run {escape(str(path))}")
    console.print(f"Enable after review with: ritualist pack enable {escape(record.import_id)}")


@pack_app.command("list-imports")
def pack_list_imports() -> None:
    """List packs currently stored in import quarantine."""
    try:
        records = list_pack_imports()
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    table = Table(title="Imported Packs")
    table.add_column("Import ID")
    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Status")
    table.add_column("Recipes")
    table.add_column("Path")
    for record in records:
        table.add_row(
            escape(record.import_id),
            escape(record.name),
            escape(record.version),
            escape(record.status),
            ", ".join(escape(recipe.recipe_id) for recipe in record.recipes),
            escape(str(record.root)),
        )
    console.print(table)
    if not records:
        console.print("No imported packs found.")


@pack_app.command("enable")
def pack_enable(
    import_id: Annotated[str, typer.Argument(help="Import id from 'ritualist pack list-imports'.")],
) -> None:
    """Validate a quarantined pack and copy its recipe into enabled recipes."""
    try:
        record = enable_import(import_id)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    console.print(f"[green]Enabled imported pack {escape(record.import_id)}.[/]")
    _print_import_record(record)
    console.print("No recipe was run.")


@perf_app.command("doctor")
def perf_doctor(
    recipe: Annotated[str, typer.Argument(help="Recipe id or YAML path.")],
    var_values: Annotated[
        list[str] | None,
        typer.Option("--var", "-v", help="Template override in KEY=VALUE form."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable performance data."),
    ] = False,
) -> None:
    """Measure recipe doctor report construction."""
    try:
        with measure_operation("perf.doctor") as report:
            parsed, _raw, missing_variables = load_recipe_for_diagnostics(
                recipe,
                _parse_vars(var_values or []),
            )
            doctor_report = build_doctor_report(parsed, missing_variables=missing_variables)
            report.counts.update(
                {
                    "checks": len(doctor_report.checks),
                    "errors": doctor_report.errors_count,
                    "warnings": doctor_report.warnings_count,
                    "actions": len(doctor_report.action_metadata),
                    "execution_steps": len(parsed.execution_steps),
                    "missing_variables": len(missing_variables),
                }
            )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    payload = _performance_payload(
        report,
        recipe_id=doctor_report.recipe_id,
        recipe_name=doctor_report.recipe_name,
        compatibility=doctor_report.compatibility,
        compatibility_score=doctor_report.compatibility_score,
    )
    if json_output:
        console.print_json(data=payload)
        return

    _print_performance_report(report)
    console.print(
        "compatibility: "
        f"{escape(doctor_report.compatibility)} ({doctor_report.compatibility_score})"
    )
    console.print(f"recipe: {escape(doctor_report.recipe_name)} ({escape(doctor_report.recipe_id)})")


@perf_app.command("list-runs")
def perf_list_runs(
    limit: Annotated[int, typer.Option("--limit", min=1, help="Maximum runs to load.")] = 20,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable performance data."),
    ] = False,
) -> None:
    """Measure recent run metadata loading."""
    with measure_operation("perf.list-runs") as report:
        records = list_recent_runs(limit=limit)
        status_counts = Counter(str(record.metadata.get("status", "")) for record in records)
        report.counts.update(
            {
                "runs": len(records),
                "steps": sum(len(record.steps) for record in records),
                **{
                    f"status_{status or 'unknown'}": count
                    for status, count in sorted(status_counts.items())
                },
            }
        )

    payload = _performance_payload(
        report,
        runs=[
            {
                "run_id": record.run_id,
                "recipe_id": record.metadata.get("recipe_id"),
                "status": record.metadata.get("status"),
                "steps": len(record.steps),
            }
            for record in records
        ],
    )
    if json_output:
        console.print_json(data=payload)
        return

    _print_performance_report(report)
    if records:
        console.print("[bold]Loaded runs[/]")
        for record in records:
            console.print(
                "- "
                f"{escape(record.run_id)} | "
                f"{escape(str(record.metadata.get('recipe_id', '')))} | "
                f"{escape(str(record.metadata.get('status', '')))} | "
                f"{len(record.steps)} steps"
            )
    else:
        console.print("No runs found.")


@perf_app.command("load-recipes")
def perf_load_recipes(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable performance data."),
    ] = False,
) -> None:
    """Measure installed recipe discovery and validation."""
    with measure_operation("perf.load-recipes") as report:
        rows = discover_recipes()
        valid_recipes = [recipe for _path, recipe, _error in rows if recipe is not None]
        invalid_count = len(rows) - len(valid_recipes)
        report.counts.update(
            {
                "recipes": len(rows),
                "valid": len(valid_recipes),
                "invalid": invalid_count,
                "execution_steps": sum(len(recipe.execution_steps) for recipe in valid_recipes),
            }
        )

    payload = _performance_payload(
        report,
        recipes=[
            {
                "path": str(path),
                "recipe_id": recipe.id if recipe is not None else path.stem,
                "status": "valid" if recipe is not None else "invalid",
                "execution_steps": len(recipe.execution_steps) if recipe is not None else 0,
                "error": error,
            }
            for path, recipe, error in rows
        ],
    )
    if json_output:
        console.print_json(data=payload)
        return

    _print_performance_report(report)
    if rows:
        console.print("[bold]Loaded recipes[/]")
        for path, recipe, error in rows:
            if recipe is None:
                console.print(f"- {escape(path.stem)} | invalid | {escape(error or '')}")
            else:
                console.print(
                    f"- {escape(recipe.id)} | valid | {len(recipe.execution_steps)} steps"
                )
    else:
        console.print("No recipes found. Run [bold]ritualist init[/] first.")


@perf_app.command("home-model")
def perf_home_model(
    mock_cards: Annotated[
        int,
        typer.Option("--mock-cards", min=1, help="Number of generated Home cards to model."),
    ] = 120,
    budget_ms: Annotated[
        float,
        typer.Option("--budget-ms", help="Advisory duration budget in milliseconds."),
    ] = 250.0,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable performance data."),
    ] = False,
) -> None:
    """Measure Home model generation with generated cards and no GUI side effects."""
    with measure_operation("perf.home-model") as report:
        from ritualist.home.models import create_mock_home_model

        model = create_mock_home_model(count=mock_cards)
        qml_payload = model.to_qml()
        cards = qml_payload.get("cards")
        categories = qml_payload.get("categories")
        report.counts.update(
            {
                "cards": len(model.cards),
                "categories": len(model.categories),
                "qml_cards": len(cards) if isinstance(cards, list) else 0,
                "qml_categories": len(categories) if isinstance(categories, list) else 0,
                "thumbnail_cache_items": 0,
            }
        )

    if budget_ms > 0 and report.duration_ms > budget_ms:
        report.warnings.append(
            f"Home model generation exceeded advisory budget: "
            f"{report.duration_ms:.3f} ms > {budget_ms:.3f} ms"
        )

    payload = _performance_payload(
        report,
        advisory_budget_ms=budget_ms,
        thumbnail_cache_work="not_applicable_for_mock_cards",
    )
    if json_output:
        console.print_json(data=payload)
        return

    _print_performance_report(report)
    console.print(f"advisory_budget_ms: {budget_ms:.3f}")
    console.print("thumbnail_cache_work: not_applicable_for_mock_cards")


@perf_app.command("canvas-model")
def perf_canvas_model(
    mock_components: Annotated[
        int,
        typer.Option("--mock-components", min=1, help="Number of generated Canvas components to model."),
    ] = 120,
    budget_ms: Annotated[
        float,
        typer.Option("--budget-ms", help="Advisory duration budget in milliseconds."),
    ] = 250.0,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable performance data."),
    ] = False,
) -> None:
    """Measure Canvas model generation and validation with no adapter side effects."""
    validation_duration_ms = 0.0
    with measure_operation("perf.canvas-model") as report:
        document = create_mock_canvas(mock_components)
        validation_started = time.perf_counter()
        validation = validate_canvas_structure(document)
        validation_duration_ms = max(0.0, (time.perf_counter() - validation_started) * 1000)
        type_count = len({component.type for component in document.components})
        report.counts.update(
            {
                "components": len(document.components),
                "component_types": type_count,
                "warnings": len(validation.warnings),
                "errors": len(validation.errors),
            }
        )

    if budget_ms > 0 and report.duration_ms > budget_ms:
        report.warnings.append(
            f"Canvas model generation exceeded advisory budget: "
            f"{report.duration_ms:.3f} ms > {budget_ms:.3f} ms"
        )

    payload = _performance_payload(
        report,
        advisory_budget_ms=budget_ms,
        validation_duration_ms=validation_duration_ms,
        canvas_id=document.id,
        validation=validation.to_dict(),
        side_effects="none",
    )
    if json_output:
        console.print_json(data=payload)
        return

    _print_performance_report(report)
    console.print(f"advisory_budget_ms: {budget_ms:.3f}")
    console.print(f"validation_duration_ms: {validation_duration_ms:.3f}")
    console.print("side_effects: none")


@perf_app.command("canvas-runtime")
def perf_canvas_runtime(
    mock_components: Annotated[
        int,
        typer.Option("--mock-components", min=1, help="Number of generated Canvas components to model."),
    ] = 120,
    budget_ms: Annotated[
        float,
        typer.Option("--budget-ms", help="Advisory duration budget in milliseconds."),
    ] = 250.0,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable performance data."),
    ] = False,
) -> None:
    """Measure Canvas runtime model generation with no adapter side effects."""
    runtime_duration_ms = 0.0
    with measure_operation("perf.canvas-runtime") as report:
        document = create_mock_canvas(mock_components)
        runtime_started = time.perf_counter()
        model = build_canvas_runtime_model(
            document,
            context=CanvasRuntimeContext(
                recipe_ids={"gaming_mode"},
                target_ids={"diablo_iv"},
                recent_runs=(),
                resolve_targets=False,
            ),
        )
        runtime_duration_ms = max(0.0, (time.perf_counter() - runtime_started) * 1000)
        report.counts.update(
            {
                "components": len(model.component_states),
                "warnings": len(model.unresolved_binding_warnings),
                "recent_activity": len(model.recent_activity),
            }
        )

    if budget_ms > 0 and report.duration_ms > budget_ms:
        report.warnings.append(
            f"Canvas runtime generation exceeded advisory budget: "
            f"{report.duration_ms:.3f} ms > {budget_ms:.3f} ms"
        )

    payload = _performance_payload(
        report,
        advisory_budget_ms=budget_ms,
        runtime_state_build_duration_ms=runtime_duration_ms,
        canvas_id=document.id,
        runtime_summary={
            "schema_version": model.schema_version,
            "canvas_id": model.canvas_id,
            "component_count": len(model.component_states),
            "warnings_count": len(model.unresolved_binding_warnings),
            "recent_activity_count": len(model.recent_activity),
            "performance_counters": model.performance_counters,
        },
        side_effects="none",
    )
    if json_output:
        console.print_json(data=payload)
        return

    _print_performance_report(report)
    console.print(f"advisory_budget_ms: {budget_ms:.3f}")
    console.print(f"runtime_state_build_duration_ms: {runtime_duration_ms:.3f}")
    console.print("side_effects: none")


@perf_app.command("canvas-use")
def perf_canvas_use(
    mock_components: Annotated[
        int,
        typer.Option("--mock-components", min=1, help="Number of generated Canvas components to model."),
    ] = 120,
    budget_ms: Annotated[
        float,
        typer.Option("--budget-ms", help="Advisory duration budget in milliseconds."),
    ] = 250.0,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable performance data."),
    ] = False,
) -> None:
    """Measure Canvas Use view-model generation with no GUI or adapter side effects."""
    view_duration_ms = 0.0
    with measure_operation("perf.canvas-use") as report:
        document = create_mock_canvas(mock_components)
        view_started = time.perf_counter()
        model = build_canvas_view_model(
            document,
            context=CanvasRuntimeContext(
                recipe_ids={"gaming_mode"},
                target_ids={"diablo_iv"},
                recent_runs=(),
                resolve_targets=False,
            ),
        )
        view_duration_ms = max(0.0, (time.perf_counter() - view_started) * 1000)
        performance_budget = canvas_performance_diagnostics(document)
        report.counts.update(
            {
                "components": len(model.components),
                "warnings": len(model.runtime.unresolved_binding_warnings),
            }
        )

    if budget_ms > 0 and report.duration_ms > budget_ms:
        report.warnings.append(
            f"Canvas Use view-model generation exceeded advisory budget: "
            f"{report.duration_ms:.3f} ms > {budget_ms:.3f} ms"
        )

    payload = _performance_payload(
        report,
        advisory_budget_ms=budget_ms,
        view_model_build_duration_ms=view_duration_ms,
        canvas_id=document.id,
        view_summary={
            "schema_version": model.to_dict()["schema_version"],
            "canvas_id": model.canvas.id,
            "component_count": len(model.components),
            "warnings_count": len(model.runtime.unresolved_binding_warnings),
            "theme_id": model.runtime.theme.get("id", ""),
            "theme_validation": model.runtime.theme.get("validation", {}),
            "performance_budget": performance_budget,
        },
        side_effects="none",
    )
    if json_output:
        console.print_json(data=payload)
        return

    _print_performance_report(report)
    console.print(f"advisory_budget_ms: {budget_ms:.3f}")
    console.print(f"view_model_build_duration_ms: {view_duration_ms:.3f}")
    console.print(f"visual_estimated_cost: {performance_budget['estimated_cost']}")
    console.print(f"visual_warning_count: {performance_budget['warning_count']}")
    console.print("side_effects: none")


@perf_app.command("fake-run")
def perf_fake_run(
    recipe: Annotated[str, typer.Argument(help="Recipe id or YAML path.")],
    var_values: Annotated[
        list[str] | None,
        typer.Option("--var", "-v", help="Template override in KEY=VALUE form."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable performance data."),
    ] = False,
) -> None:
    """Measure a recipe run using fake adapters and no run log side effects."""
    confirmations = 0
    fakes = FakeAdapters()

    def confirm_fake(_request: object) -> bool:
        nonlocal confirmations
        confirmations += 1
        return True

    try:
        with measure_operation("perf.fake-run") as report:
            parsed = load_recipe_reference(recipe, _parse_vars(var_values or []))
            executor = WorkflowExecutor(
                registry=create_default_registry(),
                adapters=fakes.bundle(),
                dry_run=False,
                confirmer=confirm_fake,
                run_logger=None,
            )
            summary = executor.run(parsed)
            status_counts = Counter(result.status for result in summary.results)
            report.counts.update(
                {
                    "steps_total": len(parsed.execution_steps),
                    "steps_completed": len(summary.results),
                    "confirmations": confirmations,
                    "shell_calls": len(fakes.shell.calls),
                    "browser_calls": sum(1 for call in fakes.browser.calls if call[0] != "close"),
                    "window_calls": len(fakes.window.calls),
                    "desktop_calls": len(fakes.desktop.calls),
                    "input_calls": len(fakes.input.calls),
                    **{
                        f"status_{status}": count
                        for status, count in sorted(status_counts.items())
                    },
                }
            )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    payload = _performance_payload(
        report,
        recipe_id=summary.recipe_id,
        recipe_name=summary.recipe_name,
        success=summary.success,
        results=[
            {
                "index": result.index,
                "step_name": result.step_name,
                "action": result.action,
                "status": result.status,
            }
            for result in summary.results
        ],
    )
    if json_output:
        console.print_json(data=payload)
        return

    _print_performance_report(report)
    console.print(f"recipe: {escape(summary.recipe_name)} ({escape(summary.recipe_id)})")
    console.print(f"success: {'yes' if summary.success else 'no'}")


@app.command()
def runs(
    limit: Annotated[int, typer.Option("--limit", min=1, help="Maximum runs to list.")] = 10,
    repair: Annotated[
        bool,
        typer.Option("--repair/--no-repair", help="Repair stale running runs before listing."),
    ] = True,
) -> None:
    """List recent run directories and final statuses."""
    if repair:
        _print_reconciled_runs(reconcile_running_runs(limit=max(limit, 100)))
    records = list_recent_runs(limit=limit)
    if not records:
        console.print("No runs found.")
        return
    console.print("[bold]Recent runs[/]")
    for record in records:
        metadata = record.metadata
        console.print(
            "- "
            f"{escape(record.run_id)} | "
            f"{escape(str(metadata.get('recipe_id', '')))} | "
            f"{escape(str(metadata.get('status', '')))} | "
            f"{escape(str(metadata.get('started_at', '')))} | "
            f"{metadata.get('steps_completed', 0)}/{metadata.get('steps_total', 0)}"
        )
        console.print(f"  path: {escape(str(record.path))}")


@app.command("show-run")
def show_run(
    run_id_or_path: Annotated[str, typer.Argument(help="Run id from 'ritualist runs' or run path.")],
    repair: Annotated[
        bool,
        typer.Option("--repair/--no-repair", help="Repair stale running runs before showing."),
    ] = True,
) -> None:
    """Show a run summary and step results."""
    if repair:
        _print_reconciled_runs(reconcile_running_runs())
    record = load_run(run_id_or_path)
    if record is None:
        console.print(f"[red]Error:[/] run not found: {escape(run_id_or_path)}")
        raise typer.Exit(1)

    metadata = record.metadata
    table = Table(title=f"Run: {escape(record.run_id)}")
    table.add_column("Field")
    table.add_column("Value")
    for key in ("recipe_id", "recipe_name", "status", "dry_run", "started_at", "ended_at"):
        table.add_row(escape(key), escape(str(metadata.get(key, ""))))
    for key in (
        "current_run_state",
        "current_step_state",
        "final_state",
        "stopped_reason",
    ):
        if _metadata_has_value(metadata, key):
            table.add_row(escape(key), escape(str(metadata.get(key, ""))))
    if _metadata_has_value(metadata, "run_state_history"):
        table.add_row(
            "run_state_history",
            escape(_format_state_history(metadata.get("run_state_history"))),
        )
    if _metadata_has_value(metadata, "event_summaries"):
        table.add_row(
            "event_summaries",
            escape(_format_event_summaries(metadata.get("event_summaries"))),
        )
    for key in ("wait_metadata", "paused_metadata", "confirming_metadata"):
        if _metadata_has_value(metadata, key):
            table.add_row(escape(key), escape(_format_metadata_value(metadata.get(key))))
    if _metadata_has_value(metadata, "declined_target"):
        table.add_row("declined_target", escape(_format_metadata_value(metadata.get("declined_target"))))
    if _metadata_has_value(metadata, "ownership_ledger"):
        table.add_row(
            "ownership_ledger",
            escape(_format_ownership_ledger(metadata.get("ownership_ledger"))),
        )
    if _metadata_has_value(metadata, "cleanup_offer"):
        table.add_row("cleanup_offer", escape(_format_cleanup_offer(metadata.get("cleanup_offer"))))
    if _metadata_has_value(metadata, "cleanup_choice"):
        table.add_row("cleanup_choice", escape(_format_metadata_value(metadata.get("cleanup_choice"))))
    if _metadata_has_value(metadata, "remembered_cleanup_preference_applied"):
        table.add_row(
            "remembered_cleanup_preference_applied",
            escape(str(metadata.get("remembered_cleanup_preference_applied"))),
        )
    if _metadata_has_value(metadata, "remembered_approval_applied"):
        table.add_row(
            "remembered_approval_applied",
            escape(_format_metadata_value(metadata.get("remembered_approval_applied"))),
        )
    if metadata.get("final_message"):
        table.add_row("final_message", escape(str(metadata.get("final_message", ""))))
    table.add_row("path", escape(str(record.path)))
    console.print(table)

    _print_runbook_summary(summarize_run_record(record))
    _print_operator_notes(record.notes)

    steps = Table(title="Steps")
    steps.add_column("#", justify="right")
    steps.add_column("Status")
    steps.add_column("Step")
    steps.add_column("Action")
    steps.add_column("Message")
    steps.add_column("Details")
    for step in record.steps:
        steps.add_row(
            str(step.get("index", "")),
            escape(str(step.get("status", ""))),
            escape(str(step.get("step_name", ""))),
            escape(str(step.get("action", ""))),
            escape(str(step.get("message", ""))),
            escape(_format_step_run_details(step.get("metadata"))),
        )
    console.print(steps)
    _print_step_run_details(record.steps)


@app.command("note-run")
def note_run(
    run_id_or_path: Annotated[str, typer.Argument(help="Run id from 'ritualist runs' or run path.")],
    note: Annotated[str | None, typer.Argument(help="User-entered operator note text.")] = None,
    stdin: Annotated[
        bool,
        typer.Option("--stdin", help="Read the user-entered operator note from standard input."),
    ] = False,
) -> None:
    """Add a user-entered operator note to a run log."""
    if note is not None and stdin:
        console.print("[red]Error:[/] pass note text or --stdin, not both.")
        raise typer.Exit(1)
    note_text = sys.stdin.read() if stdin else note
    if note_text is None:
        note_text = typer.prompt("Operator note", default="", show_default=False)
    try:
        entry = append_operator_note(run_id_or_path, note_text)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    if entry is None:
        console.print(f"[red]Error:[/] run not found: {escape(run_id_or_path)}")
        raise typer.Exit(1)
    console.print(
        "[green]Added user-entered operator note[/] "
        f"at {escape(str(entry.get('at', '')))}."
    )


@app.command()
def validate(
    recipe: Annotated[str, typer.Argument(help="Recipe id or YAML path.")],
    var_values: Annotated[
        list[str] | None,
        typer.Option("--var", "-v", help="Template override in KEY=VALUE form."),
    ] = None,
) -> None:
    """Validate a recipe without running it."""
    try:
        parsed = load_recipe_reference(recipe, _parse_vars(var_values or []))
    except RitualistError as exc:
        console.print(f"[red]Invalid recipe:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    _print_steps(parsed)
    console.print("[green]Recipe is valid.[/]")


@app.command()
def run(
    recipe: Annotated[str, typer.Argument(help="Recipe id or YAML path.")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate and show planned actions."),
    ] = False,
    keep_alive: Annotated[
        bool,
        typer.Option(
            "--keep-alive",
            help="Keep the CLI process alive after execution so Playwright browser media stays open.",
        ),
    ] = False,
    var_values: Annotated[
        list[str] | None,
        typer.Option("--var", "-v", help="Template override in KEY=VALUE form."),
    ] = None,
) -> None:
    """Run a ritual recipe."""
    _run_recipe(recipe, dry_run=dry_run, keep_alive=keep_alive, var_values=var_values)


@app.command("dry-run")
def dry_run_command(
    recipe: Annotated[str, typer.Argument(help="Recipe id or YAML path.")],
    var_values: Annotated[
        list[str] | None,
        typer.Option("--var", "-v", help="Template override in KEY=VALUE form."),
    ] = None,
) -> None:
    """Validate and show planned actions without touching the desktop."""
    _run_recipe(recipe, dry_run=True, keep_alive=False, var_values=var_values)


@app.command("inspect-window")
def inspect_window(
    title_contains: Annotated[str, typer.Argument(help="Case-insensitive text from the window title.")],
    limit: Annotated[int, typer.Option("--limit", min=1, help="Maximum labels per window.")] = 100,
    control_type: Annotated[
        str | None,
        typer.Option("--control-type", help="Optional UI Automation control type, such as Button."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable JSON."),
    ] = False,
) -> None:
    """Inspect visible labels in matching Windows UI Automation windows."""
    try:
        result = run_read_only_primitive(
            "uia.element.list_labels",
            parameters={
                "window_title_contains": title_contains,
                "limit": limit,
                **({"control_type": control_type} if control_type else {}),
            },
        )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    inspections = list(result.details.get("windows", []))

    if json_output:
        console.print_json(data=inspections)
        return

    if not inspections:
        console.print(f"No windows found containing {escape(title_contains)!r}.")
        return

    for inspection in inspections:
        console.print(f"[bold]Window:[/] {escape(str(inspection.get('title', '')))}")
        console.print("[bold]Visible labels:[/]")
        labels = inspection.get("labels", [])
        if labels:
            for label in labels:
                console.print(f"- {escape(label)}")
        else:
            console.print("- [dim](none found)[/]")


@app.command()
def doctor(
    recipe: Annotated[str, typer.Argument(help="Recipe id or YAML path.")],
    var_values: Annotated[
        list[str] | None,
        typer.Option("--var", "-v", help="Template override in KEY=VALUE form."),
    ] = None,
    no_strict: Annotated[
        bool,
        typer.Option("--no-strict", help="Always exit 0 after printing doctor checks."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable Doctor v2 JSON."),
    ] = False,
) -> None:
    """Validate recipe health without launching apps, opening browsers, or clicking."""
    if recipe.startswith("target:"):
        _doctor_target(recipe.removeprefix("target:"), no_strict=no_strict, json_output=json_output)
        return

    try:
        parsed, _raw, missing_variables = load_recipe_for_diagnostics(
            recipe,
            _parse_vars(var_values or []),
        )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    report = build_doctor_report(parsed, missing_variables=missing_variables)
    if json_output:
        console.print_json(data=report.to_dict())
        if not no_strict and report.compatibility == "incompatible":
            raise typer.Exit(1)
        return

    checks = report.checks
    table = Table(
        title=(
            f"Doctor: {escape(parsed.name)} ({escape(parsed.id)}) - "
            f"{escape(report.compatibility)} ({report.compatibility_score})"
        )
    )
    table.add_column("Status", no_wrap=True)
    table.add_column("Section", no_wrap=True)
    table.add_column("Check", no_wrap=True)
    table.add_column("Message", overflow="fold")
    styles = {"ok": "green", "warn": "yellow", "error": "red", "info": "cyan"}
    for check in checks:
        style = styles.get(check.status, "")
        status = f"[{style}]{escape(check.status)}[/]" if style else escape(check.status)
        table.add_row(status, escape(check.section), escape(check.name), escape(check.message))
    console.print(table)
    console.print("[bold]Doctor details[/]")
    for check in checks:
        console.print(
            f"{escape(check.status)} | "
            f"{escape(check.section)} | "
            f"{escape(check.name)} | "
            f"{escape(check.message)}",
            soft_wrap=True,
        )
    if not no_strict and report.compatibility == "incompatible":
        raise typer.Exit(1)


def _doctor_target(target: str, *, no_strict: bool, json_output: bool) -> None:
    target_ref = target.strip()
    if not target_ref:
        console.print("[red]Error:[/] target doctor reference must include a target id or alias")
        raise typer.Exit(1)
    try:
        resolution = resolve_target(target_ref)
        plan = compile_target_start_plan(target_ref, resolution=resolution)
        report = build_plan_doctor_report(plan)
    except (RitualistError, ValueError) as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    if json_output:
        console.print_json(data=target_plan_payload(resolution, plan, report))
        if not no_strict and report.compatibility == "incompatible":
            raise typer.Exit(1)
        return

    _print_target_resolution(resolution)
    _print_plan_preview(plan, report)
    if not no_strict and report.compatibility == "incompatible":
        raise typer.Exit(1)


@app.command()
def gui() -> None:
    """Open the desktop GUI."""
    try:
        from .ui.app import run_gui

        run_gui()
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc


@app.command()
def home(
    mock: Annotated[
        bool,
        typer.Option("--mock", help="Show the QML Home mock card model instead of installed recipes."),
    ] = False,
) -> None:
    """Open the experimental Qt Quick Home surface."""
    try:
        from .home.app import run_home

        run_home(mock=mock)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc


def _run_recipe(
    recipe: str,
    *,
    dry_run: bool,
    keep_alive: bool,
    var_values: list[str] | None,
) -> None:
    logger = setup_logging()
    try:
        if not dry_run and _is_imported_pack_recipe_path(recipe):
            raise RitualistError(
                "quarantined imported recipes cannot be run directly; "
                "run Doctor/dry-run, configure the recipe, then enable the pack first"
            )
        parsed = load_recipe_reference(recipe, _parse_vars(var_values or []))
        registry = create_default_registry()
        adapters = create_default_adapters()
        runtime_control = RuntimeControl()
        run_logger = RunLogWriter()
        executor = WorkflowExecutor(
            registry=registry,
            adapters=adapters,
            dry_run=dry_run,
            confirmer=lambda request: typer.confirm(
                format_confirmation_request(request),
                default=False,
            ),
            status_callback=lambda event: console.print(
                f"[dim]{event.index}/{event.total}[/] "
                f"{escape(event.status)}: {escape(event.step_name)}"
            ),
            logger=logger,
            run_logger=run_logger,
            runtime_control=runtime_control,
            stop_requested=runtime_control.is_stopping,
        )
        try:
            summary = executor.run(parsed)
        except KeyboardInterrupt:
            runtime_control.stop()
            _finish_run_logger_as_stopped(run_logger, logger=logger)
            console.print("[yellow]Interrupted; stop requested.[/]")
            _print_post_run_summary(
                None,
                keep_open_active=False,
                run_logger=run_logger,
                interrupted=True,
            )
            raise typer.Exit(1) from None
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    _print_results(summary.results)
    keep_open_active = not dry_run and (keep_alive or _summary_requests_keep_open(parsed, summary))
    _print_post_run_summary(
        summary,
        keep_open_active=keep_open_active,
        run_logger=run_logger,
    )
    if keep_open_active:
        _keep_alive_until_interrupted()
    if not summary.success:
        raise typer.Exit(1)


def _is_imported_pack_recipe_path(recipe: str) -> bool:
    candidate = Path(recipe).expanduser()
    if not candidate.suffix:
        return False
    try:
        resolved_candidate = candidate.resolve(strict=False)
        resolved_imports = imported_packs_path().resolve(strict=False)
    except OSError:
        return False
    return resolved_candidate.is_relative_to(resolved_imports)


def _parse_vars(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise typer.BadParameter(f"expected KEY=VALUE, got {value!r}")
        key, raw = value.split("=", 1)
        key = key.strip()
        if not key:
            raise typer.BadParameter("template variable key cannot be empty")
        parsed[key] = raw
    return parsed


def _parse_primitive_params(values: list[str]) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for value in values:
        if "=" not in value:
            raise typer.BadParameter(f"expected KEY=VALUE, got {value!r}")
        key, raw = value.split("=", 1)
        key = key.strip()
        if not key:
            raise typer.BadParameter("primitive parameter key cannot be empty")
        parsed[key] = _parse_primitive_value(raw)
    return parsed


def _parse_primitive_value(raw: str) -> object:
    text = raw.strip()
    if not text:
        return ""
    if text[0] in "[{\"" or text in {"true", "false", "null"} or text[:1].isdigit():
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return raw
    return raw


def _print_steps(recipe: object) -> None:
    table = Table(title=f"{escape(recipe.name)} ({escape(recipe.id)})")
    table.add_column("#", justify="right")
    table.add_column("Step")
    table.add_column("Action")
    table.add_column("Optional")
    table.add_column("Confirm")
    for index, step in enumerate(recipe.execution_steps, start=1):
        table.add_row(
            str(index),
            escape(step.display_name),
            escape(step.action),
            "yes" if step.optional else "no",
            "yes" if step.requires_confirmation else "no",
        )
    console.print(table)


def _print_results(results: list[object]) -> None:
    table = Table(title="Run Results")
    table.add_column("#", justify="right")
    table.add_column("Status")
    table.add_column("Step")
    table.add_column("Message")
    for result in results:
        style = {
            "success": "green",
            "dry-run": "cyan",
            "skipped": "yellow",
            "cancelled": "yellow",
            "failed": "red",
        }.get(result.status, "")
        table.add_row(
            str(result.index),
            f"[{style}]{result.status}[/]" if style else result.status,
            escape(result.step_name),
            escape(result.message),
        )
    console.print(table)


def _print_paths(paths: dict[str, object]) -> None:
    table = Table(title="Ritualist Paths")
    table.add_column("Name")
    table.add_column("Path")
    for name, path in paths.items():
        table.add_row(escape(name), escape(str(path)))
    console.print(table)


def _print_visual_pack_result(result: VisualPackResult, *, json_output: bool) -> None:
    if json_output:
        console.print_json(data=result.to_dict())
        return
    console.print(f"[green]Exported {escape(result.pack_type)} pack:[/] {escape(str(result.output_path))}")
    console.print(f"pack: {escape(result.pack_id)}")
    console.print("contents:")
    for entry in result.entries:
        console.print(f"- {escape(entry)}")


def _print_visual_pack_import(record: ImportedVisualPackRecord, *, json_output: bool) -> None:
    if json_output:
        console.print_json(data=record.to_dict())
        return
    console.print(
        f"[green]Imported {escape(record.pack_type)} pack {escape(record.import_id)} into quarantine; it is disabled.[/]"
    )
    table = Table(title=f"Visual Pack: {escape(record.import_id)}")
    table.add_column("Field")
    table.add_column("Value")
    for key, value in record.to_dict().items():
        table.add_row(escape(str(key)), escape(str(value)))
    console.print(table)
    console.print("Review the quarantined visual pack before copying it into active canvases or themes.")


def _print_suite_pack_result(result: SuitePackExportResult, *, json_output: bool) -> None:
    if json_output:
        console.print_json(data=result.to_dict())
        return
    console.print(f"[green]Exported suite pack:[/] {escape(str(result.output_path))}")
    console.print(f"suite: {escape(result.suite_id)}")
    console.print("contents:")
    for entry in result.entries:
        console.print(f"- {escape(entry)}")


def _print_suite_pack_import(record: ImportedSuitePackRecord, *, json_output: bool) -> None:
    payload = record.to_dict()
    if json_output:
        console.print_json(data=payload)
        return
    console.print(
        f"[green]Imported suite pack {escape(record.import_id)} into quarantine; nothing was enabled or run.[/]"
    )
    _print_suite_pack_summary(payload)
    console.print("Behavior-bearing ritual packs remain disabled in recipe-pack quarantine.")


def _print_suite_pack_summary(payload: dict[str, Any]) -> None:
    table = Table(title="Suite Pack")
    table.add_column("Field")
    table.add_column("Value", overflow="fold")
    for key in ("import_id", "suite_id", "name", "version", "status", "root", "source"):
        if key in payload:
            table.add_row(escape(key), escape(str(payload.get(key, ""))))
    if "manifest" in payload:
        manifest = payload.get("manifest")
        if isinstance(manifest, dict):
            table.add_row("suite_id", escape(str(manifest.get("id", ""))))
            table.add_row("name", escape(str(manifest.get("name", ""))))
    table.add_row("auto_run", escape(str(payload.get("auto_run", False))))
    table.add_row("auto_enable", escape(str(payload.get("auto_enable", False))))
    console.print(table)


def _print_import_record(record: ImportedPackRecord) -> None:
    table = Table(title=f"Import: {escape(record.import_id)}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("status", escape(record.status))
    table.add_row("name", escape(record.name))
    table.add_row("version", escape(record.version))
    table.add_row("path", escape(str(record.root)))
    for recipe in record.recipes:
        table.add_row(f"recipe {escape(recipe.recipe_id)}", escape(recipe.name))
    console.print(table)


def _build_policy_report_for_target(target: str, *, profile: str) -> PolicyReport:
    resolved_profile = PolicyProfile(profile)
    candidate = Path(target).expanduser()
    if candidate.exists() and candidate.is_dir() and (candidate / "manifest.yaml").exists():
        pack = validate_imported_pack(candidate)
        return build_policy_report_for_recipe(
            pack.recipe,
            target=str(candidate),
            profile=resolved_profile,
            imported=True,
            private_or_local=False,
        )
    if candidate.exists() and candidate.is_file() and candidate.suffix == ".ritualistpack":
        pack = validate_pack(candidate)
        return build_policy_report_for_recipe(
            pack.recipe,
            target=str(candidate),
            profile=resolved_profile,
            imported=True,
            private_or_local=False,
        )
    return build_policy_report_for_recipe_reference(target, profile=resolved_profile)


def _print_policy_report(report: PolicyReport) -> None:
    table = Table(title=f"Policy Check: {escape(report.target)}")
    table.add_column("Decision", no_wrap=True)
    table.add_column("Category", no_wrap=True)
    table.add_column("Primitive", no_wrap=True)
    table.add_column("Source", no_wrap=True)
    table.add_column("Reason", overflow="fold")
    for finding in report.findings:
        style = "red" if finding.blocked else "yellow" if finding.disclosure_required else "green"
        table.add_row(
            f"[{style}]{escape(finding.decision.value)}[/]",
            escape(finding.category.value),
            escape(finding.primitive_id),
            escape(finding.source),
            escape(finding.reason),
        )
    console.print(table)
    status = "allowed" if report.allowed else "blocked"
    console.print(
        f"Profile: {escape(report.profile.value)} | "
        f"Target: {'imported pack' if report.imported else 'local recipe'} | "
        f"Result: {escape(status)}"
    )


def _print_policy_finding(finding: PolicyFinding) -> None:
    table = Table(title=f"Policy: {escape(finding.primitive_id)}")
    table.add_column("Field", no_wrap=True)
    table.add_column("Value", overflow="fold")
    for key, value in finding.to_dict().items():
        table.add_row(escape(str(key)), escape(_format_metadata_value(value)))
    console.print(table)


def _print_reconciled_runs(repaired: list[object]) -> None:
    for repair in repaired:
        console.print(f"Marked {escape(repair.run_id)} as interrupted.")


def _print_step_run_details(steps: list[dict[str, object]]) -> None:
    rows: list[str] = []
    for step in steps:
        detail = _format_step_run_details(step.get("metadata"))
        if not detail:
            continue
        index = str(step.get("index", "")).strip() or "?"
        action = str(step.get("action", "")).strip() or "step"
        rows.append(f"#{index} {action}: {detail}")
    if not rows:
        return
    console.print("[bold]Condition/branch details[/]")
    for row in rows:
        console.print(f"- {escape(row)}")


def _metadata_has_value(metadata: dict[str, object], key: str) -> bool:
    value = metadata.get(key)
    return value not in (None, "", [], {})


def _format_state_history(value: object) -> str:
    if not isinstance(value, list):
        return _format_metadata_value(value)
    states: list[str] = []
    for entry in value:
        if isinstance(entry, dict):
            state = entry.get("state")
            if state is not None:
                states.append(str(state))
        elif entry is not None:
            states.append(str(entry))
    return " -> ".join(states) if states else _format_metadata_value(value)


def _format_event_summaries(value: object) -> str:
    if not isinstance(value, list):
        return _format_metadata_value(value)
    labels: list[str] = []
    for entry in value[-5:]:
        if isinstance(entry, dict):
            event = entry.get("event")
            run_state = entry.get("run_state")
            step_state = entry.get("step_state")
            label = str(event) if event is not None else _format_metadata_value(entry)
            states = [str(state) for state in (run_state, step_state) if state is not None]
            if states:
                label = f"{label} ({'/'.join(states)})"
            labels.append(label)
        elif entry is not None:
            labels.append(str(entry))
    return "; ".join(labels) if labels else _format_metadata_value(value)


def _format_ownership_ledger(value: object) -> str:
    if not isinstance(value, list):
        return _format_metadata_value(value)
    rows: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "resource")
        description = str(item.get("description") or "").strip()
        cleanup = str(item.get("cleanup_action") or "none")
        risk = str(item.get("cleanup_risk") or "unknown")
        available = "cleanup available" if item.get("cleanup_available") else "manual/no cleanup"
        rows.append(f"{kind}: {description} ({available}; {cleanup}; {risk})")
    return "; ".join(rows) if rows else _format_metadata_value(value)


def _format_cleanup_offer(value: object) -> str:
    if not isinstance(value, dict):
        return _format_metadata_value(value)
    default = str(value.get("default") or "")
    options = value.get("options")
    option_labels: list[str] = []
    if isinstance(options, list):
        for option in options:
            if isinstance(option, dict):
                label = str(option.get("label") or option.get("id") or "")
                if label:
                    option_labels.append(label)
    suffix = f" ({', '.join(option_labels)})" if option_labels else ""
    return f"default: {default}{suffix}".strip()


def _format_step_run_details(metadata: object) -> str:
    if not isinstance(metadata, dict):
        return ""
    details: list[str] = []
    condition = metadata.get("condition")
    if isinstance(condition, dict):
        details.append(_format_condition_run_detail(condition))
    branch = metadata.get("branch")
    if branch:
        details.append(f"branch: {branch}")
    return "; ".join(detail for detail in details if detail)


def _format_condition_run_detail(condition: dict[str, object]) -> str:
    label = _condition_run_label(condition.get("details"))
    matched = condition.get("matched")
    if matched is True:
        state = "matched"
    elif matched is False:
        state = "not matched"
    elif condition.get("evaluated") is False:
        state = "not evaluated"
    else:
        state = "unknown"
    return f"condition: {label} {state}".strip()


def _condition_run_label(details: object) -> str:
    if not isinstance(details, dict):
        return "condition"
    predicate_type = details.get("type")
    if predicate_type:
        return str(predicate_type)
    operator = details.get("operator")
    if operator:
        return str(operator)
    return "condition"


def _format_metadata_value(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _performance_payload(report: PerformanceReport, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = report.model_dump(mode="json")
    payload.update(extra)
    return payload


def _print_performance_report(report: PerformanceReport) -> None:
    console.print(f"operation: {escape(report.operation)}")
    console.print(f"duration_ms: {report.duration_ms:.3f}")
    if report.counts:
        console.print("[bold]counts[/]")
        for key, value in sorted(report.counts.items()):
            console.print(f"- {escape(key)}: {value}")
    if report.warnings:
        console.print("[bold]warnings[/]")
        for warning in report.warnings:
            console.print(f"- {escape(warning)}")


def _print_init_report(report: object) -> None:
    messages: list[str] = []
    for name, path in report.created_dirs.items():
        messages.append(f"Created {name} directory: {path}")
    if report.config_created:
        messages.append("Created config file.")
    if report.sample_copied:
        messages.append(f"Copied bundled gaming_mode sample: {report.migration.recipe_path}")

    if not messages and not report.migration.changed:
        console.print("Initialization is already up to date.")
        return
    for message in messages:
        console.print(f"- {escape(message)}")
    if report.migration.changed:
        console.print(f"- Migrated {escape(str(report.migration.recipe_path))}:")
        for change in report.migration.changes:
            console.print(f"  - {escape(change)}")


def _print_post_run_summary(
    summary: object | None,
    *,
    keep_open_active: bool,
    run_logger: object | None = None,
    interrupted: bool = False,
) -> None:
    counts: dict[str, int] = {}
    if summary is not None:
        for result in summary.results:
            counts[result.status] = counts.get(result.status, 0) + 1
    counts_text = ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))
    console.print(f"Summary: {escape(counts_text or 'no steps recorded')}")
    metadata = _run_logger_metadata(run_logger)
    _print_runbook_summary(
        summarize_step_results(
            list(getattr(summary, "results", [])) if summary is not None else [],
            metadata=metadata,
            interrupted=interrupted,
        )
    )
    console.print(
        f"Final run state: {escape(_final_run_state(summary, metadata, interrupted=interrupted))}"
    )
    console.print(f"Outcome: {escape(_run_outcome(summary, interrupted=interrupted))}")
    step_text = _current_or_last_step(summary, metadata)
    if step_text:
        console.print(f"Current/last step: {escape(step_text)}")
    if _metadata_has_value(metadata, "current_step_state"):
        console.print(
            f"Current step state: {escape(str(metadata.get('current_step_state', '')))}"
        )
    for key, label in (
        ("wait_metadata", "Waiting"),
        ("paused_metadata", "Paused"),
        ("confirming_metadata", "Confirming"),
    ):
        if _metadata_has_value(metadata, key):
            console.print(f"{label}: {escape(_format_metadata_value(metadata.get(key)))}")
    if summary is not None and any(
        result.status == "cancelled" and "declined confirmation" in result.message
        for result in summary.results
    ):
        console.print("Confirmation declined; no confirmed risky action was performed.")
    console.print(f"Keep-open: {'active' if keep_open_active else 'inactive'}")


def _print_runbook_summary(summary: RunbookSummary) -> None:
    console.print("Runbook summary:")
    console.print(
        "  Preflight: "
        f"{escape(summary.preflight_status)} "
        f"({summary.preflight_passed} passed, {summary.preflight_failed} failed)"
    )
    console.print(f"  Actions completed: {summary.actions_completed}")
    console.print(
        "  Assertions: "
        f"{summary.assertions_passed} passed, {summary.assertions_failed} failed"
    )
    console.print(f"  Human prompts answered: {summary.human_prompts_answered}")
    console.print(f"  Final status: {escape(summary.final_status)}")
    console.print(f"  Stopped/interrupted: {escape(summary.stop_semantics)}")
    console.print(f"  Last step: {escape(summary.last_step or 'none')}")


def _print_operator_notes(notes: list[dict[str, object]]) -> None:
    if not notes:
        return
    table = Table(title="Operator notes (user-entered)")
    table.add_column("At", no_wrap=True)
    table.add_column("Source", no_wrap=True)
    table.add_column("Note", overflow="fold")
    for note in notes:
        if note.get("user_entered") is True:
            source = "user-entered"
        else:
            source = str(note.get("source", ""))
        table.add_row(
            escape(str(note.get("at", ""))),
            escape(source),
            escape(str(note.get("note", ""))),
        )
    console.print(table)


def _finish_run_logger_as_stopped(run_logger: object, *, logger: object) -> None:
    finish = getattr(run_logger, "finish", None)
    if finish is None:
        return
    try:
        finish(success=False, final_state="stopped")
    except TypeError:
        try:
            finish(success=False)
        except Exception as exc:  # noqa: BLE001 - finalizing after Ctrl+C is best effort.
            debug = getattr(logger, "debug", None)
            if debug is not None:
                debug("failed to finalize interrupted run: %s", exc)
    except Exception as exc:  # noqa: BLE001 - finalizing after Ctrl+C is best effort.
        debug = getattr(logger, "debug", None)
        if debug is not None:
            debug("failed to finalize interrupted run: %s", exc)


def _run_logger_metadata(run_logger: object | None) -> dict[str, object]:
    if run_logger is None:
        return {}
    metadata = getattr(run_logger, "_metadata", None)
    if isinstance(metadata, dict):
        return metadata
    run_dir = getattr(run_logger, "run_dir", None)
    if run_dir is None:
        return {}
    try:
        record = load_run(run_dir)
    except Exception:  # noqa: BLE001 - summary metadata is best effort.
        return {}
    if record is None:
        return {}
    return record.metadata


def _final_run_state(
    summary: object | None,
    metadata: dict[str, object],
    *,
    interrupted: bool,
) -> str:
    if _metadata_has_value(metadata, "final_state"):
        return str(metadata.get("final_state"))
    if _metadata_has_value(metadata, "status") and metadata.get("status") != "running":
        return str(metadata.get("status"))
    if interrupted:
        return "stopped"
    return _run_outcome(summary, interrupted=False)


def _run_outcome(summary: object | None, *, interrupted: bool) -> str:
    if interrupted:
        return "interrupted"
    if summary is None:
        return "stopped"
    results = getattr(summary, "results", [])
    statuses = [getattr(result, "status", "") for result in results]
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status == "cancelled" for status in statuses):
        return "stopped"
    if getattr(summary, "success", False):
        return "success"
    return "stopped"


def _current_or_last_step(summary: object | None, metadata: dict[str, object]) -> str:
    step_id = metadata.get("last_step_id")
    step_name = metadata.get("last_step_name")
    step_state = metadata.get("current_step_state")
    if step_id is not None or step_name:
        label = f"#{step_id}" if step_id is not None else "unknown step"
        if step_name:
            label = f"{label} {step_name}"
        if step_state:
            label = f"{label} ({step_state})"
        return label
    if summary is None or not getattr(summary, "results", []):
        return ""
    result = summary.results[-1]
    label = f"#{result.index} {result.step_name}"
    if result.status:
        label = f"{label} ({result.status})"
    return label


def _summary_requests_keep_open(recipe: object, summary: object) -> bool:
    steps_by_index = {index: step for index, step in enumerate(recipe.execution_steps, start=1)}
    for result in summary.results:
        step = steps_by_index.get(result.index)
        if (
            result.action == "browser.open"
            and result.status == "success"
            and getattr(step, "keep_open", False)
        ):
            return True
    return False


def _keep_alive_until_interrupted() -> None:
    console.print(
        "[yellow]Browser keep-open requested. Press Ctrl+C to let Ritualist exit.[/]"
    )
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        console.print("Exiting.")
