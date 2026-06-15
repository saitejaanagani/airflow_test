from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from jinja2 import Environment, StrictUndefined

from dag_manager.template_catalog import TemplateDefinition


@dataclass(frozen=True)
class RenderedDag:
    content: str
    sha256: str


class DagRenderer:
    def __init__(self) -> None:
        self.environment = Environment(
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.environment.filters["pyrepr"] = repr

    def render(self, definition: TemplateDefinition, values: dict[str, Any]) -> RenderedDag:
        source = definition.template_path.read_text(encoding="utf-8")
        template = self.environment.from_string(source)
        content = template.render(**values).rstrip() + "\n"
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return RenderedDag(content=content, sha256=digest)
