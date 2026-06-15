from __future__ import annotations

from airflow.plugins_manager import AirflowPlugin

from dag_manager.app import app

FASTAPI_APP = {
    "app": app,
    "url_prefix": "/dag-manager",
    "name": "DAG Manager",
}

DAG_MANAGER_VIEW = {
    "name": "Manage DAGs",
    "href": "/dag-manager/",
    "destination": "nav",
    "url_route": "dag-manager",
    "category": "DAG Manager",
    "icon": "/dag-manager/static/dag-manager-icon.svg",
    "icon_dark_mode": "/dag-manager/static/dag-manager-icon.svg",
}


class DagManagerPlugin(AirflowPlugin):
    name = "dag_manager_plugin"
    fastapi_apps = [FASTAPI_APP]
    external_views = [DAG_MANAGER_VIEW]


__all__ = ["DagManagerPlugin"]
