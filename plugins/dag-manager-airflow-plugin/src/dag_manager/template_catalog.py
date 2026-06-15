from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any, Iterable

from dag_manager.config import Settings

TEMPLATE_FILE = "dag_template_file.jinja"
VARIABLES_FILE = "template_variables.json"
SUPPORTED_TYPES = {"string", "text", "integer", "number", "boolean", "select", "list", "json"}


class TemplateDefinitionError(ValueError):
    pass


@dataclass(frozen=True)
class TemplateDefinition:
    key: str
    title: str
    description: str
    template_path: Path
    variables_path: Path
    sections: list[dict[str, Any]]
    variables: dict[str, dict[str, Any]]

    def ordered_sections(self) -> list[dict[str, Any]]:
        return sorted(self.sections, key=lambda item: (item.get("order", 100), item.get("title", "")))

    def fields_for_section(self, section_key: str) -> list[tuple[str, dict[str, Any]]]:
        fields = [(key, spec) for key, spec in self.variables.items() if spec.get("section") == section_key]
        return sorted(fields, key=lambda item: (item[1].get("order", 100), item[1].get("title", item[0])))


class TemplateCatalog:
    def __init__(self, root: Path):
        self.root = root

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "TemplateCatalog":
        settings = settings or Settings.from_file()
        if settings.template_root:
            return cls(settings.template_root)
        package_templates = files("dag_manager").joinpath("templates")
        # Wheels are installed unpacked in normal Airflow deployments, so the
        # package resource can be addressed as a filesystem path.
        return cls(Path(str(package_templates)))

    def list_templates(self) -> list[TemplateDefinition]:
        if not self.root.exists():
            raise TemplateDefinitionError(f"Template root does not exist: {self.root}")
        definitions = []
        for directory in sorted(path for path in self.root.iterdir() if path.is_dir()):
            if (directory / TEMPLATE_FILE).exists() and (directory / VARIABLES_FILE).exists():
                definitions.append(self._load(directory))
        return definitions

    def get(self, template_key: str) -> TemplateDefinition:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", template_key):
            raise TemplateDefinitionError("Invalid template key.")
        directory = (self.root / template_key).resolve()
        if self.root.resolve() not in directory.parents:
            raise TemplateDefinitionError("Template path escapes the configured template root.")
        if not directory.exists():
            raise KeyError(f"Unknown template: {template_key}")
        return self._load(directory)

    def _load(self, directory: Path) -> TemplateDefinition:
        variables_path = directory / VARIABLES_FILE
        template_path = directory / TEMPLATE_FILE
        try:
            document = json.loads(variables_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise TemplateDefinitionError(f"Invalid JSON in {variables_path}: {exc}") from exc

        metadata = document.get("template", {})
        key = metadata.get("key") or directory.name
        if key != directory.name:
            raise TemplateDefinitionError(
                f"Template key '{key}' must match folder name '{directory.name}' in {variables_path}."
            )
        title = metadata.get("title") or key.replace("_", " ").title()
        description = metadata.get("description", "")
        sections = document.get("sections", [])
        variables = document.get("variables", {})
        self._validate(key, sections, variables)
        return TemplateDefinition(
            key=key,
            title=title,
            description=description,
            template_path=template_path,
            variables_path=variables_path,
            sections=sections,
            variables=variables,
        )

    @staticmethod
    def _validate(key: str, sections: list[dict[str, Any]], variables: dict[str, dict[str, Any]]) -> None:
        if not isinstance(sections, list) or not sections:
            raise TemplateDefinitionError(f"Template '{key}' must define at least one section.")
        if not isinstance(variables, dict) or not variables:
            raise TemplateDefinitionError(f"Template '{key}' must define variables.")

        section_keys = {section.get("key") for section in sections}
        if None in section_keys or len(section_keys) != len(sections):
            raise TemplateDefinitionError(f"Template '{key}' contains missing or duplicate section keys.")

        for variable_key, spec in variables.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable_key):
                raise TemplateDefinitionError(f"Invalid variable key '{variable_key}' in template '{key}'.")
            field_type = spec.get("type", "string")
            if field_type not in SUPPORTED_TYPES:
                raise TemplateDefinitionError(
                    f"Unsupported type '{field_type}' for variable '{variable_key}' in template '{key}'."
                )
            if spec.get("section") not in section_keys:
                raise TemplateDefinitionError(
                    f"Variable '{variable_key}' references an unknown section in template '{key}'."
                )
            if field_type == "select" and not spec.get("options"):
                raise TemplateDefinitionError(f"Select variable '{variable_key}' must define options.")

    def coerce_and_validate(self, definition: TemplateDefinition, raw_values: dict[str, Any]) -> dict[str, Any]:
        values: dict[str, Any] = {}
        errors: dict[str, str] = {}

        for key, spec in definition.variables.items():
            field_type = spec.get("type", "string")
            raw = raw_values.get(key)
            if field_type == "boolean":
                raw = raw in {True, "true", "1", "on", "yes"}
            elif raw is None:
                raw = spec.get("default")
            elif raw == "" and not spec.get("required", False):
                raw = None

            try:
                value = self._coerce(field_type, raw)
                self._validate_value(key, value, spec)
                values[key] = value
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                errors[key] = str(exc)

        if errors:
            details = "; ".join(f"{key}: {message}" for key, message in errors.items())
            raise TemplateDefinitionError(details)
        return values

    @staticmethod
    def _coerce(field_type: str, value: Any) -> Any:
        if value is None:
            return None
        if field_type in {"string", "text", "select"}:
            return str(value).strip()
        if field_type == "integer":
            return int(value)
        if field_type == "number":
            return float(value)
        if field_type == "boolean":
            return bool(value)
        if field_type == "list":
            if isinstance(value, list):
                return value
            return [item.strip() for item in str(value).split(",") if item.strip()]
        if field_type == "json":
            if isinstance(value, (dict, list)):
                return value
            return json.loads(str(value))
        raise ValueError(f"Unsupported type: {field_type}")

    @staticmethod
    def _validate_value(key: str, value: Any, spec: dict[str, Any]) -> None:
        if spec.get("required", False) and value in (None, "", []):
            raise ValueError("This field is required.")
        if value is None:
            return
        if isinstance(value, str):
            if spec.get("min_length") is not None and len(value) < int(spec["min_length"]):
                raise ValueError(f"Minimum length is {spec['min_length']}.")
            if spec.get("max_length") is not None and len(value) > int(spec["max_length"]):
                raise ValueError(f"Maximum length is {spec['max_length']}.")
            pattern = spec.get("pattern")
            if pattern and not re.fullmatch(pattern, value):
                raise ValueError(spec.get("pattern_message", f"Value does not match {pattern}."))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if spec.get("minimum") is not None and value < spec["minimum"]:
                raise ValueError(f"Minimum value is {spec['minimum']}.")
            if spec.get("maximum") is not None and value > spec["maximum"]:
                raise ValueError(f"Maximum value is {spec['maximum']}.")
        options = spec.get("options")
        if options and value not in [option["value"] if isinstance(option, dict) else option for option in options]:
            raise ValueError("Select one of the allowed values.")

    def validate_all(self) -> Iterable[TemplateDefinition]:
        return self.list_templates()
