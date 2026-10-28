"""classrooms memberships channels

Revision ID: 19cccd327af7
Revises: 4b95658494dc
Create Date: 2026-10-28 22:28:00.833146

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "19cccd327af7"
down_revision: str | Sequence[str] | None = "4b95658494dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "classrooms",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("invite_code", sa.String(length=16), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classrooms")),
        sa.UniqueConstraint("invite_code", name=op.f("uq_classrooms_invite_code")),
    )
    op.create_table(
        "channels",
        sa.Column("classroom_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name=op.f("fk_channels_classroom_id_classrooms"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channels")),
        sa.UniqueConstraint("classroom_id", "name", name=op.f("uq_channels_classroom_id_name")),
    )
    op.create_index(op.f("ix_channels_classroom_id"), "channels", ["classroom_id"], unique=False)
    op.create_table(
        "memberships",
        sa.Column("classroom_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role", sa.Enum("member", "moderator", "owner", name="member_role"), nullable=False
        ),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["classroom_id"],
            ["classrooms.id"],
            name=op.f("fk_memberships_classroom_id_classrooms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_memberships_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("classroom_id", "user_id", name=op.f("pk_memberships")),
    )
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_table("memberships")
    op.drop_index(op.f("ix_channels_classroom_id"), table_name="channels")
    op.drop_table("channels")
    op.drop_table("classrooms")
    sa.Enum(name="member_role").drop(op.get_bind(), checkfirst=True)
