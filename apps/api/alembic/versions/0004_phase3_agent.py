"""Phase 3 Agent Runtime schema."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_phase3_agent"
down_revision: str | None = "0003_phase2_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
TZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) "
        f"WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )


def upgrade() -> None:
    op.create_table(
        "agent_configs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("member_id", UUID, nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("model_alias", sa.String(120), nullable=False, server_default="orgweave-default"),
        sa.Column("temperature", sa.Numeric(3, 2), nullable=False, server_default="0.20"),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False, server_default="1024"),
        sa.Column("max_steps", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("max_duration_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("token_budget", sa.Integer(), nullable=False, server_default="50000"),
        sa.Column("cost_budget_usd", sa.Numeric(10, 4), nullable=False, server_default="5"),
        sa.Column("max_tool_calls", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("max_consecutive_failures", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "allowed_tools",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("memory_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("updated_at", TZ, nullable=False, server_default=NOW),
        sa.UniqueConstraint("tenant_id", "member_id", name="uq_agent_tenant_member"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_agent_tenant_id_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "member_id"],
            ["members.tenant_id", "members.id"],
            ondelete="CASCADE",
            name="fk_agent_member_same_tenant",
        ),
        sa.CheckConstraint("max_steps BETWEEN 1 AND 100", name="ck_agent_max_steps"),
    )
    op.create_index("ix_agent_tenant", "agent_configs", ["tenant_id"])

    op.create_table(
        "agent_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("agent_id", UUID, nullable=False),
        sa.Column("member_id", UUID, nullable=False),
        sa.Column("parent_session_id", UUID),
        sa.Column("task_id", UUID),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("control_mode", sa.String(20), nullable=False, server_default="autonomous"),
        sa.Column("title", sa.String(200), nullable=False, server_default="会话"),
        sa.Column("context_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("model", sa.String(120), nullable=False, server_default=""),
        sa.Column("token_usage", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_usage", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("updated_at", TZ, nullable=False, server_default=NOW),
        sa.Column("started_at", TZ),
        sa.Column("completed_at", TZ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_session_tenant_id_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_configs.tenant_id", "agent_configs.id"],
            ondelete="CASCADE",
            name="fk_session_agent_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_session_id"],
            ["agent_sessions.tenant_id", "agent_sessions.id"],
            ondelete="RESTRICT",
            name="fk_session_parent_same_tenant",
        ),
        sa.CheckConstraint(
            "status IN ('active','paused','completed','failed','killed','waiting_approval')",
            name="ck_session_status",
        ),
        sa.CheckConstraint(
            "control_mode IN ('autonomous','guide','takeover')", name="ck_session_control"
        ),
    )
    op.create_index("ix_session_tenant_agent", "agent_sessions", ["tenant_id", "agent_id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("output", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("steps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_usage", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_usage", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column(
            "limits", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("started_at", TZ),
        sa.Column("completed_at", TZ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_run_tenant_id_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "session_id"],
            ["agent_sessions.tenant_id", "agent_sessions.id"],
            ondelete="CASCADE",
            name="fk_run_session_same_tenant",
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed','cancelled','timeout')",
            name="ck_run_status",
        ),
    )
    op.create_index("ix_run_tenant_session", "agent_runs", ["tenant_id", "session_id"])

    op.create_table(
        "agent_session_messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("tool_calls", postgresql.JSONB()),
        sa.Column("tool_call_id", sa.String(120)),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["tenant_id", "session_id"],
            ["agent_sessions.tenant_id", "agent_sessions.id"],
            ondelete="CASCADE",
            name="fk_session_message_session_same_tenant",
        ),
        sa.CheckConstraint(
            "role IN ('system','user','assistant','tool')", name="ck_session_message_role"
        ),
    )
    op.create_index(
        "ix_session_message_session",
        "agent_session_messages",
        ["tenant_id", "session_id", "created_at"],
    )

    op.create_table(
        "agent_tool_calls",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("tool_call_id", sa.String(120), nullable=False),
        sa.Column("tool_name", sa.String(120), nullable=False),
        sa.Column(
            "arguments", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("started_at", TZ),
        sa.Column("completed_at", TZ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            ondelete="CASCADE",
            name="fk_tool_call_run_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "session_id"],
            ["agent_sessions.tenant_id", "agent_sessions.id"],
            ondelete="CASCADE",
            name="fk_tool_call_session_same_tenant",
        ),
        sa.CheckConstraint(
            "status IN ('requested','running','completed','failed','denied')",
            name="ck_tool_call_status",
        ),
    )
    op.create_index("ix_tool_call_run", "agent_tool_calls", ["tenant_id", "run_id"])

    op.create_table(
        "agent_memories",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("agent_id", UUID, nullable=False),
        sa.Column("memory_type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("source_session_id", UUID),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("last_accessed_at", TZ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_configs.tenant_id", "agent_configs.id"],
            ondelete="CASCADE",
            name="fk_memory_agent_same_tenant",
        ),
        sa.CheckConstraint(
            "memory_type IN ('profile','semantic','episodic','task','procedural')",
            name="ck_memory_type",
        ),
        sa.CheckConstraint("importance BETWEEN 1 AND 5", name="ck_memory_importance"),
    )
    op.create_index(
        "ix_memory_tenant_agent", "agent_memories", ["tenant_id", "agent_id", "created_at"]
    )

    for table in (
        "agent_configs",
        "agent_sessions",
        "agent_runs",
        "agent_session_messages",
        "agent_tool_calls",
        "agent_memories",
    ):
        _rls(table)

    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON
          agent_configs, agent_sessions, agent_runs, agent_session_messages,
          agent_tool_calls, agent_memories
        TO orgweave_app
        """
    )


def downgrade() -> None:
    op.drop_table("agent_memories")
    op.drop_table("agent_tool_calls")
    op.drop_table("agent_session_messages")
    op.drop_table("agent_runs")
    op.drop_table("agent_sessions")
    op.drop_table("agent_configs")
