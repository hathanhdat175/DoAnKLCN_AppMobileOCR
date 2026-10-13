"""Điểm tập hợp router của module thông báo.

Vai trò: ghép REST API và kênh WebSocket dưới cùng prefix /notifications.
Đầu vào: router REST và router realtime của module.
Đầu ra: một router để bootstrap đăng ký vào /api/v1.
Ràng buộc: chỉ làm nhiệm vụ composition, không chứa nghiệp vụ.
"""

from fastapi import APIRouter

from app.modules.thongbao.api import router as rest_router
from app.modules.thongbao.realtime import router as realtime_router


router = APIRouter()
router.include_router(rest_router)
router.include_router(realtime_router)

__all__ = ["router"]
