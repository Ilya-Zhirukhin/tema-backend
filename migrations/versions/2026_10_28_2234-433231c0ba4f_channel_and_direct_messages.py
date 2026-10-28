"""channel and direct messages

Revision ID: 433231c0ba4f
Revises: 19cccd327af7
Create Date: 2026-10-28 22:34:57.065749

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "433231c0ba4f"
down_revision: str | Sequence[str] | None = "19cccd327af7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "direct_messages",
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["users.id"],
            name=op.f("fk_direct_messages_recipient_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["users.id"],
            name=op.f("fk_direct_messages_sender_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_direct_messages")),
    )
    op.create_index(
        "ix_direct_messages_pair",
        "direct_messages",
        ["sender_id", "recipient_id", "id"],
        unique=False,
    )
    op.create_index(
        "ix_direct_messages_recipient_unread",
        "direct_messages",
        ["recipient_id", "read_at"],
        unique=False,
    )
    op.create_table(
        "messages",
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_messages_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_messages_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["messages.id"],
            name=op.f("fk_messages_parent_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index("ix_messages_channel_id_id", "messages", ["channel_id", "id"], unique=False)
    op.create_index(op.f("ix_messages_parent_id"), "messages", ["parent_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_messages_parent_id"), table_name="messages")
    op.drop_index("ix_messages_channel_id_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_direct_messages_recipient_unread", table_name="direct_messages")
    op.drop_index("ix_direct_messages_pair", table_name="direct_messages")
    op.drop_table("direct_messages")
