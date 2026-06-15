from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from dag_manager.config import Settings
from dag_manager.models import Base, SCHEMA


@lru_cache(maxsize=8)
def get_engine(postgres_conn_id: str) -> Engine:
    """Build a SQLAlchemy engine from an Airflow Postgres Connection."""

    try:
        from airflow.providers.postgres.hooks.postgres import PostgresHook  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "apache-airflow-providers-postgres is required by DAG Manager. "
            "Install the plugin package with its dependencies."
        ) from exc

    hook = PostgresHook(postgres_conn_id=postgres_conn_id)
    return create_engine(hook.sqlalchemy_url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=8)
def get_session_factory(postgres_conn_id: str):
    return sessionmaker(
        bind=get_engine(postgres_conn_id),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


@contextmanager
def session_scope(settings: Settings) -> Iterator[Session]:
    settings.require_database()
    session = get_session_factory(settings.postgres_conn_id)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_schema(settings: Settings) -> None:
    settings.require_database()
    engine = get_engine(settings.postgres_conn_id)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    Base.metadata.create_all(bind=engine)
