"""SQLAlchemy Core Table definitions for app_* tables (InnoDB)."""

from __future__ import annotations

from sqlalchemy import Table, MetaData, Column, BigInteger, String, Enum, DECIMAL, Date, Text, TIMESTAMP, UniqueConstraint, Index

metadata_app = MetaData(schema=None)  # usa el schema por defecto (motoshop2024)

app_alert_actions = Table(
    "app_alert_actions",
    metadata_app,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("alert_id", String(64), nullable=False),
    Column("sku", String(64), nullable=False),
    Column("user_id", String(64), nullable=False),
    Column("action_type", Enum("ordered", "dismissed", "postponed"), nullable=False),
    Column("quantity", DECIMAL(10, 2), nullable=True),
    Column("supplier", String(255), nullable=True),
    Column("reason", String(500), nullable=True),
    Column("postponed_to", Date, nullable=True),
    Column("notes", Text, nullable=True),
    Column("idempotency_key", String(64), nullable=False),
    Column("created_at", TIMESTAMP, nullable=False),
    Column("request_id", String(64), nullable=False),
    UniqueConstraint("idempotency_key", name="uq_idempotency"),
    Index("idx_user_created", "user_id", "created_at"),
    Index("idx_alert", "alert_id"),
    Index("idx_sku_created", "sku", "created_at"),
    extend_existing=True,
)

app_audit_log = Table(
    "app_audit_log",
    metadata_app,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False),
    Column("user_role", String(32), nullable=False),
    Column("action", String(64), nullable=False),
    Column("target_type", String(64), nullable=False),
    Column("target_id", String(64), nullable=False),
    Column("request_id", String(64), nullable=False),
    Column("ip_address", String(45), nullable=True),
    Column("user_agent", String(500), nullable=True),
    Column("payload", Text, nullable=True),
    Column("status", Enum("success", "failure"), nullable=False),
    Column("error_msg", String(500), nullable=True),
    Column("created_at", TIMESTAMP, nullable=False),
    Index("idx_user_created", "user_id", "created_at"),
    Index("idx_target", "target_type", "target_id"),
    Index("idx_action_created", "action", "created_at"),
    extend_existing=True,
)
