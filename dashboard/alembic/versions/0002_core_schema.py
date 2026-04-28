"""Core schema — all tables, indexes, non-ORM and ORM.

This migration is the source of truth for the complete dashboard schema.
It is safe to run on:
  (a) a fresh database (creates everything)
  (b) an existing SQLite database where db.create_all() already ran
      (all op.create_table calls use checkfirst=True)
  (c) a Postgres database where db.create_all() already ran
      (same — checkfirst=True)

Tables managed by ORM (models.py):
  users, audit_log, login_throttles, scheduled_tasks, triggers,
  trigger_executions, runtime_configs, systems, file_shares, roles,
  heartbeats, heartbeat_runs, heartbeat_triggers, missions, projects,
  goals, goal_tasks, tickets, ticket_comments, ticket_activity,
  brain_repo_configs, plugin_scan_cache, plugin_audit_log

Tables NOT managed by ORM (executescript-only on SQLite):
  plugins_installed, plugin_hook_circuit_state,
  integration_health_cache, plugin_orphans,
  knowledge_connections, knowledge_connection_events, knowledge_api_keys

Boolean columns per ADR PG-Q5 inventory use sa.Boolean throughout.

Performance indexes for ORM tables (not created by db.create_all()):
  idx_hb_runs_hb_status, idx_hb_runs_started, idx_hb_trig_hb_created,
  idx_projects_mission, idx_projects_status, idx_goals_project_status,
  idx_goal_tasks_goal_status, idx_tickets_assignee_status,
  idx_tickets_status_priority, idx_tickets_locked, idx_tickets_project,
  idx_tickets_goal, idx_comments_ticket_created,
  idx_activity_ticket_created, idx_plugin_audit_slug

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(conn, name: str) -> bool:
    """Return True if a table already exists on this connection."""
    return sa.inspect(conn).has_table(name)


def _has_index(conn, table: str, index_name: str) -> bool:
    """Return True if an index already exists on the given table."""
    insp = sa.inspect(conn)
    return any(idx["name"] == index_name for idx in insp.get_indexes(table))


def upgrade() -> None:
    conn = op.get_bind()

    # -----------------------------------------------------------------------
    # ORM-managed tables (create only if absent — db.create_all() may have run)
    # -----------------------------------------------------------------------

    if not _has_table(conn, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("username", sa.String(80), unique=True, nullable=False),
            sa.Column("email", sa.String(120), unique=True),
            sa.Column("password_hash", sa.String(128), nullable=False),
            sa.Column("display_name", sa.String(120)),
            sa.Column("avatar_url", sa.String(500)),
            sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("last_login", sa.DateTime(timezone=True)),
            sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("onboarding_state", sa.String(20), nullable=True),
            sa.Column("onboarding_completed_agents_visit", sa.Boolean, nullable=False, server_default="0"),
        )

    if not _has_table(conn, "roles"):
        op.create_table(
            "roles",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(80), unique=True, nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("agent_access_json", sa.Text, server_default='{"mode": "all"}'),
            sa.Column("workspace_folders_json", sa.Text, server_default='{"mode": "all"}'),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )

    if not _has_table(conn, "audit_log"):
        op.create_table(
            "audit_log",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("action", sa.String(100), nullable=False),
            sa.Column("details", sa.Text),
            sa.Column("ip_address", sa.String(50)),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )

    if not _has_table(conn, "login_throttles"):
        op.create_table(
            "login_throttles",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("dimension", sa.String(20), nullable=False),
            sa.Column("lookup_key", sa.String(200), nullable=False),
            sa.Column("fail_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("locked_until", sa.DateTime(timezone=True)),
            sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("dimension", "lookup_key", name="uq_login_throttles_dimension_lookup_key"),
        )

    if not _has_table(conn, "scheduled_tasks"):
        op.create_table(
            "scheduled_tasks",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("task_type", sa.String(50), nullable=False),
            sa.Column("config_json", sa.Text),
            sa.Column("status", sa.String(20), server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    if not _has_table(conn, "triggers"):
        op.create_table(
            "triggers",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("trigger_type", sa.String(50), nullable=False),
            sa.Column("config_json", sa.Text),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default="1"),
            sa.Column("source_plugin", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    if not _has_table(conn, "trigger_executions"):
        op.create_table(
            "trigger_executions",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("trigger_id", sa.Integer, sa.ForeignKey("triggers.id", ondelete="CASCADE")),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("result_json", sa.Text),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("ended_at", sa.DateTime(timezone=True)),
        )

    if not _has_table(conn, "runtime_configs"):
        op.create_table(
            "runtime_configs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("key", sa.String(200), unique=True, nullable=False),
            sa.Column("value", sa.Text),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    if not _has_table(conn, "systems"):
        op.create_table(
            "systems",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("slug", sa.String(100), unique=True, nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("config_json", sa.Text),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )

    if not _has_table(conn, "file_shares"):
        op.create_table(
            "file_shares",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("token", sa.String(64), unique=True, nullable=False),
            sa.Column("file_path", sa.Text, nullable=False),
            sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id")),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("expires_at", sa.DateTime(timezone=True)),
        )

    # Heartbeats domain
    if not _has_table(conn, "heartbeats"):
        op.create_table(
            "heartbeats",
            sa.Column("id", sa.String(100), primary_key=True),
            sa.Column("agent", sa.String(100), nullable=False),
            sa.Column("interval_seconds", sa.Integer, nullable=False),
            sa.Column("max_turns", sa.Integer, nullable=False, server_default="10"),
            sa.Column("timeout_seconds", sa.Integer, nullable=False, server_default="600"),
            sa.Column("lock_timeout_seconds", sa.Integer, nullable=False, server_default="1800"),
            sa.Column("wake_triggers", sa.Text, nullable=False, server_default="[]"),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("goal_id", sa.String(100), nullable=True),
            sa.Column("required_secrets", sa.Text, nullable=True, server_default="[]"),
            sa.Column("decision_prompt", sa.Text, nullable=False),
            sa.Column("source_plugin", sa.Text, nullable=True),
            sa.Column("created_at", sa.String(30)),
            sa.Column("updated_at", sa.String(30)),
        )

    if not _has_table(conn, "heartbeat_runs"):
        op.create_table(
            "heartbeat_runs",
            sa.Column("run_id", sa.String(36), primary_key=True),
            sa.Column("heartbeat_id", sa.String(100), sa.ForeignKey("heartbeats.id", ondelete="CASCADE"), nullable=False),
            sa.Column("trigger_id", sa.String(36), nullable=True),
            sa.Column("started_at", sa.String(30)),
            sa.Column("ended_at", sa.String(30), nullable=True),
            sa.Column("duration_ms", sa.Integer, nullable=True),
            sa.Column("tokens_in", sa.Integer, nullable=True),
            sa.Column("tokens_out", sa.Integer, nullable=True),
            sa.Column("cost_usd", sa.Float, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="running"),
            sa.Column("prompt_preview", sa.Text, nullable=True),
            sa.Column("error", sa.Text, nullable=True),
            sa.Column("triggered_by", sa.String(50), nullable=True),
        )

    if not _has_table(conn, "heartbeat_triggers"):
        op.create_table(
            "heartbeat_triggers",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("heartbeat_id", sa.String(100), sa.ForeignKey("heartbeats.id", ondelete="CASCADE"), nullable=False),
            sa.Column("trigger_type", sa.String(50), nullable=False),
            sa.Column("payload", sa.Text, nullable=True, server_default="{}"),
            sa.Column("created_at", sa.String(30)),
            sa.Column("consumed_at", sa.String(30), nullable=True),
            sa.Column("coalesced_into", sa.String(36), nullable=True),
        )

    # Goals domain
    if not _has_table(conn, "missions"):
        op.create_table(
            "missions",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("slug", sa.String(200), unique=True, nullable=False),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("target_metric", sa.String(100)),
            sa.Column("target_value", sa.Float),
            sa.Column("current_value", sa.Float, nullable=False, server_default="0"),
            sa.Column("due_date", sa.String(20)),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.String(30), nullable=False),
            sa.Column("updated_at", sa.String(30), nullable=False),
        )

    if not _has_table(conn, "projects"):
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("slug", sa.String(200), unique=True, nullable=False),
            sa.Column("mission_id", sa.Integer, sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=True),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("workspace_folder_path", sa.String(500)),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("source_plugin", sa.Text, nullable=True),
            sa.Column("created_at", sa.String(30), nullable=False),
            sa.Column("updated_at", sa.String(30), nullable=False),
        )

    if not _has_table(conn, "goals"):
        op.create_table(
            "goals",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("slug", sa.String(200), unique=True, nullable=False),
            sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("target_metric", sa.String(100)),
            sa.Column("metric_type", sa.String(20), nullable=False, server_default="count"),
            sa.Column("target_value", sa.Float, nullable=False, server_default="1.0"),
            sa.Column("current_value", sa.Float, nullable=False, server_default="0.0"),
            sa.Column("due_date", sa.String(20)),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("source_plugin", sa.Text, nullable=True),
            sa.Column("created_at", sa.String(30), nullable=False),
            sa.Column("updated_at", sa.String(30), nullable=False),
        )

    if not _has_table(conn, "goal_tasks"):
        op.create_table(
            "goal_tasks",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("goal_id", sa.Integer, sa.ForeignKey("goals.id", ondelete="SET NULL"), nullable=True),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("priority", sa.Integer, nullable=False, server_default="3"),
            sa.Column("assignee_agent", sa.String(100)),
            sa.Column("status", sa.String(20), nullable=False, server_default="open"),
            sa.Column("locked_at", sa.String(30)),
            sa.Column("locked_by", sa.String(100)),
            sa.Column("due_date", sa.String(20)),
            sa.Column("source_plugin", sa.Text, nullable=True),
            sa.Column("created_at", sa.String(30), nullable=False),
            sa.Column("updated_at", sa.String(30), nullable=False),
        )

    # Tickets domain
    if not _has_table(conn, "tickets"):
        op.create_table(
            "tickets",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("status", sa.String(20), nullable=False, server_default="open"),
            sa.Column("priority", sa.String(10), nullable=False, server_default="medium"),
            sa.Column("priority_rank", sa.Integer, nullable=False, server_default="2"),
            sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
            sa.Column("goal_id", sa.Integer, sa.ForeignKey("goals.id", ondelete="SET NULL"), nullable=True),
            sa.Column("assignee_agent", sa.String(100), nullable=True),
            sa.Column("locked_at", sa.String(30), nullable=True),
            sa.Column("locked_by", sa.String(100), nullable=True),
            sa.Column("lock_timeout_seconds", sa.Integer, nullable=True),
            sa.Column("created_by", sa.String(100), nullable=False, server_default="davidson"),
            sa.Column("source_agent", sa.String(100), nullable=True),
            sa.Column("source_session_id", sa.String(36), nullable=True),
            sa.Column("source_plugin", sa.Text, nullable=True),
            sa.Column("workspace_path", sa.Text, nullable=True),
            sa.Column("memory_md_path", sa.Text, nullable=True),
            sa.Column("thread_session_id", sa.Text, nullable=True),
            sa.Column("message_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("last_summary_at_message", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.String(30), nullable=False),
            sa.Column("updated_at", sa.String(30), nullable=False),
            sa.Column("resolved_at", sa.String(30), nullable=True),
            sa.CheckConstraint(
                "status IN ('open','in_progress','blocked','review','resolved','closed')",
                name="ck_ticket_status",
            ),
            sa.CheckConstraint(
                "priority IN ('urgent','high','medium','low')",
                name="ck_ticket_priority",
            ),
            sa.CheckConstraint(
                "(locked_at IS NULL AND locked_by IS NULL) OR (locked_at IS NOT NULL AND locked_by IS NOT NULL)",
                name="ck_ticket_lock_consistency",
            ),
        )

    if not _has_table(conn, "ticket_comments"):
        op.create_table(
            "ticket_comments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("ticket_id", sa.String(36), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("author", sa.String(100), nullable=False),
            sa.Column("body", sa.Text, nullable=False),
            sa.Column("mentions", sa.Text),
            sa.Column("created_at", sa.String(30), nullable=False),
        )

    if not _has_table(conn, "ticket_activity"):
        op.create_table(
            "ticket_activity",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("ticket_id", sa.String(36), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("actor", sa.String(100), nullable=False),
            sa.Column("action", sa.String(50), nullable=False),
            sa.Column("payload", sa.Text),
            sa.Column("created_at", sa.String(30), nullable=False),
        )

    # Brain repo domain
    if not _has_table(conn, "brain_repo_configs"):
        op.create_table(
            "brain_repo_configs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("github_token_encrypted", sa.LargeBinary, nullable=True),
            sa.Column("repo_url", sa.String(500), nullable=True),
            sa.Column("repo_owner", sa.String(200), nullable=True),
            sa.Column("repo_name", sa.String(200), nullable=True),
            sa.Column("local_path", sa.String(500), nullable=True),
            sa.Column("last_sync", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sync_enabled", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text, nullable=True),
            sa.Column("pending_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("sync_in_progress", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("sync_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sync_job_kind", sa.String(32), nullable=True),
            sa.Column("cancel_requested", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    # Plugin Wave 2.5 (ORM-managed)
    if not _has_table(conn, "plugin_scan_cache"):
        op.create_table(
            "plugin_scan_cache",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tarball_sha256", sa.String(64), nullable=False),
            sa.Column("scanner_version", sa.String(20), nullable=False),
            sa.Column("verdict", sa.String(10), nullable=False),
            sa.Column("findings_json", sa.Text, nullable=False, server_default="[]"),
            sa.Column("scanned_files", sa.Integer, nullable=False, server_default="0"),
            sa.Column("llm_augmented", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("tarball_sha256", "scanner_version", name="uq_scan_cache_sha_ver"),
        )

    if not _has_table(conn, "plugin_audit_log"):
        op.create_table(
            "plugin_audit_log",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("slug", sa.String(200), nullable=False),
            sa.Column("event", sa.String(50), nullable=False),
            sa.Column("verdict", sa.String(10), nullable=True),
            sa.Column("actor_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("actor_username", sa.String(80), nullable=True),
            sa.Column("detail_json", sa.Text, nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )

    # -----------------------------------------------------------------------
    # Non-ORM tables (not in models.py — executescript-only on SQLite)
    # -----------------------------------------------------------------------

    if not _has_table(conn, "plugins_installed"):
        op.create_table(
            "plugins_installed",
            sa.Column("id", sa.Text, primary_key=True),
            sa.Column("slug", sa.Text, nullable=False, unique=True),
            sa.Column("name", sa.Text, nullable=False),
            sa.Column("version", sa.Text, nullable=False),
            sa.Column("tier", sa.Text, nullable=False, server_default="essential"),
            sa.Column("source_type", sa.Text, nullable=True),
            sa.Column("source_url", sa.Text, nullable=True),
            sa.Column("source_ref", sa.Text, nullable=True),
            sa.Column("installed_at", sa.Text, nullable=False),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default="1"),
            sa.Column("manifest_json", sa.Text, nullable=True),
            sa.Column("install_sha256", sa.Text, nullable=True),
            sa.Column("status", sa.Text, nullable=False, server_default="active"),
            sa.Column("last_error", sa.Text, nullable=True),
            sa.Column("capabilities_disabled", sa.Text, nullable=False, server_default="{}"),
            sa.Column("source_plugin", sa.Text, nullable=True),
            sa.CheckConstraint(
                "status IN ('active','disabled','broken','installing','uninstalling')",
                name="ck_plugins_installed_status",
            ),
        )

    if not _has_table(conn, "plugin_hook_circuit_state"):
        op.create_table(
            "plugin_hook_circuit_state",
            sa.Column("plugin_slug", sa.Text, nullable=False, primary_key=True),
            sa.Column("handler_path", sa.Text, nullable=False, primary_key=True),
            sa.Column("failures_json", sa.Text, nullable=False, server_default="[]"),
            sa.Column("disabled_until", sa.Text, nullable=True),
            sa.Column("total_invocations", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_failures", sa.Integer, nullable=False, server_default="0"),
            sa.Column("last_failure_at", sa.Text, nullable=True),
        )

    if not _has_table(conn, "integration_health_cache"):
        op.create_table(
            "integration_health_cache",
            sa.Column("plugin_slug", sa.Text, nullable=False, primary_key=True),
            sa.Column("integration_slug", sa.Text, nullable=False, primary_key=True),
            sa.Column("last_status", sa.Text, nullable=True),
            sa.Column("last_checked_at", sa.Text, nullable=True),
            sa.Column("last_error", sa.Text, nullable=True),
        )

    if not _has_table(conn, "plugin_orphans"):
        op.create_table(
            "plugin_orphans",
            sa.Column("id", sa.Text, primary_key=True),
            sa.Column("slug", sa.Text, nullable=False),
            sa.Column("tablename", sa.Text, nullable=False),
            sa.Column("orphaned_at", sa.Text, nullable=False),
            sa.Column("orphaned_by_user_id", sa.Integer, nullable=True),
            sa.Column("original_plugin_version", sa.Text, nullable=True),
            sa.Column("original_sha256", sa.Text, nullable=True),
            sa.Column("original_publisher_url", sa.Text, nullable=True),
            sa.Column("recovered_at", sa.Text, nullable=True),
            sa.UniqueConstraint("slug", "tablename", name="uq_plugin_orphans_slug_table"),
        )

    if not _has_table(conn, "knowledge_connections"):
        op.create_table(
            "knowledge_connections",
            sa.Column("id", sa.Text, primary_key=True),
            sa.Column("slug", sa.Text, nullable=False, unique=True),
            sa.Column("name", sa.Text, nullable=False),
            sa.Column("connection_string_encrypted", sa.LargeBinary, nullable=True),
            sa.Column("host", sa.Text, nullable=True),
            sa.Column("port", sa.Integer, nullable=True),
            sa.Column("database_name", sa.Text, nullable=True),
            sa.Column("username", sa.Text, nullable=True),
            sa.Column("ssl_mode", sa.Text, nullable=True),
            sa.Column("status", sa.Text, nullable=True, server_default="disconnected"),
            sa.Column("schema_version", sa.Text, nullable=True),
            sa.Column("pgvector_version", sa.Text, nullable=True),
            sa.Column("postgres_version", sa.Text, nullable=True),
            sa.Column("last_health_check", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if not _has_table(conn, "knowledge_connection_events"):
        op.create_table(
            "knowledge_connection_events",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("connection_id", sa.Text, sa.ForeignKey("knowledge_connections.id", ondelete="CASCADE"), nullable=True),
            sa.Column("event_type", sa.Text, nullable=True),
            sa.Column("details", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if not _has_table(conn, "knowledge_api_keys"):
        op.create_table(
            "knowledge_api_keys",
            sa.Column("id", sa.Text, primary_key=True),
            sa.Column("name", sa.Text, nullable=True),
            sa.Column("prefix", sa.Text, nullable=False),
            sa.Column("token_hash", sa.Text, nullable=False),
            sa.Column("connection_id", sa.Text, nullable=False),
            sa.Column("space_ids", sa.Text, nullable=False, server_default="[]"),
            sa.Column("scopes", sa.Text, nullable=False, server_default='["read"]'),
            sa.Column("rate_limit_per_min", sa.Integer, nullable=False, server_default="60"),
            sa.Column("rate_limit_per_day", sa.Integer, nullable=False, server_default="10000"),
            sa.Column("created_at", sa.Text, nullable=False),
            sa.Column("last_used_at", sa.Text, nullable=True),
            sa.Column("expires_at", sa.Text, nullable=True),
        )

    # -----------------------------------------------------------------------
    # Performance indexes (ORM tables — not created by db.create_all())
    # -----------------------------------------------------------------------
    _idx: list[tuple[str, str, list[str]]] = [
        ("idx_hb_runs_hb_status", "heartbeat_runs", ["heartbeat_id", "status"]),
        ("idx_hb_runs_started", "heartbeat_runs", ["started_at"]),
        ("idx_hb_trig_hb_created", "heartbeat_triggers", ["heartbeat_id", "created_at"]),
        ("idx_projects_mission", "projects", ["mission_id"]),
        ("idx_projects_status", "projects", ["status"]),
        ("idx_goals_project_status", "goals", ["project_id", "status"]),
        ("idx_goal_tasks_goal_status", "goal_tasks", ["goal_id", "status"]),
        ("idx_tickets_assignee_status", "tickets", ["assignee_agent", "status"]),
        ("idx_tickets_status_priority", "tickets", ["status", "priority_rank"]),
        ("idx_tickets_locked", "tickets", ["locked_at"]),
        ("idx_tickets_project", "tickets", ["project_id"]),
        ("idx_tickets_goal", "tickets", ["goal_id"]),
        ("idx_comments_ticket_created", "ticket_comments", ["ticket_id", "created_at"]),
        ("idx_activity_ticket_created", "ticket_activity", ["ticket_id", "created_at"]),
        ("idx_plugins_status", "plugins_installed", ["status"]),
        ("idx_hook_cb_disabled", "plugin_hook_circuit_state", ["disabled_until"]),
        ("idx_plugin_orphans_slug", "plugin_orphans", ["slug"]),
        ("idx_kconn_status", "knowledge_connections", ["status"]),
        ("idx_kconn_events_conn", "knowledge_connection_events", ["connection_id", "created_at"]),
        ("idx_kak_prefix", "knowledge_api_keys", ["prefix"]),
        ("idx_plugin_audit_slug", "plugin_audit_log", ["slug"]),
        ("idx_brain_repo_user", "brain_repo_configs", ["user_id"]),
    ]
    for idx_name, tbl, cols in _idx:
        if _has_table(conn, tbl) and not _has_index(conn, tbl, idx_name):
            op.create_index(idx_name, tbl, cols)


def downgrade() -> None:
    # Drop in reverse FK order.
    # We only drop non-ORM tables; ORM tables are managed by db.create_all()
    # and should not be dropped here (they may contain production data).
    conn = op.get_bind()

    for idx_name, tbl, _ in [
        ("idx_plugin_audit_slug", "plugin_audit_log", None),
        ("idx_brain_repo_user", "brain_repo_configs", None),
        ("idx_kak_prefix", "knowledge_api_keys", None),
        ("idx_kconn_events_conn", "knowledge_connection_events", None),
        ("idx_kconn_status", "knowledge_connections", None),
        ("idx_plugin_orphans_slug", "plugin_orphans", None),
        ("idx_hook_cb_disabled", "plugin_hook_circuit_state", None),
        ("idx_plugins_status", "plugins_installed", None),
        ("idx_activity_ticket_created", "ticket_activity", None),
        ("idx_comments_ticket_created", "ticket_comments", None),
        ("idx_tickets_goal", "tickets", None),
        ("idx_tickets_project", "tickets", None),
        ("idx_tickets_locked", "tickets", None),
        ("idx_tickets_status_priority", "tickets", None),
        ("idx_tickets_assignee_status", "tickets", None),
        ("idx_goal_tasks_goal_status", "goal_tasks", None),
        ("idx_goals_project_status", "goals", None),
        ("idx_projects_status", "projects", None),
        ("idx_projects_mission", "projects", None),
        ("idx_hb_trig_hb_created", "heartbeat_triggers", None),
        ("idx_hb_runs_started", "heartbeat_runs", None),
        ("idx_hb_runs_hb_status", "heartbeat_runs", None),
    ]:
        if _has_table(conn, tbl) and _has_index(conn, tbl, idx_name):
            op.drop_index(idx_name, table_name=tbl)

    for tbl in [
        "knowledge_api_keys",
        "knowledge_connection_events",
        "knowledge_connections",
        "plugin_orphans",
        "integration_health_cache",
        "plugin_hook_circuit_state",
        "plugins_installed",
    ]:
        if _has_table(conn, tbl):
            op.drop_table(tbl)
