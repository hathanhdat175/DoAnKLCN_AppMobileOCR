"""Định nghĩa hợp đồng API cho trung tâm thông báo.

Vai trò: mô tả dữ liệu thông báo trả về cho ứng dụng mobile và web.
Đầu vào: dict đã chuẩn hóa từ service.to_payload.
Đầu ra: DTO Pydantic cho danh sách, đồng bộ gia tăng và bộ đếm chưa đọc.
Ràng buộc: thời gian luôn ở UTC (hậu tố Z) để client tự đổi sang giờ địa phương.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: UUID
    type: str
    severity: str
    title: str
    body: str
    entity_type: str | None = None
    entity_id: UUID | None = None
    origin: str
    data: dict | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int
    page: int
    page_size: int


class NotificationSync(BaseModel):
    """Kết quả đồng bộ gia tăng: thông báo mới kể từ mốc `since` của client."""

    items: list[NotificationOut]
    unread: int
    server_time: datetime


class UnreadCount(BaseModel):
    unread: int
