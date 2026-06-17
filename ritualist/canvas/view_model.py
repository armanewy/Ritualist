from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import CanvasDocument
from .runtime import CanvasRuntimeContext, CanvasRuntimeModel, build_canvas_runtime_model


@dataclass(frozen=True)
class CanvasViewModel:
    runtime: CanvasRuntimeModel

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "ritualist.canvas.view_model.v1",
            "runtime": self.runtime.to_dict(),
        }


def build_canvas_view_model(
    document: CanvasDocument,
    *,
    context: CanvasRuntimeContext | None = None,
) -> CanvasViewModel:
    return CanvasViewModel(runtime=build_canvas_runtime_model(document, context=context))
