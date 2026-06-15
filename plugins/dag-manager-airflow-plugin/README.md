# Airflow DAG Manager Plugin

A template-driven Apache Airflow 3 plugin that creates and edits DAG files in GitHub from folder-based Jinja templates.

Supported Airflow versions:

- Apache Airflow 3.1.2+
- Apache Airflow 3.2.x

The plugin uses Airflow's `fastapi_apps` and `external_views` plugin interfaces. Its UI is server-rendered with Jinja and lightweight JavaScript so it remains easy to customize.

## Version 0.2 security/configuration model

DAG Manager no longer reads database URLs or GitHub tokens from `.env` files.

- PostgreSQL credentials come from an Airflow **Postgres Connection**.
- GitHub credentials come from an Airflow **Connection**.
- Connection IDs and non-secret settings come from an external JSON file outside the installed package.
- The JSON file must not contain passwords or tokens.

## Features

- Adds a **DAG Manager** section to the Airflow navigation.
- Discovers templates from folders.
- Builds forms from `template_variables.json`.
- Groups variables by configurable sections.
- Validates and renders `dag_template_file.jinja` using Jinja `StrictUndefined`.
- Creates and updates DAG files through the GitHub Contents API.
- Lists DAGs created by the UI.
- Stores current state and revision history in PostgreSQL schema `pcs_dags_manager`.
- Supports an external template directory.

## Template layout

```text
templates/
├── s3_to_s3_dag_template/
│   ├── dag_template_file.jinja
│   └── template_variables.json
└── smb_to_s3_dag_template/
    ├── dag_template_file.jinja
    └── template_variables.json
```

## 1. Create Airflow Connections

### PostgreSQL Connection

Create an Airflow Connection with a connection ID such as:

```text
dag_manager_postgres
```

Use:

```text
Connection Type: Postgres
Host: PostgreSQL/RDS hostname
Database/Schema: airflow or your application database
Login: database username
Password: database password
Port: 5432
```

Optional SSL settings can be stored in the Airflow Connection's Extra JSON, for example:

```json
{
  "sslmode": "require"
}
```

### GitHub Connection

Create an Airflow Connection with a connection ID such as:

```text
dag_manager_github
```

Recommended fields:

```text
Connection Type: Generic
Password: GitHub fine-grained personal access token
```

The plugin reads the token from the Connection password. For compatibility, it can also read a `token` value from the Connection Extra JSON, but the password field is preferred.

The token needs repository **Contents: Read and write** permission for the target DAG repository.

## 2. Create the external JSON configuration

Copy:

```text
config/dag_manager.example.json
```

to an external mounted location such as:

```text
/opt/airflow/config/dag_manager.json
```

Example:

```json
{
  "connections": {
    "postgres_conn_id": "dag_manager_postgres",
    "github_conn_id": "dag_manager_github"
  },
  "github": {
    "repository": "your-organization/airflow-dags",
    "branch": "main",
    "dag_path": "dags/generated",
    "api_url": "https://api.github.com"
  },
  "templates": {
    "root": "/opt/airflow/dag-manager-templates"
  },
  "database": {
    "auto_create_schema": false
  }
}
```

### JSON properties

| Property | Purpose |
|---|---|
| `connections.postgres_conn_id` | Airflow Connection ID used by `PostgresHook`. |
| `connections.github_conn_id` | Airflow Connection ID holding the GitHub token. |
| `github.repository` | GitHub repository in `owner/repository` format. |
| `github.branch` | Branch where generated DAG files are written. |
| `github.dag_path` | Folder within the repository for generated DAGs. |
| `github.api_url` | GitHub REST API root. Use your enterprise API root for GitHub Enterprise Server. |
| `templates.root` | External folder containing template subfolders. Relative paths are resolved relative to the JSON file. |
| `database.auto_create_schema` | Whether the plugin may create its schema/tables when the UI loads. |

## 3. Tell DAG Manager where the JSON file is

The normal/default location is:

```text
$AIRFLOW_HOME/config/dag_manager.json
```

For the standard Docker image this commonly resolves to:

```text
/opt/airflow/config/dag_manager.json
```

For a different location, add this section to `airflow.cfg`:

```ini
[dag_manager]
config_file = /mounted/config/dag_manager-prod.json
```

No DAG Manager-specific environment variables are required.

## 4. Install and initialize

```bash
pip install .
dag-manager-init-db
airflow plugins
```

To initialize using an explicit file path from a shell:

```bash
dag-manager-init-db --config /opt/airflow/config/dag_manager.json
```

Validate templates:

```bash
dag-manager-validate-templates --config /opt/airflow/config/dag_manager.json
```

Restart the Airflow API server after installing or upgrading the package.

## Kubernetes deployment example

Store `dag_manager.json` in a ConfigMap and mount it as:

```text
/opt/airflow/config/dag_manager.json
```

Store credentials only in Airflow Connections or an Airflow Connections secrets backend. Do not place credentials in the ConfigMap.

Mount the external template folders separately, for example:

```text
/opt/airflow/dag-manager-templates
```

## Database model

Only two application tables are used:

- `pcs_dags_manager.managed_dag`: current configuration and latest GitHub state.
- `pcs_dags_manager.dag_revision`: immutable create/update history.

Templates and variable definitions are not stored in PostgreSQL.

## Customize the actual DAG implementation

The supplied S3-to-S3 and SMB-to-S3 templates are demonstration DAGs. Replace their task bodies or imports with your existing custom operators. The UI and renderer do not need changes as long as template variable keys remain aligned with `template_variables.json`.

## Production hardening to add later

- GitHub App authentication instead of a personal access token.
- Branch-per-change and pull-request approval mode.
- Airflow RBAC-aware authorization for create/edit actions.
- CSRF protection or an API-only backend with signed requests.
- Secret references in template fields instead of accepting secret values in forms.
