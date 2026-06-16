from __future__ import annotations

from collections import Counter
import json
import time
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from .actions.registry import create_default_registry
from .adapters.fake import FakeAdapters
from .adapters import create_default_adapters
from .app_setup import initialize_app
from .doctor import build_doctor_report
from .errors import RitualistError
from .executor import WorkflowExecutor
from .logging_setup import setup_logging
from .overlay import format_confirmation_request
from .perf import PerformanceReport, measure_operation
from .paths import (
    app_data_dir,
    browser_profiles_dir,
    config_dir,
    config_file,
    logs_dir,
    recipes_dir,
    runs_dir,
)
from .recipe_loader import discover_recipes, load_recipe_for_diagnostics, load_recipe_reference
from .run_logs import RunLogWriter, list_recent_runs, load_run, reconcile_running_runs
from .runtime_control import RuntimeControl

app = typer.Typer(help="Run local, inspectable desktop rituals.")
perf_app = typer.Typer(help="Measure Ritualist CLI operations without timing gates.")
app.add_typer(perf_app, name="perf")
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
            "logs": logs_dir(),
            "runs": runs_dir(),
            "browser_profiles": browser_profiles_dir(),
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
                    "browser_calls": len(fakes.browser.calls),
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
    for key in ("current_run_state", "current_step_state", "final_state"):
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
    if metadata.get("final_message"):
        table.add_row("final_message", escape(str(metadata.get("final_message", ""))))
    table.add_row("path", escape(str(record.path)))
    console.print(table)

    steps = Table(title="Steps")
    steps.add_column("#", justify="right")
    steps.add_column("Status")
    steps.add_column("Step")
    steps.add_column("Action")
    steps.add_column("Message")
    for step in record.steps:
        steps.add_row(
            str(step.get("index", "")),
            escape(str(step.get("status", ""))),
            escape(str(step.get("step_name", ""))),
            escape(str(step.get("action", ""))),
            escape(str(step.get("message", ""))),
        )
    console.print(steps)


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
        from .adapters.windows_uia import WindowsUIAutomationAdapter

        inspections = WindowsUIAutomationAdapter().inspect_windows(
            title_contains=title_contains,
            limit=limit,
            control_type=control_type,
        )
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    if json_output:
        console.print_json(
            data=[
                {"title": inspection.title, "labels": inspection.labels}
                for inspection in inspections
            ]
        )
        return

    if not inspections:
        console.print(f"No windows found containing {escape(title_contains)!r}.")
        return

    for inspection in inspections:
        console.print(f"[bold]Window:[/] {escape(inspection.title)}")
        console.print("[bold]Visible labels:[/]")
        if inspection.labels:
            for label in inspection.labels:
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


def _print_reconciled_runs(repaired: list[object]) -> None:
    for repair in repaired:
        console.print(f"Marked {escape(repair.run_id)} as interrupted.")


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
