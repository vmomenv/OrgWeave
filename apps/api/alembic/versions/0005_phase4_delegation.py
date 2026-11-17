"""Phase 4 delegation: agent policies and delegation records."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase4_delegation"
down_revision: str | None = "0004_phase3_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
TZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column("max_delegation_depth", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "agent_configs",
        sa.Column(
            "allowed_agent_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[\"*\"]'::jsonb"),
        ),
    )

    op.create_table(
        "agent_delegations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("parent_run_id", UUID, nullable=False),
        sa.Column("parent_session_id", UUID, nullable=False),
        sa.Column("parent_agent_id", UUID, nullable=False),
        sa.Column("child_agent_id", UUID, nullable=False),
        sa.Column("child_session_id", UUID, nullable=False, unique=True),
        sa.Column("child_run_id", UUID),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("summary", sa.Text()),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("started_at", TZ),
        sa.Column("completed_at", TZ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            ondelete="CASCADE",
            name="fk_delegation_parent_run_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_session_id"],
            ["agent_sessions.tenant_id", "agent_sessions.id"],
            ondelete="CASCADE",
            name="fk_delegation_parent_session_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "child_session_id"],
            ["agent_sessions.tenant_id", "agent_sessions.id"],
            ondelete="CASCADE",
            name="fk_delegation_child_session_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_agent_id"],
            ["agent_configs.tenant_id", "agent_configs.id"],
            ondelete="CASCADE",
            name="fk_delegation_parent_agent_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "child_agent_id"],
            ["agent_configs.tenant_id", "agent_configs.id"],
            ondelete="CASCADE",
            name="fk_delegation_child_agent_same_tenant",
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed','cancelled')",
            name="ck_delegation_status",
        ),
    )
    op.create_index(
        "ix_delegation_parent_session", "agent_delegations", ["tenant_id", "parent_session_id"]
    )
    op.create_index(
        "ix_delegation_child_agent", "agent_delegations", ["tenant_id", "child_agent_id"]
    )

    op.execute("ALTER TABLE agent_delegations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_delegations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON agent_delegations "
        "USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) "
        "WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON agent_delegations TO orgweave_app")


def downgrade() -> None:
    op.drop_table("agent_delegations")
    op.drop_column("agent_configs", "allowed_agent_ids")
    op.drop_column("agent_configs", "max_delegation_depth")
