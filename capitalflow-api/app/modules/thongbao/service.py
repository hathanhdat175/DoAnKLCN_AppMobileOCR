"""Tạo và chuyển đổi thông báo dùng chung cho route nghiệp vụ và worker nền.

Vai trò: một điểm duy nhất để ghi thông báo, xác định nguồn thao tác (web/mobile/hệ
thống) và chuẩn hóa dữ liệu trả về cho REST lẫn WebSocket.
Đầu vào: Session đang mở của nghiệp vụ, user ID và nội dung thông báo.
Đầu ra: bản ghi Notification được thêm vào cùng transaction với nghiệp vụ.
Ràng buộc: không tự commit/flush — bên gọi quyết định commit hay rollback, nhờ đó
thông báo chỉ xuất hiện khi thao tác tài chính thực sự được lưu.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.thongbao.persistence.notification import Notification, utc_now


SEVERITIES = {"INFO", "SUCCESS", "WARNING", "DANGER"}
ORIGINS = {"WEB", "MOBILE", "SYSTEM"}

# Header do ứng dụng mobile gửi kèm mọi request để backend biết thao tác đến từ đâu.
CLIENT_PLATFORM_HEADER = "x-client-platform"


def vnd(amount: Any) -> str:
    """Định dạng số tiền kiểu Việt Nam (1.250.000 ₫); luôn hiển thị giá trị tuyệt đối."""

    try:
        value = abs(Decimal(str(amount if amount is not None else 0)))
    except (InvalidOperation, ValueError):
        value = Decimal("0")
    return f"{value:,.0f}".replace(",", ".") + " ₫"


def request_origin(db: Session) -> str:
    """Suy ra nguồn thao tác từ request gắn với session; worker không có request."""

    request = db.info.get("request") if isinstance(getattr(db, "info", None), dict) else None
    if request is None:
        return "SYSTEM"
    try:
        platform = (request.headers.get(CLIENT_PLATFORM_HEADER) or "").strip().lower()
    except Exception:
        return "WEB"
    return "MOBILE" if platform == "mobile" else "WEB"


def _clip(value: Any, limit: int) -> str:
    text_value = str(value or "").strip()
    return text_value if len(text_value) <= limit else text_value[: limit - 1] + "…"


def _as_uuid(value: Any) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def notify(
    db: Session,
    user_id: uuid.UUID,
    type_: str,
    title: str,
    body: str = "",
    *,
    severity: str = "INFO",
    entity_type: str | None = None,
    entity_id: Any = None,
    data: dict | None = None,
    dedupe_key: str | None = None,
    origin: str | None = None,
) -> Notification | None:
    """Thêm một thông báo vào transaction hiện tại; trả None nếu trùng dedupe_key."""

    key = dedupe_key[:200] if dedupe_key else None
    if key:
        duplicate = db.scalar(
            select(Notification.id).where(
                Notification.user_id == user_id,
                Notification.dedupe_key == key,
            )
        )
        if duplicate:
            return None

    resolved_origin = (origin or request_origin(db)).upper()
    row = Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        type=_clip(type_, 40).upper(),
        severity=severity if severity in SEVERITIES else "INFO",
        title=_clip(title, 200) or "Thông báo",
        body=_clip(body, 1000),
        entity_type=_clip(entity_type, 30) or None,
        entity_id=_as_uuid(entity_id),
        origin=resolved_origin if resolved_origin in ORIGINS else "SYSTEM",
        data_json=json.dumps(data, ensure_ascii=False, default=str) if data else None,
        dedupe_key=key,
        is_read=False,
        created_at=utc_now(),
    )
    db.add(row)
    return row


def iso_utc(value: datetime | None) -> str | None:
    """Chuỗi ISO-8601 có hậu tố Z để client không hiểu nhầm múi giờ."""

    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def naive_utc(value: datetime) -> datetime:
    """Đưa datetime bất kỳ về UTC dạng naive để so sánh với cột created_at."""

    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def to_payload(row: Notification) -> dict:
    """Biểu diễn JSON ổn định của một thông báo cho REST và WebSocket."""

    data = None
    if row.data_json:
        try:
            parsed = json.loads(row.data_json)
            data = parsed if isinstance(parsed, dict) else None
        except ValueError:
            data = None
    return {
        "id": str(row.id),
        "type": row.type,
        "severity": row.severity,
        "title": row.title,
        "body": row.body or "",
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id) if row.entity_id else None,
        "origin": row.origin,
        "data": data,
        "is_read": bool(row.is_read),
        "read_at": iso_utc(row.read_at),
        "created_at": iso_utc(row.created_at),
    }


def unread_count(db: Session, user_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.is_read == False,  # noqa: E712 - biểu thức SQL
            )
        )
        or 0
    )
