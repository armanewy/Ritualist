from __future__ import annotations

import time
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from .actions.registry import create_default_registry
from .adapters import create_default_adapters
from .app_setup import initialize_app
from .doctor import diagnose_recipe
from .errors import RitualistError
from .executor import WorkflowExecutor
from .logging_setup import setup_logging
from .overlay import format_confirmation_request
from .paths import (
    app_data_dir,
    browser_profiles_dir,
    config_dir,
    config_file,
    logs_dir,
    recipes_dir,
    runs_dir,
)
from .recipe_loader import discover_recipes, load_recipe_reference
from .run_logs import RunLogWriter, list_recent_runs, load_run, reconcile_running_runs

app = typer.Typer(help="Run local, inspectable desktop rituals.")
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
) -> None:
    """Validate recipe health without launching apps, opening browsers, or clicking."""
    try:
        parsed = load_recipe_reference(recipe, _parse_vars(var_values or []))
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    checks = diagnose_recipe(parsed)
    table = Table(title=f"Doctor: {escape(parsed.name)} ({escape(parsed.id)})")
    table.add_column("Status")
    table.add_column("Check")
    table.add_column("Message")
    styles = {"ok": "green", "warn": "yellow", "error": "red", "info": "cyan"}
    for check in checks:
        style = styles.get(check.status, "")
        status = f"[{style}]{escape(check.status)}[/]" if style else escape(check.status)
        table.add_row(status, escape(check.name), escape(check.message))
    console.print(table)
    if not no_strict and any(check.status == "error" for check in checks):
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
            run_logger=RunLogWriter(),
        )
        summary = executor.run(parsed)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    _print_results(summary.results)
    keep_open_active = not dry_run and (keep_alive or _summary_requests_keep_open(parsed, summary))
    _print_post_run_summary(summary, keep_open_active=keep_open_active)
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


def _print_post_run_summary(summary: object, *, keep_open_active: bool) -> None:
    counts: dict[str, int] = {}
    for result in summary.results:
        counts[result.status] = counts.get(result.status, 0) + 1
    counts_text = ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))
    console.print(f"Summary: {escape(counts_text or 'no steps recorded')}")
    if any(
        result.status == "cancelled" and "declined confirmation" in result.message
        for result in summary.results
    ):
        console.print("Confirmation declined; no confirmed risky action was performed.")
    console.print(f"Keep-open: {'active' if keep_open_active else 'inactive'}")


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
