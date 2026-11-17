"""Phase 1: identity, tenants, organization, RBAC, invitations, audit + RLS.

Revision ID: 0002_phase1
Revises: 0001_phase0
Create Date: 2026-11-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_phase1"
down_revision: str | None = "0001_phase0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
TZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")

TENANT_POLICY = """
    {table} = nullif(current_setting('app.tenant_id', true), '')::uuid
"""


def _tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING ({TENANT_POLICY.format(table='tenant_id')}) "
        f"WITH CHECK ({TENANT_POLICY.format(table='tenant_id')})"
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("updated_at", TZ, nullable=False, server_default=NOW),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("revoked_at", TZ),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.create_table(
        "tenants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("updated_at", TZ, nullable=False, server_default=NOW),
    )

    op.create_table(
        "tenant_memberships",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),
        sa.CheckConstraint(
            "status IN ('active', 'invited', 'suspended')", name="ck_membership_status"
        ),
    )
    op.create_index("ix_membership_user", "tenant_memberships", ["user_id"])

    op.create_table(
        "departments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("parent_id", UUID),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("updated_at", TZ, nullable=False, server_default=NOW),
        sa.UniqueConstraint("tenant_id", "id", name="uq_department_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_department_tenant_name"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["departments.tenant_id", "departments.id"],
            ondelete="RESTRICT",
            name="fk_department_parent_same_tenant",
        ),
    )
    op.create_index("ix_department_tenant", "departments", ["tenant_id"])

    op.create_table(
        "members",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("member_type", sa.String(10), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("title", sa.String(120)),
        sa.Column("bio", sa.Text()),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("department_id", UUID),
        sa.Column("manager_id", UUID),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("ai_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.Column("updated_at", TZ, nullable=False, server_default=NOW),
        sa.UniqueConstraint("tenant_id", "id", name="uq_member_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_member_tenant_user"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["departments.tenant_id", "departments.id"],
            ondelete="RESTRICT",
            name="fk_member_department_same_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "manager_id"],
            ["members.tenant_id", "members.id"],
            ondelete="RESTRICT",
            name="fk_member_manager_same_tenant",
        ),
        sa.CheckConstraint("member_type IN ('human', 'ai')", name="ck_member_type"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_member_status"),
        sa.CheckConstraint(
            "(member_type = 'human' AND user_id IS NOT NULL) OR "
            "(member_type = 'ai' AND user_id IS NULL)",
            name="ck_member_identity",
        ),
    )
    op.create_index("ix_member_tenant_type", "members", ["tenant_id", "member_type"])
    op.create_index("ix_member_department", "members", ["tenant_id", "department_id"])

    op.create_table(
        "permissions",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table(
        "roles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("key", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", UUID, sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "permission_key",
            sa.String(80),
            sa.ForeignKey("permissions.key", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "member_roles",
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("member_id", UUID, primary_key=True),
        sa.Column("role_id", UUID, sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "member_id"],
            ["members.tenant_id", "members.id"],
            ondelete="CASCADE",
            name="fk_member_role_member_same_tenant",
        ),
    )

    op.create_table(
        "invitations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("role_key", sa.String(40), nullable=False, server_default="member"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("invited_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("accepted_at", TZ),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_invitation_status",
        ),
    )
    op.create_index("ix_invitation_tenant", "invitations", ["tenant_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE")),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", UUID),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", UUID),
        sa.Column("result", sa.String(20), nullable=False, server_default="success"),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("created_at", TZ, nullable=False, server_default=NOW),
    )
    op.create_index("ix_audit_tenant_created", "audit_logs", ["tenant_id", "created_at"])
    op.create_index("ix_audit_actor", "audit_logs", ["actor_id"])

    # ------------------------------------------------------------------
    # Seed global permissions and role templates.
    # ------------------------------------------------------------------
    op.execute(
        """
        INSERT INTO permissions (key, description) VALUES
          ('tenant.manage', 'Manage tenant settings and deletion'),
          ('member.read', 'View members and departments'),
          ('member.manage', 'Create, update and disable members'),
          ('department.manage', 'Create, update and delete departments'),
          ('role.read', 'View roles and permissions'),
          ('role.manage', 'Assign roles to members'),
          ('invitation.manage', 'Invite members'),
          ('audit.read', 'Read audit logs')
        """
    )
    op.execute(
        """
        INSERT INTO roles (id, key, name, description, is_system) VALUES
          (gen_random_uuid(), 'owner', 'Owner', 'Full tenant control', true),
          (gen_random_uuid(), 'admin', 'Admin', 'Manage organization and members', true),
          (gen_random_uuid(), 'member', 'Member', 'Standard organization member', true)
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_key)
        SELECT r.id, p.key FROM roles r CROSS JOIN permissions p WHERE r.key = 'owner'
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_key)
        SELECT r.id, p.key FROM roles r CROSS JOIN permissions p
        WHERE r.key = 'admin' AND p.key <> 'tenant.manage'
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_key)
        SELECT r.id, p.key FROM roles r CROSS JOIN permissions p
        WHERE r.key = 'member' AND p.key IN ('member.read', 'role.read')
        """
    )

    # ------------------------------------------------------------------
    # RLS for every tenant-scoped table.
    # ------------------------------------------------------------------
    for table in (
        "departments",
        "members",
        "member_roles",
        "invitations",
        "audit_logs",
    ):
        _tenant_rls(table)

    # Membership must be readable by its own user before a tenant is selected.
    op.execute("ALTER TABLE tenant_memberships ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_memberships FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_membership_isolation ON tenant_memberships
        USING (
            tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
            OR user_id = nullif(current_setting('app.user_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )

    # Audit logs may be global (login events) but a user only sees their own.
    op.execute("DROP POLICY tenant_isolation ON audit_logs")
    op.execute(
        """
        CREATE POLICY audit_isolation ON audit_logs
        USING (
            (tenant_id IS NOT NULL
             AND tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
            OR (tenant_id IS NULL
                AND actor_id = nullif(current_setting('app.user_id', true), '')::uuid)
        )
        WITH CHECK (
            tenant_id IS NULL
            OR tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )

    # ------------------------------------------------------------------
    # SECURITY DEFINER bootstrap functions (tenant creation, invitations).
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION orgweave_create_tenant(
            p_user_id uuid,
            p_name text,
            p_slug text,
            p_display_name text
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DECLARE
            v_tenant uuid;
            v_member uuid;
            v_owner uuid;
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM users WHERE id = p_user_id AND is_active
            ) THEN
                RAISE EXCEPTION 'user_not_found';
            END IF;

            INSERT INTO tenants (id, name, slug)
            VALUES (gen_random_uuid(), p_name, p_slug)
            RETURNING id INTO v_tenant;

            INSERT INTO tenant_memberships (id, tenant_id, user_id, status)
            VALUES (gen_random_uuid(), v_tenant, p_user_id, 'active');

            INSERT INTO members (
                id, tenant_id, member_type, user_id, display_name, status, ai_enabled
            ) VALUES (
                gen_random_uuid(), v_tenant, 'human', p_user_id, p_display_name, 'active', false
            ) RETURNING id INTO v_member;

            SELECT id INTO v_owner FROM roles WHERE key = 'owner';
            IF v_owner IS NULL THEN
                RAISE EXCEPTION 'owner_role_missing';
            END IF;

            INSERT INTO member_roles (tenant_id, member_id, role_id)
            VALUES (v_tenant, v_member, v_owner);

            INSERT INTO audit_logs (
                id, tenant_id, actor_type, actor_id, action, resource_type, resource_id, result
            ) VALUES (
                gen_random_uuid(), v_tenant, 'user', p_user_id,
                'tenant.created', 'tenant', v_tenant, 'success'
            );
            RETURN v_tenant;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION orgweave_accept_invitation(
            p_token_hash text,
            p_user_id uuid
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DECLARE
            v_inv invitations%ROWTYPE;
            v_user users%ROWTYPE;
            v_member uuid;
            v_role uuid;
        BEGIN
            SELECT * INTO v_user FROM users WHERE id = p_user_id AND is_active;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'user_not_found';
            END IF;

            SELECT * INTO v_inv FROM invitations
            WHERE token_hash = p_token_hash FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'invitation_not_found';
            END IF;
            IF v_inv.status <> 'pending' THEN
                RAISE EXCEPTION 'invitation_not_pending';
            END IF;
            IF v_inv.expires_at < now() THEN
                UPDATE invitations SET status = 'expired' WHERE id = v_inv.id;
                RAISE EXCEPTION 'invitation_expired';
            END IF;
            IF lower(v_user.email) <> lower(v_inv.email) THEN
                RAISE EXCEPTION 'invitation_email_mismatch';
            END IF;

            INSERT INTO tenant_memberships (id, tenant_id, user_id, status)
            VALUES (gen_random_uuid(), v_inv.tenant_id, p_user_id, 'active')
            ON CONFLICT (tenant_id, user_id) DO UPDATE SET status = 'active';

            INSERT INTO members (
                id, tenant_id, member_type, user_id, display_name, status, ai_enabled
            ) VALUES (
                gen_random_uuid(), v_inv.tenant_id, 'human', p_user_id,
                v_user.display_name, 'active', false
            )
            ON CONFLICT (tenant_id, user_id) DO UPDATE
              SET display_name = EXCLUDED.display_name,
                  status = 'active'
            RETURNING id INTO v_member;

            SELECT id INTO v_role FROM roles WHERE key = v_inv.role_key;
            IF v_role IS NULL THEN
                SELECT id INTO v_role FROM roles WHERE key = 'member';
            END IF;
            INSERT INTO member_roles (tenant_id, member_id, role_id)
            VALUES (v_inv.tenant_id, v_member, v_role)
            ON CONFLICT DO NOTHING;

            UPDATE invitations
            SET status = 'accepted', accepted_at = now()
            WHERE id = v_inv.id;

            INSERT INTO audit_logs (
                id, tenant_id, actor_type, actor_id, action, resource_type, resource_id, result
            ) VALUES (
                gen_random_uuid(), v_inv.tenant_id, 'user', p_user_id,
                'invitation.accepted', 'invitation', v_inv.id, 'success'
            );
            RETURN v_inv.tenant_id;
        END;
        $$;
        """
    )

    op.execute("REVOKE ALL ON FUNCTION orgweave_create_tenant(uuid, text, text, text) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION orgweave_accept_invitation(text, uuid) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION orgweave_create_tenant(uuid, text, text, text) TO orgweave_app"
    )
    op.execute("GRANT EXECUTE ON FUNCTION orgweave_accept_invitation(text, uuid) TO orgweave_app")

    # Explicit grants in addition to ALTER DEFAULT PRIVILEGES.
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON
          users, refresh_tokens, tenants, tenant_memberships, departments, members,
          permissions, roles, role_permissions, member_roles, invitations, audit_logs
        TO orgweave_app
        """
    )
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO orgweave_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS orgweave_accept_invitation(text, uuid)")
    op.execute("DROP FUNCTION IF EXISTS orgweave_create_tenant(uuid, text, text, text)")
    op.drop_table("audit_logs")
    op.drop_table("invitations")
    op.drop_table("member_roles")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
    op.drop_table("members")
    op.drop_table("departments")
    op.drop_table("tenant_memberships")
    op.drop_table("tenants")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
