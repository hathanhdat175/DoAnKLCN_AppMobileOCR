"""Ánh xạ thông báo gửi tới người dùng trên web và ứng dụng mobile.

Vai trò: lưu từng sự kiện cần báo cho chủ tài khoản (giao dịch, ví, ngân sách,
hóa đơn OCR, bảo mật) để mobile nhận gần thời gian thực và tra cứu lại sau.
Đầu vào: service thông báo được gọi từ route nghiệp vụ và worker nền.
Đầu ra: thực thể Notification cho REST API, WebSocket và trung tâm thông báo.
Ràng buộc: bản ghi được ghi trong cùng transaction với nghiệp vụ phát sinh nên
chỉ tồn tại khi nghiệp vụ commit thành công; không lưu mật khẩu, token hay OTP.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Unicode, UnicodeText, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base


def utc_now() -> datetime:
    """Trả về thời điểm UTC dạng naive, thống nhất với sysutcdatetime() của SQL Server."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", name="FK_notifications_user", ondelete="CASCADE"),
        nullable=False,
    )

    # Mã sự kiện ổn định để client chọn icon/điều hướng (VD: TRANSACTION_CREATED).
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    # INFO | SUCCESS | WARNING | DANGER — quyết định màu và mức ưu tiên hiển thị.
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="INFO", server_default="INFO")
    title: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    body: Mapped[str] = mapped_column(Unicode(1000), nullable=False, default="")

    # Đối tượng nghiệp vụ liên quan để mobile mở đúng màn hình khi chạm vào thông báo.
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    # WEB | MOBILE | SYSTEM — nơi phát sinh thao tác. Mobile không bật banner cho
    # chính thao tác nó vừa thực hiện nhưng vẫn lưu vào lịch sử thông báo.
    origin: Mapped[str] = mapped_column(String(10), nullable=False, default="SYSTEM", server_default="SYSTEM")
    data_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    # Khóa chống trùng cho sự kiện có thể bị worker phát lại (cảnh báo ngân sách, OCR).
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, server_default=func.sysutcdatetime()
    )

    __table_args__ = (
        Index("IX_notifications_user_created", "user_id", "created_at"),
        Index("IX_notifications_user_unread", "user_id", "is_read", "created_at"),
        Index(
            "UX_notifications_user_dedupe", "user_id", "dedupe_key", unique=True,
            mssql_where=text("dedupe_key IS NOT NULL"),
            sqlite_where=text("dedupe_key IS NOT NULL"),
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
    )
