# DAG Manager architecture

## Runtime flow

1. Airflow loads `dag_manager.plugin:DagManagerPlugin` through the `airflow.plugins` package entry point.
2. The plugin registers a FastAPI app at `/dag-manager` and an embedded Airflow external view named **Manage DAGs**.
3. DAG Manager resolves its external JSON file from:
   1. an explicit CLI `--config` argument,
   2. `[dag_manager] config_file` in `airflow.cfg`, or
   3. `$AIRFLOW_HOME/config/dag_manager.json`.
4. The JSON supplies Airflow Connection IDs and non-secret behavior settings.
5. `PostgresHook` resolves the PostgreSQL Airflow Connection and builds the SQLAlchemy engine.
6. `BaseHook.get_connection()` resolves the GitHub Airflow Connection and reads its token from the password field.
7. The dashboard discovers template folders from the external `templates.root` or from packaged starter templates.
8. A selected `template_variables.json` generates a sectioned form.
9. Submitted values are type-coerced and validated against variable metadata.
10. `dag_template_file.jinja` is rendered with Jinja `StrictUndefined` and a safe Python-literal filter.
11. The GitHub Contents API creates or updates `dags/generated/<dag_id>.py` on the configured branch.
12. PostgreSQL stores the current form values and an immutable revision record.

## Configuration boundary

### Airflow Connections: credentials

- PostgreSQL username/password, host, port, database, and SSL extras.
- GitHub personal access token or equivalent token.

The plugin retrieves these values at runtime from Airflow. This also allows Airflow's configured Connections secrets backend to supply them.

### External JSON: non-secret settings

- PostgreSQL Connection ID.
- GitHub Connection ID.
- Repository, branch, DAG folder, and API URL.
- External template root.
- Schema auto-creation behavior.

The JSON is deliberately outside the installed Python package so a ConfigMap, mounted file, or deployment-specific configuration can replace it without rebuilding the wheel.

## Minimal PostgreSQL design

### `managed_dag`

One row per DAG currently managed by the UI. It stores only the template key, GitHub path, latest values, state, commit SHA, and audit columns.

### `dag_revision`

One row per successful create/update operation. It keeps the exact values, generated-file SHA-256, GitHub commit SHA, actor, and revision number.

No template text, field definitions, generated Python source, or credentials are duplicated in PostgreSQL.

## Compatibility choice

The plugin uses FastAPI apps and external views available in Airflow 3.1.2 and the Airflow 3.2.x line. A standalone Jinja/JavaScript interface is used instead of coupling the package to Airflow frontend internals.
