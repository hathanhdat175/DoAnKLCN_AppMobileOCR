"""Cung cấp REST API cho trung tâm thông báo của người dùng.

Vai trò: liệt kê, đồng bộ gia tăng, đánh dấu đã đọc và xóa thông báo.
Đầu vào: current user, tham số phân trang/mốc thời gian và DB session.
Đầu ra: dữ liệu thông báo đã giới hạn theo chủ sở hữu.
Ràng buộc: người dùng chỉ thấy và thao tác trên thông báo của chính mình.
"""

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.modules.dangnhap.persistence.user import User
from app.modules.thongbao.persistence.notification import Notification, utc_now
from app.modules.thongbao.schemas import NotificationPage, NotificationSync, UnreadCount
from app.modules.thongbao.service import iso_utc, naive_utc, to_payload, unread_count
from app.shared.http.dependencies import get_current_user, get_db

router = APIRouter(prefix="/notifications", tags=["Notifications"])

# Lùi mốc đồng bộ vài giây để không bỏ sót bản ghi commit trễ; client khử trùng theo id.
SYNC_OVERLAP_SECONDS = 15
SYNC_MAX_ITEMS = 100


@router.get(
    "",
    response_model=NotificationPage,
    summary="Danh sách thông báo (List Notifications)",
    description=(
        "🇻🇳 **Mô tả**: Lấy danh sách thông báo của người dùng theo thứ tự mới nhất, "
        "có phân trang và lọc thông báo chưa đọc.\n\n"
        "🇬🇧 **Description**: Retrieve the user's notifications (newest first) with "
        "pagination and an unread-only filter."
    ),
)
def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.is_read == False)  # noqa: E712 - biểu thức SQL

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [to_payload(row) for row in rows],
        "total": total,
        "unread": unread_count(db, user.id),
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/sync",
    response_model=NotificationSync,
    summary="Đồng bộ thông báo mới (Incremental Sync)",
    description=(
        "🇻🇳 **Mô tả**: Trả về các thông báo phát sinh sau mốc `since` cùng số thông báo chưa đọc. "
        "Ứng dụng mobile gọi định kỳ để nhận thông báo ngay cả khi kênh WebSocket bị gián đoạn. "
        "Lần gọi đầu (không có `since`) chỉ trả mốc thời gian và bộ đếm.\n\n"
        "🇬🇧 **Description**: Return notifications created after `since` plus the unread counter. "
        "Used by the mobile app as a polling fallback for the realtime channel."
    ),
)
def sync_notifications(
    since: datetime | None = Query(None, description="Mốc server_time của lần đồng bộ trước (ISO-8601)"),
    limit: int = Query(50, ge=1, le=SYNC_MAX_ITEMS),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    server_time = utc_now()
    rows: list[Notification] = []
    if since is not None:
        cutoff = naive_utc(since) - timedelta(seconds=SYNC_OVERLAP_SECONDS)
        rows = list(
            db.scalars(
                select(Notification)
                .where(Notification.user_id == user.id, Notification.created_at > cutoff)
                .order_by(Notification.created_at.asc(), Notification.id.asc())
                .limit(limit)
            ).all()
        )
    return {
        "items": [to_payload(row) for row in rows],
        "unread": unread_count(db, user.id),
        "server_time": iso_utc(server_time),
    }


@router.get(
    "/unread-count",
    response_model=UnreadCount,
    summary="Số thông báo chưa đọc (Unread Count)",
    description="Trả về số thông báo chưa đọc để hiển thị huy hiệu trên biểu tượng chuông.",
)
def get_unread_count(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {"unread": unread_count(db, user.id)}


@router.post(
    "/read-all",
    response_model=UnreadCount,
    summary="Đánh dấu tất cả đã đọc (Mark All As Read)",
    description="Đánh dấu toàn bộ thông báo của người dùng là đã đọc.",
)
def mark_all_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read == False)  # noqa: E712
        .values(is_read=True, read_at=utc_now())
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return {"unread": 0}


@router.post(
    "/{notification_id}/read",
    response_model=UnreadCount,
    summary="Đánh dấu một thông báo đã đọc (Mark As Read)",
    description="Đánh dấu một thông báo là đã đọc và trả về số thông báo chưa đọc còn lại.",
)
def mark_read(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông báo")
    if not row.is_read:
        row.is_read = True
        row.read_at = utc_now()
        db.commit()
    return {"unread": unread_count(db, user.id)}


@router.delete(
    "",
    summary="Xóa thông báo hàng loạt (Clear Notifications)",
    description=(
        "Xóa các thông báo đã đọc của người dùng. Truyền `only_read=false` để xóa toàn bộ "
        "kể cả thông báo chưa đọc."
    ),
)
def clear_notifications(
    only_read: bool = Query(True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement = delete(Notification).where(Notification.user_id == user.id)
    if only_read:
        statement = statement.where(Notification.is_read == True)  # noqa: E712 - biểu thức SQL
    result = db.execute(statement.execution_options(synchronize_session=False))
    db.commit()
    return {"deleted": int(result.rowcount or 0), "unread": unread_count(db, user.id)}


@router.delete(
    "/{notification_id}",
    status_code=204,
    summary="Xóa một thông báo (Delete Notification)",
    description="Xóa vĩnh viễn một thông báo thuộc về người dùng hiện tại.",
)
def delete_notification(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông báo")
    db.delete(row)
    db.commit()
