# Thông báo người dùng và kênh đẩy tới ứng dụng mobile

## Mục tiêu

Khi người dùng thao tác trên web (hoặc trên một thiết bị khác), ứng dụng mobile phải biết ngay:
hiện thông báo, cập nhật số liệu và nhắc nhở khi chi tiêu chạm ngưỡng ngân sách. Module
`app/modules/thongbao` cung cấp bảng lưu thông báo, REST API và kênh WebSocket cho mục tiêu đó.

## Nguyên tắc thiết kế

- **Cùng transaction với nghiệp vụ.** `service.notify()` chỉ `db.add()` bản ghi, không tự commit.
  Thông báo vì thế chỉ tồn tại khi thao tác tài chính commit thành công; request bị rollback hoặc
  request lặp có cùng `Idempotency-Key` không sinh thông báo thừa.
- **Biết nguồn thao tác.** Ứng dụng mobile gửi header `X-Client-Platform: mobile`; request không có
  header được coi là từ web; worker nền không có request nên là `SYSTEM`. Giá trị lưu ở cột `origin`
  (`WEB` / `MOBILE` / `SYSTEM`) để mobile không tự bật banner cho thao tác của chính nó.
- **Đẩy liên tiến trình.** Thông báo có thể do API process hoặc worker (OCR, ngân sách) ghi. Kênh
  WebSocket đọc CSDL theo chu kỳ 2 giây thay vì dựa vào bộ nhớ của một tiến trình, nên hoạt động
  đúng cả khi chạy nhiều API process.
- **Không mất thông báo.** Mobile đồng thời gọi `GET /notifications/sync?since=...` định kỳ; máy chủ
  lùi mốc 15 giây và client khử trùng theo `id`.

## Bảng `notifications`

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | UNIQUEIDENTIFIER PK | |
| `user_id` | UNIQUEIDENTIFIER FK → `users.id` ON DELETE CASCADE | Chủ sở hữu |
| `type` | VARCHAR(40) | Mã sự kiện, ví dụ `TRANSACTION_CREATED` |
| `severity` | VARCHAR(10) | `INFO` / `SUCCESS` / `WARNING` / `DANGER` |
| `title`, `body` | NVARCHAR(200) / NVARCHAR(1000) | Nội dung tiếng Việt |
| `entity_type`, `entity_id` | VARCHAR(30) / UNIQUEIDENTIFIER | Đối tượng liên quan để điều hướng |
| `origin` | VARCHAR(10) | `WEB` / `MOBILE` / `SYSTEM` |
| `data_json` | NVARCHAR(MAX) | Dữ liệu bổ sung (số tiền, tên…) |
| `dedupe_key` | VARCHAR(200) | Chống trùng cho sự kiện worker có thể phát lại |
| `is_read`, `read_at`, `created_at` | BIT / DATETIME2 / DATETIME2 (UTC) | |

Index: `IX_notifications_user_created`, `IX_notifications_user_unread`,
`UX_notifications_user_dedupe` (unique, lọc `dedupe_key IS NOT NULL`).

## Danh sách sự kiện

| Mã | Phát sinh khi | Mức |
|---|---|---|
| `ACCOUNT_CREATED` / `ACCOUNT_UPDATED` / `ACCOUNT_DELETED` | Tạo, sửa, ngừng sử dụng ví | SUCCESS / INFO / WARNING |
| `TRANSACTION_CREATED` / `_UPDATED` / `_DELETED` | Ghi, sửa, xóa giao dịch | INFO–SUCCESS / INFO / WARNING |
| `TRANSFER_CREATED` | Chuyển tiền giữa hai ví | INFO |
| `BUDGET_CREATED` / `_UPDATED` / `_DELETED` | Tạo, sửa, xóa ngân sách | SUCCESS / INFO / WARNING |
| `BUDGET_WARNING` | Khoản chi làm ngân sách đạt ngưỡng cảnh báo | WARNING |
| `BUDGET_EXCEEDED` | Khoản chi làm ngân sách vượt hạn mức | DANGER |
| `CATEGORY_CREATED` / `_UPDATED` / `_DELETED` | Tạo, sửa, ẩn danh mục cá nhân | SUCCESS / INFO / WARNING |
| `INVOICE_UPLOADED` | Tải hóa đơn lên | INFO |
| `INVOICE_OCR_COMPLETED` / `INVOICE_OCR_FAILED` | Worker OCR xong / thất bại | SUCCESS / DANGER |
| `INVOICE_CONFIRMED` / `INVOICE_DELETED` | Xác nhận ghi sổ / xóa hóa đơn | SUCCESS / WARNING |
| `SECURITY_LOGIN` | Đăng nhập thành công | INFO |
| `SECURITY_PASSWORD_CHANGED` | Đổi hoặc đặt lại mật khẩu | WARNING |

Cảnh báo ngân sách được khử trùng theo `(ngân sách, giao dịch, mức)`: mỗi khoản chi làm ngân sách ở
mức cảnh báo/vượt tạo đúng một thông báo, kể cả khi job `BUDGET` bị worker chạy lại.

## REST API (`/api/v1/notifications`)

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/notifications?page&page_size&unread_only` | Danh sách mới nhất trước, kèm `total`, `unread` |
| GET | `/notifications/sync?since&limit` | Thông báo tạo sau mốc `since`, kèm `unread`, `server_time` |
| GET | `/notifications/unread-count` | Số thông báo chưa đọc |
| POST | `/notifications/{id}/read` | Đánh dấu một thông báo đã đọc |
| POST | `/notifications/read-all` | Đánh dấu tất cả đã đọc |
| DELETE | `/notifications/{id}` | Xóa một thông báo |
| DELETE | `/notifications?only_read=true` | Xóa các thông báo đã đọc |

Mọi endpoint yêu cầu Bearer token và chỉ thao tác trên thông báo của chính người dùng.

## WebSocket `/api/v1/notifications/ws`

```
client → {"type": "auth", "token": "<access token>", "since": "<ISO-8601, tùy chọn>"}
server → {"type": "ready", "unread": 3, "server_time": "2026-10-06T11:00:00.000000Z"}
server → {"type": "notification", "unread": 4, "data": { ...giống REST... }}
client → "ping"        server → {"type": "pong", "unread": 4}
```

- Token gửi trong thông điệp đầu tiên (không nằm trên URL để tránh lọt vào log). Quá 10 giây không
  xác thực hoặc token sai: đóng với mã **4401**.
- Mỗi chu kỳ máy chủ kiểm tra lại trạng thái tài khoản và `token_version`; tài khoản bị khóa, bị xóa
  hoặc đổi mật khẩu sẽ bị đóng kết nối với mã 4401.

## Kiểm thử

`tests/integration/thongbao/test_notifications.py` kiểm tra: phát sinh theo nghiệp vụ, phân biệt
nguồn web/mobile, không trùng khi replay idempotent, không sinh thông báo khi nghiệp vụ thất bại,
quyền sở hữu, đánh dấu đọc/xóa, đồng bộ gia tăng và cảnh báo ngân sách qua worker.
