"""Thêm bảng thông báo phục vụ ứng dụng mobile và đồng bộ web–mobile.

Revision ID: cfdb_20261006_notifications
Revises: cfdb_20260924_baseline
Ngày tạo UTC: 2026-10-06

Revision này chỉ THÊM bảng `notifications` cùng index; không sửa, không xóa bảng
hay dữ liệu hiện có. Nếu bảng đã được tạo trước bằng script
`sql/20261006_notifications.sql` trong SSMS thì upgrade tự bỏ qua.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql


revision: str = "cfdb_20261006_notifications"
down_revision: Union[str, Sequence[str], None] = "cfdb_20260924_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Tạo bảng thông báo người dùng; an toàn khi chạy lại."""

    if sa.inspect(op.get_bind()).has_table("notifications"):
        return

    op.create_table(
        "notifications",
        sa.Column("id", mssql.UNIQUEIDENTIFIER(), autoincrement=False, nullable=False),
        sa.Column("user_id", mssql.UNIQUEIDENTIFIER(), autoincrement=False, nullable=False),
        sa.Column("type", sa.VARCHAR(length=40), autoincrement=False, nullable=False),
        sa.Column("severity", sa.VARCHAR(length=10), server_default=sa.text("('INFO')"), autoincrement=False, nullable=False),
        sa.Column("title", sa.NVARCHAR(length=200), autoincrement=False, nullable=False),
        sa.Column("body", sa.NVARCHAR(length=1000), server_default=sa.text("(N'')"), autoincrement=False, nullable=False),
        sa.Column("entity_type", sa.VARCHAR(length=30), autoincrement=False, nullable=True),
        sa.Column("entity_id", mssql.UNIQUEIDENTIFIER(), autoincrement=False, nullable=True),
        sa.Column("origin", sa.VARCHAR(length=10), server_default=sa.text("('SYSTEM')"), autoincrement=False, nullable=False),
        sa.Column("data_json", sa.NVARCHAR(), autoincrement=False, nullable=True),
        sa.Column("dedupe_key", sa.VARCHAR(length=200), autoincrement=False, nullable=True),
        sa.Column("is_read", mssql.BIT(), server_default=sa.text("((0))"), autoincrement=False, nullable=False),
        sa.Column("read_at", mssql.DATETIME2(), autoincrement=False, nullable=True),
        sa.Column("created_at", mssql.DATETIME2(), server_default=sa.text("(sysutcdatetime())"), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="FK_notifications_user", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="PK_notifications"),
    )
    op.create_index("IX_notifications_user_created", "notifications", ["user_id", "created_at"], unique=False)
    op.create_index("IX_notifications_user_unread", "notifications", ["user_id", "is_read", "created_at"], unique=False)
    op.create_index(
        "UX_notifications_user_dedupe", "notifications", ["user_id", "dedupe_key"],
        unique=True, mssql_where="([dedupe_key] IS NOT NULL)",
    )


def downgrade() -> None:
    """Gỡ bảng thông báo. Lịch sử thông báo sẽ mất; dữ liệu tài chính không bị ảnh hưởng."""

    op.drop_index("UX_notifications_user_dedupe", table_name="notifications")
    op.drop_index("IX_notifications_user_unread", table_name="notifications")
    op.drop_index("IX_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
