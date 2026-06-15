from __future__ import annotations

import argparse
from pathlib import Path

from dag_manager.config import Settings
from dag_manager.db import init_schema as create_schema
from dag_manager.template_catalog import TemplateCatalog


def _config_argument(description: str) -> Path | None:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=(
            "Path to dag_manager.json. If omitted, DAG Manager reads "
            "[dag_manager] config_file from airflow.cfg, then "
            "$AIRFLOW_HOME/config/dag_manager.json."
        ),
    )
    return parser.parse_args().config


def init_db() -> None:
    settings = Settings.from_file(_config_argument("Initialize the DAG Manager PostgreSQL schema."))
    settings.require_database()
    create_schema(settings)
    print(f"Initialized PostgreSQL schema pcs_dags_manager using Airflow Connection '{settings.postgres_conn_id}'.")


def validate_templates() -> None:
    settings = Settings.from_file(_config_argument("Validate DAG Manager templates."))
    catalog = TemplateCatalog.from_settings(settings)
    templates = list(catalog.validate_all())
    for definition in templates:
        print(f"OK  {definition.key}: {len(definition.variables)} variables")
    print(f"Validated {len(templates)} template(s) using configuration {settings.config_file}.")
