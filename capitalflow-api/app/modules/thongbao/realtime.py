"""Kênh WebSocket đẩy thông báo gần thời gian thực tới ứng dụng mobile.

Vai trò: giữ kết nối với client đã xác thực và gửi ngay thông báo mới của họ.
Đầu vào: access token (JWT) gửi trong thông điệp đầu tiên sau khi kết nối.
Đầu ra: các thông điệp JSON `ready`, `notification` và `pong`.
Ràng buộc: thông báo có thể được ghi bởi tiến trình khác (worker OCR/ngân sách hoặc
một API process khác), vì vậy kênh này đọc CSDL theo chu kỳ ngắn thay vì dựa vào
bộ nhớ của riêng một tiến trình. Token không nằm trên URL để tránh lọt vào log.

Giao thức:
  client → {"type": "auth", "token": "<access token>", "since": "<ISO-8601, tùy chọn>"}
  server → {"type": "ready", "unread": 3, "server_time": "...Z"}
  server → {"type": "notification", "unread": 4, "data": {...}}   (mỗi thông báo mới)
  client → "ping"   /   server → {"type": "pong"}
Mã đóng 4401: token không hợp lệ, hết hạn lúc bắt tay hoặc phiên đã bị thu hồi.
"""

import asyncio
import json
import uuid
from collections import deque
from datetime import datetime, timedelta

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.modules.dangnhap.persistence.user import User
from app.modules.thongbao.persistence.notification import Notification, utc_now
from app.modules.thongbao.service import iso_utc, naive_utc, to_payload, unread_count
from app.shared.database.session import SessionLocal
from app.shared.security.tokens import decode_token

router = APIRouter(prefix="/notifications", tags=["Notifications"])

AUTH_TIMEOUT_SECONDS = 10
POLL_SECONDS = 2.0
OVERLAP_SECONDS = 15
MAX_BATCH = 100
MAX_REMEMBERED_IDS = 500
CLOSE_UNAUTHORIZED = 4401


def _parse_since(raw) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return naive_utc(datetime.fromisoformat(raw.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


def _authenticate(token: str) -> tuple[uuid.UUID, int, int] | None:
    """Xác minh access token và trạng thái tài khoản; trả (user_id, token_version, unread)."""

    try:
        payload = decode_token(token)
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        return None
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if (
            not user
            or user.is_deleted
            or not user.is_active
            or user.must_change_password
            or payload["ver"] != user.token_version
        ):
            return None
        return user.id, int(user.token_version), unread_count(db, user.id)


def _poll(user_id: uuid.UUID, token_version: int, cursor: datetime) -> tuple[list[dict], int] | None:
    """Đọc thông báo mới hơn mốc `cursor`; trả None khi phiên không còn hợp lệ."""

    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user or user.is_deleted or not user.is_active or user.token_version != token_version:
            return None
        rows = db.scalars(
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.created_at > cursor - timedelta(seconds=OVERLAP_SECONDS),
            )
            .order_by(Notification.created_at.asc(), Notification.id.asc())
            .limit(MAX_BATCH)
        ).all()
        return [to_payload(row) for row in rows], unread_count(db, user_id)


async def _close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except Exception:
        pass


@router.websocket("/ws")
async def notifications_socket(websocket: WebSocket) -> None:
    await websocket.accept()

    # Bước 1: bắt tay xác thực trong thời hạn ngắn để không giữ kết nối vô danh.
    try:
        first = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
        hello = json.loads(first)
        if not isinstance(hello, dict):
            raise ValueError("Invalid handshake")
        token = str(hello.get("token") or "")
        since = _parse_since(hello.get("since"))
    except WebSocketDisconnect:
        return
    except Exception:
        await _close(websocket, CLOSE_UNAUTHORIZED)
        return

    identity = await run_in_threadpool(_authenticate, token)
    if identity is None:
        await _close(websocket, CLOSE_UNAUTHORIZED)
        return
    user_id, token_version, initial_unread = identity

    cursor = since or utc_now()
    remembered: deque[str] = deque(maxlen=MAX_REMEMBERED_IDS)
    remembered_set: set[str] = set()

    try:
        await websocket.send_json(
            {"type": "ready", "unread": initial_unread, "server_time": iso_utc(utc_now())}
        )
        while True:
            # Bước 2: đọc CSDL ngoài event loop để không chặn các kết nối khác.
            state = await run_in_threadpool(_poll, user_id, token_version, cursor)
            if state is None:
                await _close(websocket, CLOSE_UNAUTHORIZED)
                return
            payloads, unread = state
            for payload in payloads:
                identifier = payload["id"]
                if identifier in remembered_set:
                    continue
                if len(remembered) == remembered.maxlen:
                    remembered_set.discard(remembered[0])
                remembered.append(identifier)
                remembered_set.add(identifier)
                await websocket.send_json({"type": "notification", "unread": unread, "data": payload})
                created = _parse_since(payload.get("created_at"))
                if created and created > cursor:
                    cursor = created

            # Bước 3: chờ thông điệp từ client tối đa một chu kỳ rồi kiểm tra tiếp.
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=POLL_SECONDS)
            except asyncio.TimeoutError:
                continue
            if message.strip().lower() in {"ping", '{"type":"ping"}'}:
                await websocket.send_json({"type": "pong", "unread": unread})
    except WebSocketDisconnect:
        return
    except Exception:
        await _close(websocket, 1011)
