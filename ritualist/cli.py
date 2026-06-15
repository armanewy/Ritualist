from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .actions.registry import create_default_registry
from .adapters import create_default_adapters
from .errors import RitualistError
from .executor import WorkflowExecutor
from .logging_setup import setup_logging
from .recipe_loader import load_recipe

app = typer.Typer(help="Run local, inspectable desktop rituals.")
console = Console()


@app.command()
def validate(
    recipe: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    var_values: Annotated[
        list[str] | None,
        typer.Option("--var", "-v", help="Template override in KEY=VALUE form."),
    ] = None,
) -> None:
    """Validate a recipe without running it."""
    try:
        parsed = load_recipe(recipe, _parse_vars(var_values or []))
    except RitualistError as exc:
        console.print(f"[red]Invalid recipe:[/] {exc}")
        raise typer.Exit(1) from exc

    _print_steps(parsed.name, parsed.steps)
    console.print("[green]Recipe is valid.[/]")


@app.command()
def run(
    recipe: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and show planned actions.")],
    var_values: Annotated[
        list[str] | None,
        typer.Option("--var", "-v", help="Template override in KEY=VALUE form."),
    ] = None,
) -> None:
    """Run a ritual recipe."""
    logger = setup_logging()
    try:
        parsed = load_recipe(recipe, _parse_vars(var_values or []))
        registry = create_default_registry()
        adapters = create_default_adapters()
        executor = WorkflowExecutor(
            registry=registry,
            adapters=adapters,
            dry_run=dry_run,
            confirmer=lambda prompt: typer.confirm(prompt, default=False),
            status_callback=lambda event: console.print(
                f"[dim]{event.index}/{event.total}[/] {event.status}: {event.step_name}"
            ),
            logger=logger,
        )
        summary = executor.run(parsed)
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1) from exc

    _print_results(summary.results)
    if not summary.success:
        raise typer.Exit(1)


@app.command()
def gui() -> None:
    """Open the desktop GUI."""
    try:
        from .ui.app import run_gui

        run_gui()
    except RitualistError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1) from exc


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


def _print_steps(recipe_name: str, steps: list[object]) -> None:
    table = Table(title=recipe_name)
    table.add_column("#", justify="right")
    table.add_column("Step")
    table.add_column("Action")
    table.add_column("Optional")
    table.add_column("Confirm")
    for index, step in enumerate(steps, start=1):
        table.add_row(
            str(index),
            step.display_name,
            step.action,
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
            result.step_name,
            result.message,
        )
    console.print(table)
