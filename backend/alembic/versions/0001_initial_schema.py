"""Initial schema: users, files, file_hashes, duplicate_groups, file_metadata, deletion_history, audit_logs

Revision ID: 0001
Revises:
Create Date: 2026-10-06 00:00:00
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DT = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", DT, nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "duplicate_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("total_size", sa.BigInteger(), nullable=False),
        sa.Column("potential_savings", sa.BigInteger(), nullable=False),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.UniqueConstraint("owner_id", "sha256", name="uq_duplicate_groups_owner_sha256"),
    )
    op.create_index("ix_duplicate_groups_owner_id", "duplicate_groups", ["owner_id"])
    op.create_index("ix_duplicate_groups_sha256", "duplicate_groups", ["sha256"])

    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(500), nullable=False),
        sa.Column("extension", sa.String(20), nullable=False),
        sa.Column("content_type", sa.String(150), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("is_protected", sa.Boolean(), nullable=False),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False),
        sa.Column(
            "duplicate_group_id",
            sa.Integer(),
            sa.ForeignKey("duplicate_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("uploaded_at", DT, nullable=False),
        sa.Column("processed_at", DT, nullable=True),
    )
    op.create_index("ix_files_owner_id", "files", ["owner_id"])
    op.create_index("ix_files_extension", "files", ["extension"])
    op.create_index("ix_files_category", "files", ["category"])
    op.create_index("ix_files_size_bytes", "files", ["size_bytes"])
    op.create_index("ix_files_status", "files", ["status"])
    op.create_index("ix_files_is_duplicate", "files", ["is_duplicate"])
    op.create_index("ix_files_duplicate_group_id", "files", ["duplicate_group_id"])
    op.create_index("ix_files_owner_uploaded", "files", ["owner_id", "uploaded_at"])

    op.create_table(
        "file_hashes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("algorithm", sa.String(20), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("computed_at", DT, nullable=False),
        sa.UniqueConstraint("file_id"),
    )
    op.create_index("ix_file_hashes_sha256", "file_hashes", ["sha256"])

    op.create_table(
        "file_metadata",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("detected_mime", sa.String(150), nullable=True),
        sa.Column("extension", sa.String(20), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.UniqueConstraint("file_id"),
    )

    op.create_table(
        "deletion_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_freed", sa.BigInteger(), nullable=False),
        sa.Column("was_duplicate", sa.Boolean(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("deleted_at", DT, nullable=False),
    )
    op.create_index("ix_deletion_history_user_id", "deletion_history", ["user_id"])
    op.create_index("ix_deletion_history_deleted_at", "deletion_history", ["deleted_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", DT, nullable=False),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("deletion_history")
    op.drop_table("file_metadata")
    op.drop_table("file_hashes")
    op.drop_table("files")
    op.drop_table("duplicate_groups")
    op.drop_table("users")
