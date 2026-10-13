"""Soạn nội dung thông báo cho từng sự kiện nghiệp vụ của CapitalFlow.

Vai trò: giữ toàn bộ câu chữ và quy tắc phân loại thông báo ở một nơi, để route
nghiệp vụ chỉ cần gọi một hàm ngắn sau khi thay đổi dữ liệu.
Đầu vào: Session của nghiệp vụ đang chạy và thực thể vừa được tạo/sửa/xóa.
Đầu ra: bản ghi Notification nằm trong cùng transaction (xem service.notify).
Ràng buộc: không commit, không gọi dịch vụ ngoài và không đưa dữ liệu nhạy cảm
(mật khẩu, token, OTP) vào nội dung thông báo.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.modules.danhmuc.persistence.category import Category
from app.modules.taichinh.persistence.account import Account
from app.modules.thongbao.service import notify, vnd


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value or "")


def _day(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def _account_name(db: Session, account_id: uuid.UUID | None) -> str:
    account = db.get(Account, account_id) if account_id else None
    return account.name if account else "ví đã chọn"


def _category_name(db: Session, category_id: uuid.UUID | None) -> str | None:
    category = db.get(Category, category_id) if category_id else None
    return category.name if category else None


# ── Ví & tài khoản ───────────────────────────────────────────────────────────

def account_created(db: Session, user_id: uuid.UUID, account: Account) -> None:
    notify(
        db, user_id, "ACCOUNT_CREATED", "Đã thêm ví mới",
        f"Ví «{account.name}» được tạo với số dư {vnd(account.balance)}.",
        severity="SUCCESS", entity_type="account", entity_id=account.id,
        data={"name": account.name, "balance": account.balance},
    )


def account_updated(db: Session, user_id: uuid.UUID, account: Account) -> None:
    notify(
        db, user_id, "ACCOUNT_UPDATED", "Ví đã được cập nhật",
        f"Thông tin ví «{account.name}» vừa thay đổi. Số dư hiện tại {vnd(account.balance)}.",
        entity_type="account", entity_id=account.id,
        data={"name": account.name, "balance": account.balance},
    )


def account_deleted(db: Session, user_id: uuid.UUID, account: Account) -> None:
    notify(
        db, user_id, "ACCOUNT_DELETED", "Đã ngừng sử dụng ví",
        f"Ví «{account.name}» đã được ẩn khỏi danh sách. Lịch sử giao dịch cũ vẫn được giữ nguyên.",
        severity="WARNING", entity_type="account", entity_id=account.id,
        data={"name": account.name},
    )


# ── Giao dịch ────────────────────────────────────────────────────────────────

def _transaction_line(db: Session, txn: Any) -> str:
    parts = [str(txn.description or "").strip() or "Không có diễn giải", f"Ví {_account_name(db, txn.account_id)}"]
    category = _category_name(db, txn.category_id)
    if category:
        suffix = " (tự động phân loại)" if getattr(txn, "category_was_auto", False) else ""
        parts.append(f"Danh mục {category}{suffix}")
    parts.append(_day(txn.transaction_date))
    return " · ".join(parts)


def transaction_created(db: Session, user_id: uuid.UUID, txn: Any) -> None:
    is_income = _enum_value(txn.type) == "INCOME"
    notify(
        db, user_id, "TRANSACTION_CREATED",
        f"Khoản thu mới: +{vnd(txn.amount)}" if is_income else f"Khoản chi mới: -{vnd(txn.amount)}",
        _transaction_line(db, txn),
        severity="SUCCESS" if is_income else "INFO",
        entity_type="transaction", entity_id=txn.id,
        data={"amount": txn.amount, "type": _enum_value(txn.type), "account_id": txn.account_id},
    )


def transaction_updated(db: Session, user_id: uuid.UUID, txn: Any) -> None:
    sign = "+" if _enum_value(txn.type) == "INCOME" else "-"
    notify(
        db, user_id, "TRANSACTION_UPDATED", f"Giao dịch đã được chỉnh sửa: {sign}{vnd(txn.amount)}",
        _transaction_line(db, txn),
        entity_type="transaction", entity_id=txn.id,
        data={"amount": txn.amount, "type": _enum_value(txn.type), "account_id": txn.account_id},
    )


def transaction_deleted(
    db: Session,
    user_id: uuid.UUID,
    *,
    description: str,
    amount: Decimal,
    tx_type: Any,
    account_id: uuid.UUID | None,
) -> None:
    sign = "+" if _enum_value(tx_type) == "INCOME" else "-"
    notify(
        db, user_id, "TRANSACTION_DELETED", f"Đã xóa giao dịch {sign}{vnd(amount)}",
        f"{(description or '').strip() or 'Không có diễn giải'} · Số dư ví {_account_name(db, account_id)} đã được hoàn lại.",
        severity="WARNING", entity_type="transaction",
        data={"amount": amount, "type": _enum_value(tx_type), "account_id": account_id},
    )


def transfer_created(
    db: Session,
    user_id: uuid.UUID,
    *,
    from_account_id: uuid.UUID,
    to_account_id: uuid.UUID,
    amount: Decimal,
    transfer_out_id: uuid.UUID | None = None,
) -> None:
    notify(
        db, user_id, "TRANSFER_CREATED", f"Chuyển tiền giữa hai ví: {vnd(amount)}",
        f"Từ «{_account_name(db, from_account_id)}» sang «{_account_name(db, to_account_id)}».",
        entity_type="transaction", entity_id=transfer_out_id,
        data={"amount": amount, "from_account_id": from_account_id, "to_account_id": to_account_id},
    )


# ── Ngân sách ────────────────────────────────────────────────────────────────

def budget_created(db: Session, user_id: uuid.UUID, budget: Any) -> None:
    notify(
        db, user_id, "BUDGET_CREATED", "Đã tạo ngân sách mới",
        f"«{budget.name}»: hạn mức {vnd(budget.amount_limit)} từ {_day(budget.start_date)} đến {_day(budget.end_date)}.",
        severity="SUCCESS", entity_type="budget", entity_id=budget.id,
        data={"name": budget.name, "amount_limit": budget.amount_limit},
    )


def budget_updated(db: Session, user_id: uuid.UUID, budget: Any) -> None:
    notify(
        db, user_id, "BUDGET_UPDATED", "Ngân sách đã được cập nhật",
        f"«{budget.name}»: hạn mức {vnd(budget.amount_limit)}, áp dụng {_day(budget.start_date)} – {_day(budget.end_date)}.",
        entity_type="budget", entity_id=budget.id,
        data={"name": budget.name, "amount_limit": budget.amount_limit},
    )


def budget_deleted(db: Session, user_id: uuid.UUID, *, name: str, budget_id: uuid.UUID) -> None:
    notify(
        db, user_id, "BUDGET_DELETED", "Đã xóa ngân sách",
        f"Ngân sách «{name}» không còn được theo dõi.",
        severity="WARNING", entity_type="budget", entity_id=budget_id, data={"name": name},
    )


def budget_threshold(
    db: Session,
    user_id: uuid.UUID,
    budget: Any,
    *,
    spent: Decimal,
    limit: Decimal,
    percent: float,
    transaction_id: uuid.UUID | None,
) -> None:
    """Nhắc nhở chi tiêu: mỗi giao dịch làm ngân sách ở mức cảnh báo/vượt chỉ báo một lần."""

    exceeded = percent >= 100.0
    level = "EXCEEDED" if exceeded else "WARNING"
    if exceeded:
        title = f"Đã vượt ngân sách «{budget.name}»"
        body = (
            f"Bạn đã chi {vnd(spent)} trên hạn mức {vnd(limit)} ({percent:.0f}%), "
            f"vượt {vnd(spent - limit)}. Hãy cân nhắc giảm chi tiêu trong kỳ này."
        )
    else:
        title = f"Sắp chạm hạn mức «{budget.name}»"
        body = (
            f"Bạn đã dùng {percent:.0f}% ngân sách: {vnd(spent)} / {vnd(limit)}. "
            f"Còn lại {vnd(limit - spent)} đến {_day(budget.end_date)}."
        )
    notify(
        db, user_id, f"BUDGET_{level}", title, body,
        severity="DANGER" if exceeded else "WARNING",
        entity_type="budget", entity_id=budget.id, origin="SYSTEM",
        data={"name": budget.name, "spent": spent, "amount_limit": limit, "percent": round(percent, 1)},
        dedupe_key=f"budget:{budget.id}:{transaction_id or 'manual'}:{level}",
    )


# ── Danh mục ─────────────────────────────────────────────────────────────────

def _category_kind(category: Any) -> str:
    return "thu" if _enum_value(category.type) == "INCOME" else "chi"


def category_created(db: Session, user_id: uuid.UUID, category: Any) -> None:
    notify(
        db, user_id, "CATEGORY_CREATED", "Đã thêm danh mục mới",
        f"Danh mục {_category_kind(category)} «{category.name}» đã sẵn sàng để phân loại giao dịch.",
        severity="SUCCESS", entity_type="category", entity_id=category.id, data={"name": category.name},
    )


def category_updated(db: Session, user_id: uuid.UUID, category: Any) -> None:
    notify(
        db, user_id, "CATEGORY_UPDATED", "Danh mục đã được cập nhật",
        f"Danh mục {_category_kind(category)} «{category.name}» vừa được chỉnh sửa.",
        entity_type="category", entity_id=category.id, data={"name": category.name},
    )


def category_deleted(db: Session, user_id: uuid.UUID, category: Any) -> None:
    notify(
        db, user_id, "CATEGORY_DELETED", "Đã ẩn danh mục",
        f"Danh mục «{category.name}» không còn hiển thị khi tạo giao dịch mới.",
        severity="WARNING", entity_type="category", entity_id=category.id, data={"name": category.name},
    )


# ── Hóa đơn & OCR ────────────────────────────────────────────────────────────

def _invoice_label(invoice: Any) -> str:
    return (
        str(invoice.merchant_name or "").strip()
        or str(invoice.original_filename or "").strip()
        or "Hóa đơn"
    )


def invoice_uploaded(db: Session, user_id: uuid.UUID, invoice: Any) -> None:
    structured = str(invoice.status) == "REVIEW_REQUIRED"
    notify(
        db, user_id, "INVOICE_UPLOADED", "Hóa đơn mới đã được tải lên",
        (
            f"«{_invoice_label(invoice)}» đã được đọc từ XML, hãy kiểm tra và xác nhận."
            if structured
            else f"«{_invoice_label(invoice)}» đang chờ quét AI để nhận dạng nội dung."
        ),
        entity_type="invoice", entity_id=invoice.id,
        data={"status": invoice.status, "filename": invoice.original_filename},
    )


def invoice_ocr_completed(db: Session, user_id: uuid.UUID, invoice: Any, ocr_job_id: uuid.UUID | None) -> None:
    total = f" · Tổng tiền {vnd(invoice.total_amount)}" if invoice.total_amount else ""
    notify(
        db, user_id, "INVOICE_OCR_COMPLETED", "Đã nhận dạng xong hóa đơn",
        f"«{_invoice_label(invoice)}»{total}. Hãy kiểm tra lại kết quả trước khi ghi khoản chi.",
        severity="SUCCESS", entity_type="invoice", entity_id=invoice.id, origin="SYSTEM",
        data={"total_amount": invoice.total_amount, "merchant_name": invoice.merchant_name},
        dedupe_key=f"ocr-done:{ocr_job_id}" if ocr_job_id else None,
    )


def invoice_ocr_failed(db: Session, user_id: uuid.UUID, invoice: Any, ocr_job_id: uuid.UUID | None) -> None:
    notify(
        db, user_id, "INVOICE_OCR_FAILED", "Nhận dạng hóa đơn thất bại",
        f"Không thể đọc «{_invoice_label(invoice)}». Bạn có thể quét lại hoặc nhập tay thông tin hóa đơn.",
        severity="DANGER", entity_type="invoice", entity_id=invoice.id, origin="SYSTEM",
        dedupe_key=f"ocr-failed:{ocr_job_id}" if ocr_job_id else None,
    )


def invoice_confirmed(db: Session, user_id: uuid.UUID, invoice: Any, txn: Any) -> None:
    category = _category_name(db, txn.category_id)
    category_text = f" · Danh mục {category}" if category else ""
    notify(
        db, user_id, "INVOICE_CONFIRMED", f"Hóa đơn đã ghi sổ: -{vnd(txn.amount)}",
        f"«{_invoice_label(invoice)}» · Ví {_account_name(db, txn.account_id)}{category_text}.",
        severity="SUCCESS", entity_type="invoice", entity_id=invoice.id,
        data={"amount": txn.amount, "transaction_id": txn.id},
    )


def invoice_deleted(db: Session, user_id: uuid.UUID, *, label: str, count: int = 1) -> None:
    notify(
        db, user_id, "INVOICE_DELETED",
        "Đã xóa hóa đơn" if count == 1 else f"Đã xóa {count} hóa đơn",
        (
            f"«{label}» đã bị xóa. Giao dịch liên quan (nếu có) vẫn được giữ lại."
            if count == 1
            else "Các hóa đơn đã chọn đã bị xóa. Giao dịch liên quan (nếu có) vẫn được giữ lại."
        ),
        severity="WARNING", entity_type="invoice",
    )


# ── Bảo mật tài khoản ────────────────────────────────────────────────────────

def describe_device(device_name: str | None, user_agent: str | None = None) -> str:
    """Rút gọn tên thiết bị/User-Agent thành mô tả dễ đọc, không lộ chuỗi kỹ thuật dài."""

    name = (device_name or "").strip()
    if name and not name.lower().startswith("mozilla/"):
        return name[:80]
    agent = (user_agent or name).lower()
    if not agent:
        return "thiết bị không xác định"
    browser = (
        "Edge" if "edg/" in agent else
        "Chrome" if "chrome/" in agent else
        "Firefox" if "firefox/" in agent else
        "Safari" if "safari/" in agent else
        "trình duyệt web"
    )
    system = (
        "Windows" if "windows" in agent else
        "Android" if "android" in agent else
        "iPhone/iPad" if ("iphone" in agent or "ipad" in agent) else
        "macOS" if "mac os" in agent else
        "Linux" if "linux" in agent else
        ""
    )
    return f"{browser} trên {system}" if system else browser


def security_login(
    db: Session,
    user_id: uuid.UUID,
    device_name: str | None,
    user_agent: str | None = None,
) -> None:
    device = describe_device(device_name, user_agent)
    notify(
        db, user_id, "SECURITY_LOGIN", "Đăng nhập mới vào tài khoản",
        f"Tài khoản vừa đăng nhập từ {device}. Nếu không phải bạn, hãy đổi mật khẩu ngay.",
        entity_type="security", data={"device": device},
    )


def password_changed(db: Session, user_id: uuid.UUID) -> None:
    notify(
        db, user_id, "SECURITY_PASSWORD_CHANGED", "Mật khẩu đã được thay đổi",
        "Mọi phiên đăng nhập cũ đã bị đăng xuất. Hãy đăng nhập lại bằng mật khẩu mới.",
        severity="WARNING", entity_type="security",
    )
