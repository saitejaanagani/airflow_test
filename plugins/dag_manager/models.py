from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, MetaData, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

SCHEMA = "pcs_dags_manager"
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Base = declarative_base(metadata=MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION))


class ManagedDag(Base):
    __tablename__ = "managed_dag"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dag_id = Column(String(250), nullable=False, unique=True, index=True)
    template_key = Column(String(128), nullable=False, index=True)
    github_path = Column(Text, nullable=False, unique=True)
    current_values = Column(JSONB, nullable=False)
    state = Column(String(24), nullable=False, default="ACTIVE", server_default="ACTIVE")
    latest_commit_sha = Column(String(64), nullable=True)
    created_by = Column(String(250), nullable=True)
    updated_by = Column(String(250), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    revisions = relationship(
        "DagRevision",
        back_populates="managed_dag",
        cascade="all, delete-orphan",
        order_by="DagRevision.revision_no",
    )


class DagRevision(Base):
    __tablename__ = "dag_revision"
    __table_args__ = (UniqueConstraint("managed_dag_id", "revision_no"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    managed_dag_id = Column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.managed_dag.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_no = Column(Integer, nullable=False)
    action = Column(String(16), nullable=False)
    values = Column(JSONB, nullable=False)
    rendered_sha256 = Column(String(64), nullable=False)
    github_commit_sha = Column(String(64), nullable=True)
    created_by = Column(String(250), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    managed_dag = relationship("ManagedDag", back_populates="revisions")
