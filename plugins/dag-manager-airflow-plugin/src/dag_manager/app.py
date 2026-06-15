from __future__ import annotations

import logging
from importlib.resources import as_file, files
from typing import Any
from urllib.parse import quote_plus

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dag_manager.config import Settings
from dag_manager.db import init_schema, session_scope
from dag_manager.service import DagManagerService
from dag_manager.template_catalog import TemplateCatalog, TemplateDefinitionError

log = logging.getLogger(__name__)

app = FastAPI(title="DAG Manager", docs_url="/api/docs", redoc_url=None)

static_resource = files("dag_manager").joinpath("static")
ui_resource = files("dag_manager").joinpath("ui_templates")
_static_context = as_file(static_resource)
_ui_context = as_file(ui_resource)
static_path = _static_context.__enter__()
ui_path = _ui_context.__enter__()
app.mount("/static", StaticFiles(directory=str(static_path)), name="dag_manager_static")
templates = Jinja2Templates(directory=str(ui_path))


def _actor(request: Request) -> str:
    for header in ("x-forwarded-user", "remote-user", "x-auth-request-user"):
        if request.headers.get(header):
            return request.headers[header]
    return "airflow-user"


def _context(request: Request, **kwargs: Any) -> dict[str, Any]:
    return {
        "request": request,
        "app_name": "DAG Manager",
        **kwargs,
    }


def _maybe_init_schema(settings: Settings) -> None:
    if settings.auto_create_schema:
        init_schema(settings)


@app.get("/", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request, message: str | None = None, error: str | None = None):
    settings = Settings.from_file()
    try:
        settings.require_database()
        _maybe_init_schema(settings)
        catalog = TemplateCatalog.from_settings(settings)
        with session_scope(settings) as session:
            dags = DagManagerService(session, settings).list_dags()
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=_context(
                request,
                dags=dags,
                available_templates=catalog.list_templates(),
                message=message,
                error=error,
                repository=settings.github_repository,
                branch=settings.github_branch,
            ),
        )
    except Exception as exc:
        log.exception("Unable to load DAG Manager dashboard")
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context=_context(request, title="DAG Manager configuration error", error=str(exc)),
            status_code=500,
        )


@app.get("/dags/new", response_class=HTMLResponse, name="new_dag")
def new_dag(request: Request, template_key: str | None = None):
    settings = Settings.from_file()
    catalog = TemplateCatalog.from_settings(settings)
    available = catalog.list_templates()
    selected_key = template_key or (available[0].key if available else None)
    if not selected_key:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context=_context(request, title="No templates found", error="Add at least one template folder."),
            status_code=404,
        )
    definition = catalog.get(selected_key)
    values = {}
    for section in definition.ordered_sections():
        for key, spec in definition.fields_for_section(section["key"]):
            values[key] = spec.get("default") if section["key"] == "advanced_configuration" else None
    return templates.TemplateResponse(
        request=request,
        name="dag_form.html",
        context=_context(
            request,
            mode="create",
            definition=definition,
            available_templates=available,
            values=values,
            managed_dag=None,
            error=None,
        ),
    )


@app.post("/dags", name="create_dag")
async def create_dag(request: Request):
    settings = Settings.from_file()
    form = dict(await request.form())
    template_key = str(form.pop("template_key", ""))
    catalog = TemplateCatalog.from_settings(settings)
    definition = catalog.get(template_key)
    try:
        settings.require_database()
        settings.require_github()
        _maybe_init_schema(settings)
        with session_scope(settings) as session:
            result = DagManagerService(session, settings).create(template_key, form, _actor(request))
        message = quote_plus(f"Created {result.managed_dag.dag_id} in GitHub commit {result.github.commit_sha or 'unknown'}.")
        return RedirectResponse(url=f"{request.url_for('dashboard')}?message={message}", status_code=303)
    except Exception as exc:
        log.exception("Failed to create managed DAG")
        values = form
        values.setdefault("dag_id", form.get("dag_id"))
        return templates.TemplateResponse(
            request=request,
            name="dag_form.html",
            context=_context(
                request,
                mode="create",
                definition=definition,
                available_templates=catalog.list_templates(),
                values=values,
                managed_dag=None,
                error=str(exc),
            ),
            status_code=400,
        )


@app.get("/dags/{managed_dag_id}/edit", response_class=HTMLResponse, name="edit_dag")
def edit_dag(request: Request, managed_dag_id: int):
    settings = Settings.from_file()
    try:
        with session_scope(settings) as session:
            service = DagManagerService(session, settings)
            managed_dag = service.get_dag(managed_dag_id)
            definition = service.catalog.get(managed_dag.template_key)
            values = dict(managed_dag.current_values)
        return templates.TemplateResponse(
            request=request,
            name="dag_form.html",
            context=_context(
                request,
                mode="edit",
                definition=definition,
                available_templates=[definition],
                values=values,
                managed_dag=managed_dag,
                error=None,
            ),
        )
    except Exception as exc:
        return RedirectResponse(url=f"{request.url_for('dashboard')}?error={quote_plus(str(exc))}", status_code=303)


@app.post("/dags/{managed_dag_id}", name="update_dag")
async def update_dag(request: Request, managed_dag_id: int):
    settings = Settings.from_file()
    form = dict(await request.form())
    try:
        settings.require_github()
        with session_scope(settings) as session:
            service = DagManagerService(session, settings)
            managed_dag = service.get_dag(managed_dag_id)
            result = service.update(managed_dag_id, form, _actor(request))
        message = quote_plus(f"Updated {result.managed_dag.dag_id} in GitHub commit {result.github.commit_sha or 'unknown'}.")
        return RedirectResponse(url=f"{request.url_for('dashboard')}?message={message}", status_code=303)
    except Exception as exc:
        log.exception("Failed to update managed DAG")
        with session_scope(settings) as session:
            service = DagManagerService(session, settings)
            managed_dag = service.get_dag(managed_dag_id)
            definition = service.catalog.get(managed_dag.template_key)
        return templates.TemplateResponse(
            request=request,
            name="dag_form.html",
            context=_context(
                request,
                mode="edit",
                definition=definition,
                available_templates=[definition],
                values=form,
                managed_dag=managed_dag,
                error=str(exc),
            ),
            status_code=400,
        )


@app.get("/health", name="health")
def health():
    settings = Settings.from_file()
    catalog = TemplateCatalog.from_settings(settings)
    return {
        "status": "ok",
        "templates": [template.key for template in catalog.list_templates()],
        "github_repository": settings.github_repository or None,
        "github_branch": settings.github_branch,
    }
