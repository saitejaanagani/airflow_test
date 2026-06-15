from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dag_manager.config import Settings
from dag_manager.github_client import GitHubClient, GitHubWriteResult
from dag_manager.models import DagRevision, ManagedDag
from dag_manager.renderer import DagRenderer, RenderedDag
from dag_manager.template_catalog import TemplateCatalog

DAG_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,249}$")


@dataclass(frozen=True)
class SaveResult:
    managed_dag: ManagedDag
    rendered: RenderedDag
    github: GitHubWriteResult


class DagManagerService:
    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings
        self.catalog = TemplateCatalog.from_settings(settings)
        self.renderer = DagRenderer()

    def list_dags(self) -> list[ManagedDag]:
        statement = select(ManagedDag).order_by(ManagedDag.updated_at.desc(), ManagedDag.dag_id.asc())
        return list(self.session.execute(statement).scalars().all())

    def get_dag(self, managed_dag_id: int) -> ManagedDag:
        dag = self.session.get(ManagedDag, managed_dag_id)
        if not dag:
            raise KeyError(f"Managed DAG {managed_dag_id} was not found.")
        return dag

    def create(self, template_key: str, raw_values: dict[str, Any], actor: str | None) -> SaveResult:
        definition = self.catalog.get(template_key)
        values = self.catalog.coerce_and_validate(definition, raw_values)
        dag_id = self._validate_dag_id(values.get("dag_id"))
        existing = self.session.execute(select(ManagedDag).where(ManagedDag.dag_id == dag_id)).scalar_one_or_none()
        if existing:
            raise ValueError(f"DAG ID '{dag_id}' is already managed. Open it from the dashboard to edit it.")

        rendered = self.renderer.render(definition, values)
        github_path = self._github_path(dag_id)
        github = self._write_github(github_path, rendered.content, f"Create DAG {dag_id} from {template_key}")

        managed_dag = ManagedDag(
            dag_id=dag_id,
            template_key=template_key,
            github_path=github_path,
            current_values=values,
            state="ACTIVE",
            latest_commit_sha=github.commit_sha,
            created_by=actor,
            updated_by=actor,
        )
        self.session.add(managed_dag)
        self.session.flush()
        self._add_revision(managed_dag, 1, "CREATE", values, rendered.sha256, github.commit_sha, actor)
        return SaveResult(managed_dag=managed_dag, rendered=rendered, github=github)

    def update(self, managed_dag_id: int, raw_values: dict[str, Any], actor: str | None) -> SaveResult:
        managed_dag = self.get_dag(managed_dag_id)
        definition = self.catalog.get(managed_dag.template_key)
        values = self.catalog.coerce_and_validate(definition, raw_values)
        dag_id = self._validate_dag_id(values.get("dag_id"))
        if dag_id != managed_dag.dag_id:
            raise ValueError("Renaming an existing DAG ID is intentionally disabled in the starter package.")

        rendered = self.renderer.render(definition, values)
        github = self._write_github(
            managed_dag.github_path,
            rendered.content,
            f"Update DAG {managed_dag.dag_id} from {managed_dag.template_key}",
        )
        next_revision = self.session.execute(
            select(func.coalesce(func.max(DagRevision.revision_no), 0) + 1).where(
                DagRevision.managed_dag_id == managed_dag.id
            )
        ).scalar_one()

        managed_dag.current_values = values
        managed_dag.latest_commit_sha = github.commit_sha
        managed_dag.updated_by = actor
        self._add_revision(
            managed_dag,
            int(next_revision),
            "UPDATE",
            values,
            rendered.sha256,
            github.commit_sha,
            actor,
        )
        self.session.flush()
        return SaveResult(managed_dag=managed_dag, rendered=rendered, github=github)

    def preview(self, template_key: str, raw_values: dict[str, Any]) -> RenderedDag:
        definition = self.catalog.get(template_key)
        values = self.catalog.coerce_and_validate(definition, raw_values)
        self._validate_dag_id(values.get("dag_id"))
        return self.renderer.render(definition, values)

    def _write_github(self, path: str, content: str, message: str) -> GitHubWriteResult:
        client = GitHubClient(self.settings)
        try:
            return client.upsert_file(path, content, message)
        finally:
            client.close()

    def _github_path(self, dag_id: str) -> str:
        filename = f"{dag_id}.py"
        return str(PurePosixPath(self.settings.github_dag_path) / filename)

    @staticmethod
    def _validate_dag_id(value: Any) -> str:
        dag_id = str(value or "").strip()
        if not DAG_ID_PATTERN.fullmatch(dag_id):
            raise ValueError(
                "DAG ID must begin with a letter and contain only letters, numbers, underscore, dot, or hyphen."
            )
        return dag_id

    def _add_revision(
        self,
        managed_dag: ManagedDag,
        revision_no: int,
        action: str,
        values: dict[str, Any],
        rendered_sha256: str,
        commit_sha: str | None,
        actor: str | None,
    ) -> None:
        self.session.add(
            DagRevision(
                managed_dag_id=managed_dag.id,
                revision_no=revision_no,
                action=action,
                values=values,
                rendered_sha256=rendered_sha256,
                github_commit_sha=commit_sha,
                created_by=actor,
            )
        )
