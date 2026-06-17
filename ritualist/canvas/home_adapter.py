from __future__ import annotations

from typing import Mapping

from ritualist.home.models import (
    DEFAULT_RECIPE_ACCENT,
    HomeCard,
    HomeCardStatus,
    HomeLastRunStatus,
    HomeModel,
)

from .models import CanvasBindingKind, CanvasComponent, CanvasComponentBinding, CanvasDocument


def canvas_to_home_model(
    canvas: CanvasDocument,
    *,
    runtime_state: Mapping[str, Mapping[str, object]] | None = None,
) -> HomeModel:
    cards: list[HomeCard] = []
    for component in canvas.components:
        card = _component_to_home_card(component, runtime_state or {})
        if card is not None:
            cards.append(card)
    return HomeModel(cards=cards)


def recipe_card_component(
    recipe_id: str,
    *,
    title: str,
    x: float = 80,
    y: float = 120,
) -> CanvasComponent:
    return CanvasComponent(
        id=recipe_id,
        type="ritual.card",
        x=x,
        y=y,
        width=520,
        height=300,
        z=10,
        props={"title": title, "recipe_id": recipe_id, "primary_action": "run"},
        binding=CanvasComponentBinding(kind=CanvasBindingKind.RECIPE, recipe_id=recipe_id),
    )


def _component_to_home_card(
    component: CanvasComponent,
    runtime_state: Mapping[str, Mapping[str, object]],
) -> HomeCard | None:
    props = component.props_dict()
    binding = component.binding
    if component.type == "ritual.card":
        recipe_id = _binding_reference(binding) or str(props.get("recipe_id") or component.id)
        return _home_card(
            component,
            title=str(props.get("title") or recipe_id),
            category="Recipes",
            subtitle=str(props.get("subtitle") or "Ready to run locally"),
            description=str(props.get("description") or ""),
            runtime_state=runtime_state.get(recipe_id, {}),
        )
    if component.type == "target.card":
        target_id = _binding_reference(binding) or str(props.get("target") or component.id)
        return _home_card(
            component,
            title=str(props.get("title") or target_id),
            category="Targets",
            subtitle=str(props.get("subtitle") or "Preview target plan"),
            description=str(props.get("description") or f"Target binding: {target_id}"),
            runtime_state=runtime_state.get(target_id, {}),
        )
    return None


def _home_card(
    component: CanvasComponent,
    *,
    title: str,
    category: str,
    subtitle: str,
    description: str,
    runtime_state: Mapping[str, object],
) -> HomeCard:
    status = _home_status(runtime_state.get("status"))
    last_run_status = _last_run_status(runtime_state.get("last_run_status"))
    return HomeCard(
        id=component.id,
        title=title,
        category=category,
        subtitle=str(runtime_state.get("subtitle") or subtitle),
        description=str(runtime_state.get("description") or description),
        status=status,
        last_run_status=last_run_status,
        last_run_message=str(runtime_state.get("last_run_message") or ""),
        accent=str(component.props_dict().get("accent") or DEFAULT_RECIPE_ACCENT),
        image=str(component.props_dict().get("image") or ""),
    )


def _binding_reference(binding: CanvasComponentBinding | None) -> str:
    return binding.reference if binding is not None else ""


def _home_status(value: object) -> HomeCardStatus:
    try:
        return HomeCardStatus(str(value))
    except ValueError:
        return HomeCardStatus.READY


def _last_run_status(value: object) -> HomeLastRunStatus:
    try:
        return HomeLastRunStatus(str(value))
    except ValueError:
        return HomeLastRunStatus.NONE
