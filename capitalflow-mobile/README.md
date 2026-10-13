# CapitalFlow Mobile

Ứng dụng Flutter (Android) của hệ thống CapitalFlow — quản lý tài chính cá nhân tích hợp nhận dạng
hóa đơn bằng OCR. App gọi **cùng REST API FastAPI** với hai cổng web nên dùng chung cơ sở dữ liệu
SQL Server, và nhận **thông báo đẩy từ web** qua WebSocket `/api/v1/notifications/ws`.

> Hướng dẫn cài đặt chi tiết từng bước: [`../HUONG_DAN_MOBILE.md`](../HUONG_DAN_MOBILE.md)

## Chạy nhanh

```powershell
cd capitalflow-mobile
flutter create --platforms=android --org vn.edu.huit --project-name capitalflow_mobile .
dart run tool/setup_android.dart
flutter pub get
flutter analyze
flutter test
flutter run
```

Backend (`capitalflow-api`) và worker phải đang chạy; bảng `notifications` phải được tạo trước
(script `capitalflow-database/sql/20261006_notifications.sql`).

- Máy ảo Android: địa chỉ máy chủ mặc định `http://10.0.2.2:8000` (không cần đổi).
- Điện thoại thật: đổi trong màn **Máy chủ** (biểu tượng ở góc trên phải màn Đăng nhập).

## Cấu trúc mã nguồn

| Đường dẫn | Mục đích |
|---|---|
| `lib/main.dart` | Khởi tạo dịch vụ, provider, điều hướng theo trạng thái đăng nhập. |
| `lib/core/api_client.dart` | HTTP client: JWT, tự làm mới token, `Idempotency-Key`, chuẩn hóa lỗi. |
| `lib/core/app_config.dart` | Địa chỉ backend (REST + WebSocket). |
| `lib/core/token_store.dart` | Lưu token trong vùng bảo mật của thiết bị. |
| `lib/core/formatters.dart`, `theme.dart`, `category_style.dart` | Định dạng tiền/ngày, giao diện, icon và màu danh mục (khớp bản web). |
| `lib/models/models.dart` | Kiểu dữ liệu ánh xạ hợp đồng API. |
| `lib/services/repositories.dart` | Lời gọi REST theo phân hệ: tài chính, hóa đơn, thông báo, quản trị. |
| `lib/services/auth_controller.dart` | Phiên đăng nhập, đăng ký, OTP, đổi mật khẩu. |
| `lib/services/app_data.dart` | Bộ nhớ ví/danh mục và "số phiên bản dữ liệu" để các màn hình tự tải lại. |
| `lib/services/notification_center.dart` | Nhận thông báo (WebSocket + đồng bộ định kỳ), khử trùng, hiện banner. |
| `lib/services/realtime_socket.dart` | Kết nối WebSocket, tự kết nối lại, làm mới token khi bị từ chối. |
| `lib/services/local_notifier.dart` | Thông báo hệ thống Android và lịch nhắc hằng ngày. |
| `lib/services/app_settings.dart` | Tùy chọn thông báo của người dùng. |
| `lib/widgets/` | Thành phần giao diện dùng chung, bộ chọn, biểu đồ tự vẽ. |
| `lib/screens/auth/` | Đăng nhập, đăng ký, quên mật khẩu (OTP), đặt mật khẩu lần đầu. |
| `lib/screens/dashboard_screen.dart` | Tổng quan: tài sản, thu chi tháng, ví, ngân sách, giao dịch gần đây. |
| `lib/screens/transactions/` | Lịch sử giao dịch, ghi/sửa giao dịch thủ công, chuyển tiền. |
| `lib/screens/budgets/` | Theo dõi và quản lý ngân sách. |
| `lib/screens/invoices/` | Chụp/tải hóa đơn, theo dõi OCR, kiểm tra và xác nhận kết quả. |
| `lib/screens/analytics/` | Báo cáo, thống kê và biểu đồ. |
| `lib/screens/accounts/`, `categories/` | Ví & tài khoản; danh mục thu – chi. |
| `lib/screens/notifications/` | Trung tâm thông báo. |
| `lib/screens/settings/` | Bảo mật, cài đặt thông báo & nhắc nhở, cấu hình máy chủ. |
| `lib/screens/admin/` | Quản trị người dùng (chỉ với tài khoản admin). |
| `tool/setup_android.dart` | Cấu hình `AndroidManifest.xml` và Gradle sau `flutter create`. |
| `test/widget_test.dart` | Kiểm thử đơn vị cho định dạng, đọc dữ liệu API, nhận diện tệp hóa đơn. |

Thư mục `android/` không nằm trong mã nguồn: nó được `flutter create` sinh ra theo đúng phiên bản
Flutter đang cài, rồi `tool/setup_android.dart` bổ sung cấu hình cần thiết.

## Thư viện sử dụng

`http`, `provider`, `shared_preferences`, `flutter_secure_storage`, `image_picker`, `file_selector`,
`flutter_local_notifications`, `timezone`. Biểu đồ được tự vẽ bằng `CustomPainter`.
