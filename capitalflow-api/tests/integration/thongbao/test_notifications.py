"""Kiểm thử trung tâm thông báo: phát sinh theo nghiệp vụ, quyền sở hữu và đồng bộ."""

from datetime import date

from sqlalchemy import func, select

from app.modules.thongbao.persistence.notification import Notification
from tests.integration.taichinh.test_transactions import account, headers
from tests.operational.test_security_contract import drain_jobs


def listed(client, token, **params):
    response = client.get("/api/v1/notifications", headers=headers(token), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def types(page):
    return [item["type"] for item in page["items"]]


def test_web_action_notifies_owner_only(client, user_token, admin_token):
    account(client, user_token, "Ví chính", 500000)

    page = listed(client, user_token)
    assert "ACCOUNT_CREATED" in types(page)
    created = next(item for item in page["items"] if item["type"] == "ACCOUNT_CREATED")
    assert created["origin"] == "WEB"
    assert created["is_read"] is False
    assert created["entity_type"] == "account" and created["entity_id"]
    assert "Ví chính" in created["body"]
    assert page["unread"] >= 1

    # Người dùng khác không được thấy thông báo của chủ tài khoản.
    assert listed(client, admin_token)["items"] == []


def test_mobile_origin_header_is_recorded(client, user_token):
    response = client.post(
        "/api/v1/categories",
        headers={**headers(user_token), "X-Client-Platform": "mobile"},
        json={"name": "Cà phê sáng", "type": "EXPENSE"},
    )
    assert response.status_code == 201, response.text
    created = next(item for item in listed(client, user_token)["items"] if item["type"] == "CATEGORY_CREATED")
    assert created["origin"] == "MOBILE"


def test_idempotent_replay_does_not_duplicate_notification(client, db, user_token):
    auth = {**headers(user_token), "Idempotency-Key": "notify-replay-001"}
    body = {"name": "Replay", "account_type": "CASH", "balance": "100", "currency": "VND"}
    assert client.post("/api/v1/accounts", headers=auth, json=body).status_code == 201
    assert client.post("/api/v1/accounts", headers=auth, json=body).status_code == 201
    count = db.scalar(
        select(func.count()).select_from(Notification).where(Notification.type == "ACCOUNT_CREATED")
    )
    assert count == 1


def test_failed_operation_leaves_no_notification(client, db, user_token):
    a, b = account(client, user_token, "A", 100), account(client, user_token, "B", 0)
    response = client.post(
        "/api/v1/transactions/transfer",
        headers=headers(user_token),
        json={"from_account_id": a, "to_account_id": b, "amount": 101},
    )
    assert response.status_code == 400
    count = db.scalar(
        select(func.count()).select_from(Notification).where(Notification.type == "TRANSFER_CREATED")
    )
    assert count == 0


def test_transaction_lifecycle_notifications(client, user_token):
    acc = account(client, user_token, "Tiền mặt", 1000000)
    created = client.post(
        "/api/v1/transactions",
        headers=headers(user_token),
        json={"account_id": acc, "type": "EXPENSE", "amount": 45000, "transaction_date": str(date.today()), "description": "Ăn trưa"},
    )
    assert created.status_code == 201, created.text
    tx = created.json()["id"]
    assert client.patch(f"/api/v1/transactions/{tx}", headers=headers(user_token), json={"amount": 50000}).status_code == 200
    assert client.delete(f"/api/v1/transactions/{tx}", headers=headers(user_token)).status_code == 204

    page = listed(client, user_token, page_size=50)
    for expected in ("TRANSACTION_CREATED", "TRANSACTION_UPDATED", "TRANSACTION_DELETED"):
        assert expected in types(page)
    first = next(item for item in page["items"] if item["type"] == "TRANSACTION_CREATED")
    assert "45.000" in first["title"] and "Ăn trưa" in first["body"]


def test_mark_read_delete_and_clear(client, user_token):
    account(client, user_token, "A", 0)
    account(client, user_token, "B", 0)
    page = listed(client, user_token)
    assert page["unread"] == 2
    first, second = page["items"][0]["id"], page["items"][1]["id"]

    marked = client.post(f"/api/v1/notifications/{first}/read", headers=headers(user_token))
    assert marked.status_code == 200 and marked.json()["unread"] == 1
    assert [item["id"] for item in listed(client, user_token, unread_only=True)["items"]] == [second]

    assert client.delete(f"/api/v1/notifications/{second}", headers=headers(user_token)).status_code == 204
    assert client.get("/api/v1/notifications/unread-count", headers=headers(user_token)).json() == {"unread": 0}

    cleared = client.delete("/api/v1/notifications", headers=headers(user_token))
    assert cleared.status_code == 200 and cleared.json()["deleted"] == 1
    assert listed(client, user_token)["total"] == 0


def test_other_user_cannot_touch_notification(client, user_token, admin_token):
    account(client, user_token, "A", 0)
    target = listed(client, user_token)["items"][0]["id"]
    assert client.post(f"/api/v1/notifications/{target}/read", headers=headers(admin_token)).status_code == 404
    assert client.delete(f"/api/v1/notifications/{target}", headers=headers(admin_token)).status_code == 404


def test_sync_returns_items_created_after_marker(client, user_token):
    first = client.get("/api/v1/notifications/sync", headers=headers(user_token))
    assert first.status_code == 200, first.text
    assert first.json()["items"] == []
    marker = first.json()["server_time"]

    account(client, user_token, "Sau mốc", 0)
    second = client.get("/api/v1/notifications/sync", headers=headers(user_token), params={"since": marker})
    assert second.status_code == 200, second.text
    assert "ACCOUNT_CREATED" in [item["type"] for item in second.json()["items"]]
    assert second.json()["unread"] == 1


def test_budget_threshold_pushes_spending_reminder(client, db, user_token):
    acc = account(client, user_token, "Ví chi tiêu", 1000)
    budget = client.post(
        "/api/v1/budgets",
        headers=headers(user_token),
        json={"name": "Chi tiêu hôm nay", "amount_limit": 100, "start_date": str(date.today()), "end_date": str(date.today())},
    )
    assert budget.status_code == 201, budget.text

    def spend(amount):
        response = client.post(
            "/api/v1/transactions",
            headers=headers(user_token),
            json={"account_id": acc, "type": "EXPENSE", "amount": amount, "transaction_date": str(date.today())},
        )
        assert response.status_code == 201, response.text
        drain_jobs(db)

    spend(50)
    assert "BUDGET_WARNING" not in types(listed(client, user_token, page_size=50))
    spend(40)
    page = listed(client, user_token, page_size=50)
    warning = next(item for item in page["items"] if item["type"] == "BUDGET_WARNING")
    assert warning["origin"] == "SYSTEM" and warning["severity"] == "WARNING"
    spend(20)
    page = listed(client, user_token, page_size=50)
    exceeded = next(item for item in page["items"] if item["type"] == "BUDGET_EXCEEDED")
    assert exceeded["severity"] == "DANGER"
    assert exceeded["entity_id"] == budget.json()["id"]
