"""Phase 2 chat migration: groups, group members, messages, mentions, attachments."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_phase2_chat"
down_revision: str | None = "0002_phase1"
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
        "groups",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(120)),
        sa.Column("group_type", sa.String(20), nullable=False, server_default="channel"),
        sa.Column("created_by_member_id", UUID),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("updated_at", TZ, nullable=False, server_default=NOW),
        sa.UniqueConstraint("tenant_id", "id", name="uq_group_tenant_id_id"),
        sa.CheckConstraint("group_type IN ('channel', 'direct')", name="ck_group_type"),
    )
    op.create_index("ix_group_tenant", "groups", ["tenant_id"])

    op.create_table(
        "group_members",
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("group_id", UUID, primary_key=True),
        sa.Column("member_id", UUID, primary_key=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("joined_at", TZ, nullable=False, server_default=NOW),
        sa.Column("last_read_at", TZ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "group_id"],
            ["groups.tenant_id", "groups.id"],
            ondelete="CASCADE",
            name="fk_group_member_group_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "member_id"],
            ["members.tenant_id", "members.id"],
            ondelete="CASCADE",
            name="fk_group_member_member_same_tenant",
        ),
        sa.CheckConstraint("role IN ('owner', 'member')", name="ck_group_member_role"),
    )

    op.create_table(
        "messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("group_id", UUID, nullable=False),
        sa.Column("sender_member_id", UUID, nullable=False),
        sa.Column("parent_message_id", UUID),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("edited_at", TZ),
        sa.Column("deleted_at", TZ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "group_id"],
            ["groups.tenant_id", "groups.id"],
            ondelete="CASCADE",
            name="fk_message_group_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sender_member_id"],
            ["members.tenant_id", "members.id"],
            ondelete="RESTRICT",
            name="fk_message_sender_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_message_id"],
            ["messages.tenant_id", "messages.id"],
            ondelete="RESTRICT",
            name="fk_message_parent_same_tenant",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_message_tenant_id_id"),
    )
    op.create_index("ix_message_group_created", "messages", ["tenant_id", "group_id", "created_at"])

    op.create_table(
        "message_mentions",
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("message_id", UUID, primary_key=True),
        sa.Column("member_id", UUID, primary_key=True),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
            ondelete="CASCADE",
            name="fk_mention_message_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "member_id"],
            ["members.tenant_id", "members.id"],
            ondelete="CASCADE",
            name="fk_mention_member_same_tenant",
        ),
    )

    op.create_table(
        "attachments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("group_id", UUID, nullable=False),
        sa.Column("message_id", UUID),
        sa.Column("uploader_member_id", UUID, nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False, unique=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.ForeignKeyConstraint(
            ["tenant_id", "group_id"],
            ["groups.tenant_id", "groups.id"],
            ondelete="CASCADE",
            name="fk_attachment_group_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
            ondelete="CASCADE",
            name="fk_attachment_message_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "uploader_member_id"],
            ["members.tenant_id", "members.id"],
            ondelete="RESTRICT",
            name="fk_attachment_uploader_same_tenant",
        ),
    )
    op.create_index("ix_attachment_group", "attachments", ["tenant_id", "group_id"])

    for table in ("groups", "group_members", "messages", "message_mentions", "attachments"):
        _rls(table)

    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON
          groups, group_members, messages, message_mentions, attachments
        TO orgweave_app
        """
    )


def downgrade() -> None:
    op.drop_table("attachments")
    op.drop_table("message_mentions")
    op.drop_table("messages")
    op.drop_table("group_members")
    op.drop_table("groups")
