# Hướng dẫn cài đặt và chạy CapitalFlow Mobile (kèm backend + web)

Tài liệu này hướng dẫn **từng bước** để chạy ứng dụng mobile Flutter của đề tài
*CNTT-KLCN242 — Xây dựng ứng dụng quản lý tài chính cá nhân tích hợp nhận dạng hóa đơn bằng OCR*,
dùng **VS Code** và **Android Studio** trên Windows.

> Đọc lướt mục 1 để hiểu hệ thống, sau đó làm lần lượt từ mục 3 đến mục 9.
> Mỗi bước đều có phần **"Kết quả đúng"** để bạn tự kiểm tra trước khi sang bước sau.

---

## 1. Hệ thống hoạt động như thế nào

```
 ┌────────────────┐        ┌────────────────┐
 │  Web người dùng │        │  App mobile    │
 │  (Next.js :3010)│        │  (Flutter)     │
 └───────┬────────┘        └───────┬────────┘
         │  REST /api/v1           │  REST /api/v1  +  WebSocket /notifications/ws
         └────────────┬────────────┘
                      ▼
            ┌───────────────────┐      ┌─────────────────────────┐
            │  FastAPI  (:8000) │◄────►│  Worker nền             │
            │  capitalflow-api  │      │  OCR Gemini, email,     │
            └─────────┬─────────┘      │  cảnh báo ngân sách     │
                      ▼                └────────────┬────────────┘
            ┌───────────────────┐                   │
            │  SQL Server       │◄──────────────────┘
            │  personal_finance │
            └───────────────────┘
```

- **Dùng chung database:** web và mobile đều gọi **cùng một backend FastAPI**, backend ghi vào
  **cùng một database SQL Server**. Mobile không kết nối thẳng vào SQL Server (đây là cách làm
  chuẩn và an toàn). Vì vậy tài khoản, ví, giao dịch, ngân sách, hóa đơn trên web và mobile là một.
- **Thông báo từ web về mobile:** mỗi khi có thao tác ghi dữ liệu (thêm/sửa/xóa giao dịch, ví,
  ngân sách, danh mục, hóa đơn, đăng nhập, đổi mật khẩu…), backend ghi một dòng vào bảng mới
  `notifications`. App mobile nhận thông báo qua 2 đường:
  1. **WebSocket** — gần như tức thời;
  2. **Đồng bộ định kỳ 5 giây** — tự động dùng khi WebSocket gián đoạn, và lấy bù thông báo
     phát sinh lúc app đang đóng.
  Thông báo đến từ web/hệ thống sẽ hiện **banner trên điện thoại** và các màn hình đang mở tự tải lại.
- **Nhắc nhở chi tiêu:** khi một khoản chi làm ngân sách chạm ngưỡng cảnh báo (mặc định 80%) hoặc
  vượt hạn mức, worker tạo thông báo `BUDGET_WARNING` / `BUDGET_EXCEEDED` đẩy về điện thoại.
  Ngoài ra app có nhắc ghi chép hằng ngày theo giờ bạn chọn.

## 2. Những gì đã được thêm vào đồ án

| Thư mục | Nội dung |
|---|---|
| `capitalflow-mobile/` | **Mới.** Ứng dụng Flutter (45 file Dart). |
| `capitalflow-api/app/modules/thongbao/` | **Mới.** Module thông báo: bảng, REST API, WebSocket. |
| `capitalflow-api/app/...` | **Sửa nhẹ** 12 file có sẵn: đăng ký module mới và gọi phát thông báo sau mỗi thao tác ghi (không đổi API cũ). |
| `capitalflow-api/tests/integration/thongbao/` | **Mới.** 9 bài kiểm thử cho module thông báo. |
| `capitalflow-database/sql/20261006_notifications.sql` | **Mới.** Script tạo bảng `notifications` chạy trong SSMS. |
| `capitalflow-database/alembic/versions/cfdb_20261006_notifications.py` | **Mới.** Migration Alembic tương đương. |
| `capitalflow-database/alembic/env.py`, `tools/seed.py` | **Sửa:** đổi import sang cấu trúc module mới của API (bản gốc còn trỏ `app.core`, `app.models` đã bị xóa nên chạy sẽ lỗi `ModuleNotFoundError`). |

Hai cổng web (`frontend/user-web`, `frontend/admin-web`) **không bị sửa**.

### Cách đưa gói này vào máy của bạn

Gói `DoAn_KLCN-main` này là **toàn bộ đồ án cũ + phần bổ sung**. Chọn một trong hai cách:

- **Dùng làm thư mục đồ án mới:** giải nén ra, rồi chép file `capitalflow-api\.env` (và thư mục
  `capitalflow-api\uploads` nếu có) từ đồ án cũ sang. Tạo lại `.venv` và chạy `npm ci` như lần đầu.
- **Giải nén đè lên đồ án cũ:** các file `.env`, `.venv`, `node_modules`, `uploads` của bạn không nằm
  trong gói nên được giữ nguyên. Chỉ 14 file có sẵn sau đây bị thay bằng bản đã sửa — nếu bạn từng
  tự chỉnh chúng thì hãy sao lưu trước:

  ```text
  capitalflow-api/app/bootstrap/app_factory.py          (thêm nhóm tài liệu "Notifications")
  capitalflow-api/app/bootstrap/routers.py              (đăng ký router thông báo)
  capitalflow-api/app/shared/database/model_registry.py (đăng ký model Notification)
  capitalflow-api/app/modules/dangnhap/api/routes.py    (thông báo đăng nhập, đổi mật khẩu)
  capitalflow-api/app/modules/taichinh/accounts/api.py  (thông báo ví)
  capitalflow-api/app/modules/taichinh/transactions/api.py (thông báo giao dịch, chuyển tiền)
  capitalflow-api/app/modules/taichinh/budgets/api.py   (thông báo ngân sách)
  capitalflow-api/app/modules/taichinh/ledger.py        (cảnh báo ngưỡng/vượt ngân sách)
  capitalflow-api/app/modules/danhmuc/api.py            (thông báo danh mục)
  capitalflow-api/app/modules/hoadon/api/routes.py      (thông báo hóa đơn)
  capitalflow-api/app/modules/jobs/runner.py            (thông báo OCR xong/thất bại)
  capitalflow-api/app/modules/admin/user_lifecycle/service.py (xóa thông báo khi xóa hẳn người dùng)
  capitalflow-database/alembic/env.py                   (sửa import cũ)
  capitalflow-database/tools/seed.py                    (sửa import cũ)
  ```

  Ngoài ra `README.md` và `PROJECT_STRUCTURE.md` ở thư mục gốc được bổ sung phần mô tả mobile.

---

## 3. Chuẩn bị phần mềm (làm một lần)

| Phần mềm | Dùng để | Ghi chú |
|---|---|---|
| Python 3.12 | Chạy backend | Bạn đã có nếu web đang chạy được |
| Node.js 20 | Chạy web | Bạn đã có nếu web đang chạy được |
| SQL Server + SSMS + ODBC Driver 18 | Database | Bạn đã có nếu web đang chạy được |
| **Flutter SDK** (bản stable mới nhất) | Biên dịch app mobile | Cài ở bước 3.1 |
| **Android Studio** | Android SDK + máy ảo | Cài ở bước 3.2 |
| **VS Code** + extension **Flutter** | Viết code và chạy app | Cài ở bước 3.3 |

### 3.1. Cài Flutter SDK

1. Vào <https://docs.flutter.dev/get-started/install/windows/mobile> và tải file zip Flutter **stable**.
2. Giải nén vào đường dẫn **không có dấu cách và không có dấu tiếng Việt**, ví dụ `C:\dev\flutter`.
3. Thêm `C:\dev\flutter\bin` vào biến môi trường **Path**:
   *Start → gõ "environment variables" → Edit the system environment variables → Environment Variables →
   chọn Path (User) → Edit → New → dán `C:\dev\flutter\bin` → OK*.
4. Mở **PowerShell mới** và chạy:

   ```powershell
   flutter --version
   ```

**Kết quả đúng:** in ra `Flutter 3.x.x • channel stable`. Ứng dụng cần Flutter **3.27 trở lên**
(nên dùng bản stable mới nhất).

### 3.2. Cài Android Studio và tạo máy ảo

1. Tải và cài Android Studio: <https://developer.android.com/studio> (giữ nguyên các lựa chọn mặc định,
   có **Android SDK** và **Android Virtual Device**).
2. Mở Android Studio → **More Actions → SDK Manager → tab SDK Tools** → tick
   **Android SDK Command-line Tools (latest)** → Apply.
3. Vào **Plugins** (trong màn hình Welcome hoặc *File → Settings → Plugins*) → tìm và cài plugin
   **Flutter** (plugin Dart được cài kèm) → Restart IDE.
4. Chấp nhận giấy phép Android, chạy trong PowerShell:

   ```powershell
   flutter doctor --android-licenses
   ```

   Gõ `y` cho mọi câu hỏi.
5. Tạo máy ảo: Android Studio → **More Actions → Virtual Device Manager → Create Device** →
   chọn **Pixel 7** → chọn system image **API 34 hoặc 35 (có Google APIs)** → Next → Finish.
6. Kiểm tra tổng thể:

   ```powershell
   flutter doctor
   ```

**Kết quả đúng:** các dòng `Flutter`, `Android toolchain`, `Android Studio` có dấu ✓.
(Dòng `Visual Studio` hoặc `Chrome` báo ✗ cũng không sao — chỉ cần cho app Windows/web.)

### 3.3. Cài extension cho VS Code

Mở VS Code → **Extensions** (Ctrl+Shift+X) → cài **Flutter** (của Dart Code; extension **Dart** tự cài kèm).

---

## 4. Bước 1 — Cập nhật database (thêm bảng thông báo)

Chỉ **thêm** bảng `notifications`, không sửa hay xóa dữ liệu cũ. Chọn **một** trong hai cách.

### Cách A — Dùng SSMS (khuyên dùng, đơn giản nhất)

1. Mở **SQL Server Management Studio** và kết nối tới server của bạn (ví dụ `localhost\SQLEXPRESS`).
2. *File → Open → File…* → chọn `capitalflow-database\sql\20261006_notifications.sql`.
3. Ở ô chọn database trên thanh công cụ, chọn **`personal_finance`** (database của đồ án).
4. Bấm **Execute** (F5).

**Kết quả đúng:** tab Messages in `Đã tạo bảng dbo.notifications.` và `Hoàn tất.`
Trong Object Explorer → Tables xuất hiện `dbo.notifications`. Chạy lại script lần nữa cũng không lỗi.

### Cách B — Dùng Alembic

```powershell
cd capitalflow-api
.\.venv\Scripts\Activate.ps1
python -m pip install -r ..\capitalflow-database\requirements.txt
python -m alembic -c ..\capitalflow-database\alembic.ini upgrade head
```

**Kết quả đúng:** in ra `Running upgrade cfdb_20260924_baseline -> cfdb_20261006_notifications`.

> Nếu **quên bước này**, backend sẽ trả lỗi 500 ("Lỗi cơ sở dữ liệu") mỗi khi thêm giao dịch,
> vì chưa có bảng để ghi thông báo.

---

## 5. Bước 2 — Chạy backend (API + worker)

Nếu web của bạn đang chạy được thì file `capitalflow-api\.env` đã đúng — **giữ nguyên**.
Nếu cài mới, làm theo `README.md` ở thư mục gốc để tạo `.venv` và `.env`. Tham khảo `.env` cho máy cá nhân:

```ini
APP_ENV=development
DEBUG=true
# SQL Server Authentication (đổi user/mật khẩu cho đúng):
DATABASE_URL=mssql+pyodbc://sa:MatKhauCuaBan@localhost\SQLEXPRESS/personal_finance?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes
# Hoặc Windows Authentication:
# DATABASE_URL=mssql+pyodbc://@localhost\SQLEXPRESS/personal_finance?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&Encrypt=yes&TrustServerCertificate=yes
JWT_SECRET_KEY=mot-chuoi-ngau-nhien-dai-it-nhat-32-ky-tu
JOB_ENCRYPTION_KEY=<dán khóa Fernet>
GOOGLE_AI_API_KEY=<khóa Gemini để chạy OCR>
```

Tạo khóa Fernet: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

Mở **2 cửa sổ PowerShell**:

```powershell
# Cửa sổ 1 — API. Lưu ý --host 0.0.0.0 để điện thoại thật trong mạng LAN gọi được.
cd capitalflow-api
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

```powershell
# Cửa sổ 2 — Worker (bắt buộc cho OCR, email và CẢNH BÁO NGÂN SÁCH).
cd capitalflow-api
.\.venv\Scripts\Activate.ps1
python -m app.modules.jobs.runner
```

**Kết quả đúng:**

- Mở <http://localhost:8000/health> thấy `{"status":"ok",...}`.
- Mở <http://localhost:8000/docs> thấy nhóm API mới **Notifications**.
- Cửa sổ worker in `Worker started for ALL. Waiting for jobs`.

(Tùy chọn) Chạy kiểm thử backend, gồm 9 bài mới cho thông báo:

```powershell
cd capitalflow-api
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## 6. Bước 3 — Chạy web (như trước đây)

```powershell
# Cửa sổ 3
cd frontend\user-web
npm ci
npm run dev
```

**Kết quả đúng:** mở <http://localhost:3010> đăng nhập được. Nếu chưa có tài khoản, bấm đăng ký
(hoặc đăng ký ngay trên app mobile ở bước sau — cùng một tài khoản).

---

## 7. Bước 4 — Chuẩn bị dự án mobile (làm một lần)

Thư mục `capitalflow-mobile` chứa mã Dart (`lib/`), `pubspec.yaml` và công cụ cấu hình. Phần Android
(`android/`) được Flutter sinh ra đúng theo phiên bản Flutter trên máy bạn.

Mở PowerShell tại thư mục gốc đồ án:

```powershell
cd capitalflow-mobile

# 1) Sinh thư mục android/ (không ghi đè lib/ và pubspec.yaml có sẵn)
flutter create --platforms=android --org vn.edu.huit --project-name capitalflow_mobile .

# 2) Tự cấu hình Android: quyền Internet/thông báo, cho phép http nội bộ, desugaring...
dart run tool/setup_android.dart

# 3) Tải thư viện
flutter pub get

# 4) Kiểm tra mã nguồn
flutter analyze
flutter test
```

**Kết quả đúng:**

- Lệnh 1: `All done!` và xuất hiện thư mục `capitalflow-mobile\android`.
- Lệnh 2: in các dòng `[OK] Thêm quyền: INTERNET, POST_NOTIFICATIONS, RECEIVE_BOOT_COMPLETED`,
  `[OK] build.gradle.kts: bật core library desugaring`…
- Lệnh 3: `Got dependencies!`
- Lệnh 4: `flutter analyze` không có dòng `error`; `flutter test` báo `All tests passed!`

> **Quan trọng:** nếu `flutter analyze` hoặc `flutter run` báo `error`, hãy chép nguyên văn thông báo
> lỗi gửi lại để được sửa. Mã Dart được viết và rà soát kỹ nhưng chưa được biên dịch trên máy của
> người viết (xem mục 12).

---

## 8. Bước 5 — Chạy app

### 8.1. Chạy trên máy ảo Android (dễ nhất)

**Bằng VS Code**

1. *File → Open Folder…* → chọn thư mục **`capitalflow-mobile`** (mở đúng thư mục này, không mở thư mục gốc).
2. Nhìn góc **dưới bên phải** thanh trạng thái, bấm vào tên thiết bị (hoặc `No Device`) →
   chọn **Start Pixel 7 …** để bật máy ảo. Chờ máy ảo hiện màn hình chính.
3. Mở file `lib/main.dart` → nhấn **F5** (*Run → Start Debugging*).
4. Lần build đầu mất 3–10 phút (tải Gradle và thư viện Android). Các lần sau nhanh hơn nhiều.

**Bằng Android Studio**

1. *File → Open* → chọn thư mục **`capitalflow-mobile`** → Trust Project.
2. Chọn máy ảo ở ô thiết bị trên thanh công cụ → bấm nút **Run ▶** (Shift+F10).

**Bằng dòng lệnh** (khi máy ảo đang mở): `flutter run`

**Kết quả đúng:** app mở màn **Đăng nhập** của CapitalFlow.
Địa chỉ máy chủ mặc định là `http://10.0.2.2:8000` — đây chính là `localhost:8000` của máy tính khi
nhìn từ máy ảo, nên **không cần cấu hình gì thêm**.

Đăng nhập bằng tài khoản web → cho phép quyền thông báo khi được hỏi → vào màn **Tổng quan**.
Dòng trạng thái dưới lời chào hiện **"Đang đồng bộ trực tiếp với web"** (chấm xanh) nghĩa là
WebSocket đã kết nối.

### 8.2. Chạy trên điện thoại Android thật

1. Trên điện thoại: *Cài đặt → Giới thiệu điện thoại* → chạm **Số bản dựng** 7 lần để bật
   *Tùy chọn nhà phát triển* → bật **Gỡ lỗi USB**.
2. Cắm cáp USB, chọn **Cho phép gỡ lỗi USB** trên điện thoại. Chạy `flutter devices` phải thấy máy.
3. Chọn điện thoại làm thiết bị rồi F5 (VS Code) hoặc Run (Android Studio).
4. Cho app biết địa chỉ backend — chọn **một** trong hai cách:

   **Cách 1 — qua cáp USB (không phụ thuộc Wi-Fi):**

   ```powershell
   & "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" reverse tcp:8000 tcp:8000
   ```

   Trong app: màn Đăng nhập → biểu tượng máy chủ góc trên phải → chọn nhanh
   **"Điện thoại thật qua USB"** (`http://127.0.0.1:8000`) → Kiểm tra kết nối → Lưu.
   (Phải chạy lại lệnh `adb reverse` mỗi lần cắm lại cáp.)

   **Cách 2 — qua Wi-Fi (điện thoại và máy tính cùng một mạng):**

   - Lấy IP máy tính: chạy `ipconfig`, xem dòng **IPv4 Address** (ví dụ `192.168.1.10`).
   - Mở cổng 8000 trên tường lửa — PowerShell **Run as administrator**:

     ```powershell
     New-NetFirewallRule -DisplayName "CapitalFlow API 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
     ```

   - Backend phải chạy với `--host 0.0.0.0` (đã ghi ở bước 2).
   - Trong app nhập `http://192.168.1.10:8000` → Kiểm tra kết nối → Lưu.

**Kết quả đúng:** nút *Kiểm tra kết nối* báo **"Kết nối thành công tới máy chủ."**

---

## 9. Bước 6 — Kiểm tra liên kết web ↔ mobile và thông báo

Mở song song: web <http://localhost:3010> trên máy tính và app trên máy ảo/điện thoại,
**đăng nhập cùng một tài khoản**. Đảm bảo API và worker đang chạy.

| # | Làm trên WEB | Thấy gì trên MOBILE (trong vài giây) |
|---|---|---|
| 1 | Đăng nhập | Banner **"Đăng nhập mới vào tài khoản"** |
| 2 | *Ví & tài khoản* → thêm ví "Tiền mặt" 5.000.000 | Banner **"Đã thêm ví mới"**; tab Tổng quan tự cập nhật tổng tài sản |
| 3 | *Giao dịch* → thêm khoản chi 45.000 "Cà phê" | Banner **"Khoản chi mới: -45.000 ₫"**; tab Giao dịch tự có dòng mới |
| 4 | *Ngân sách* → tạo ngân sách tháng này 100.000 | Banner **"Đã tạo ngân sách mới"** |
| 5 | Thêm khoản chi 90.000 | Banner cảnh báo **"Sắp chạm hạn mức…"** hoặc **"Đã vượt ngân sách…"** (do worker tạo) |
| 6 | *Hóa đơn AI* → tải ảnh hóa đơn → Quét AI | **"Hóa đơn mới đã được tải lên"**, rồi **"Đã nhận dạng xong hóa đơn"** |

Chiều ngược lại: thêm giao dịch trên mobile → nhấn F5 trên web sẽ thấy giao dịch đó (cùng database).

Xem lại toàn bộ thông báo: chạm **biểu tượng chuông** ở tab Tổng quan. Mỗi dòng ghi rõ nguồn
*Từ web / Từ điện thoại / Hệ thống*. Thao tác làm ngay trên điện thoại được lưu vào danh sách nhưng
mặc định không bật banner (đổi trong *Thêm → Cài đặt thông báo & nhắc nhở*).

Thử thông báo hệ thống: *Thêm → Cài đặt thông báo & nhắc nhở → Gửi thông báo thử*.

---

## 10. Chức năng mobile đối chiếu với đề cương

| Yêu cầu trong đề cương | Vị trí trong app |
|---|---|
| Đăng nhập, đăng xuất, đổi mật khẩu, phân quyền | Màn Đăng nhập/Đăng ký/Quên mật khẩu (OTP email); *Thêm → Bảo mật*; mục Quản trị chỉ hiện với admin |
| Quản lý tài khoản người dùng (quản trị người dùng Mobile) | *Thêm → Quản trị người dùng*: KPI hệ thống, tìm kiếm, tạo tài khoản, khóa/mở khóa, cấp lại mật khẩu |
| Quản lý danh mục thu – chi | *Thêm → Danh mục thu – chi* (biểu tượng, màu, từ khóa tự phân loại) |
| Quản lý ví, tài khoản ngân hàng | *Thêm → Ví & tài khoản*; chuyển tiền giữa ví |
| Ghi nhận giao dịch thủ công | Nút **+** → Ghi khoản chi / Ghi khoản thu |
| Xem lịch sử giao dịch | Tab **Giao dịch**: nhóm theo ngày, tìm kiếm, lọc theo loại/ví/danh mục/khoảng ngày |
| Theo dõi ngân sách theo tháng hoặc theo danh mục | Tab **Ngân sách**: tiến độ, còn lại, trạng thái an toàn/cảnh báo/vượt |
| Chụp hoặc tải lên hóa đơn; lưu trữ và tra cứu | Nút **+** → Chụp hóa đơn / Tải từ thư viện; *Thêm → Hóa đơn AI* (ảnh, PDF, XML; lọc trạng thái) |
| Tích hợp OCR (cửa hàng, ngày, sản phẩm, tổng tiền, VAT) | Tự gửi quét AI sau khi tải lên; màn *Kiểm tra hóa đơn* tự cập nhật khi có kết quả |
| Kiểm tra, chỉnh sửa kết quả OCR trước khi lưu | Màn *Kiểm tra hóa đơn*: sửa mọi trường và từng dòng hàng, rồi **Xác nhận & ghi khoản chi** |
| Tự động phân loại giao dịch | Gợi ý danh mục khi gõ diễn giải; tự áp dụng khi độ tin cậy ≥ 90% |
| Thông báo, nhắc nhở, cảnh báo ngân sách | Banner hệ thống, trung tâm thông báo, cảnh báo ngưỡng/vượt hạn mức, nhắc ghi chép hằng ngày |
| Báo cáo, thống kê, trực quan hóa | *Thêm → Báo cáo tài chính*: dòng tiền ròng, so sánh kỳ trước, biểu đồ tròn theo danh mục, cột 6 tháng |
| Đồng bộ dữ liệu web – mobile | Dùng chung API và database; màn hình tự tải lại khi web thay đổi |

---

## 11. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân và cách xử lý |
|---|---|
| App báo *"Không kết nối được máy chủ…"* | Backend chưa chạy, hoặc sai địa chỉ. Máy ảo dùng `http://10.0.2.2:8000`. Điện thoại thật xem mục 8.2. Thử mở `http://<địa chỉ>:8000/health` bằng trình duyệt của điện thoại. |
| Thêm giao dịch báo *"Lỗi cơ sở dữ liệu"* (500) | Chưa tạo bảng `notifications` — làm lại Bước 1. |
| Không có cảnh báo ngân sách / OCR đứng ở "Đang quét AI" | Worker chưa chạy (cửa sổ 2 ở Bước 2), hoặc thiếu `GOOGLE_AI_API_KEY`. |
| Chấm vàng "Đồng bộ định kỳ" thay vì chấm xanh | WebSocket chưa kết nối (thường do proxy/tường lửa). Thông báo vẫn đến, chậm tối đa ~5 giây. |
| Không thấy banner dù danh sách có thông báo | Chưa cấp quyền thông báo: *Cài đặt Android → Ứng dụng → CapitalFlow → Thông báo → Cho phép*. Hoặc thao tác đó làm ngay trên điện thoại (mặc định không báo). |
| `flutter create` báo tên dự án không hợp lệ | Phải có `--project-name capitalflow_mobile` vì tên thư mục chứa dấu gạch ngang. |
| Build lỗi `requires core library desugaring` | Chưa chạy `dart run tool/setup_android.dart`. Chạy lại lệnh đó. |
| Build lỗi liên quan `compileSdk` / `minSdk` | Mở `android/app/build.gradle.kts`, đặt `compileSdk = 36` và `minSdk = 24` trong khối tương ứng, rồi `flutter clean` và chạy lại. |
| Build lỗi sau khi nâng cấp Flutter | Xóa thư mục `android`, chạy lại 3 lệnh đầu của Bước 4. |
| `alembic` báo `ModuleNotFoundError: app.models` | Bạn đang dùng `alembic/env.py` bản cũ. Dùng bản trong gói này (đã sửa import). |
| `ERR_CLEARTEXT_NOT_PERMITTED` | Manifest chưa có `usesCleartextTraffic` — chạy lại `dart run tool/setup_android.dart`. |
| Đường dẫn dự án có dấu tiếng Việt/khoảng trắng gây lỗi build | Chuyển đồ án sang đường dẫn đơn giản, ví dụ `C:\dev\DoAn_KLCN`. |

**Cấu hình Android thủ công** (chỉ khi script ở Bước 4 báo `[CẦN LÀM TAY]`):

1. `android/app/src/main/AndroidManifest.xml` — thêm ngay trước thẻ `<application`:

   ```xml
   <uses-permission android:name="android.permission.INTERNET"/>
   <uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
   <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED"/>
   ```

   thêm vào thẻ `<application ...>` hai thuộc tính
   `android:usesCleartextTraffic="true" android:allowBackup="false"`, và thêm ngay trước `</application>`:

   ```xml
   <receiver android:exported="false" android:name="com.dexterous.flutterlocalnotifications.ScheduledNotificationReceiver" />
   <receiver android:exported="false" android:name="com.dexterous.flutterlocalnotifications.ScheduledNotificationBootReceiver">
       <intent-filter>
           <action android:name="android.intent.action.BOOT_COMPLETED"/>
           <action android:name="android.intent.action.MY_PACKAGE_REPLACED"/>
       </intent-filter>
   </receiver>
   ```

2. `android/app/build.gradle.kts` — trong `compileOptions { ... }` thêm
   `isCoreLibraryDesugaringEnabled = true`, và thêm ở cuối file:

   ```kotlin
   dependencies {
       coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
   }
   ```

---

## 12. Giới hạn hiện tại — cần biết trước khi báo cáo

1. **Chưa biên dịch thử.** Mã Flutter và phần backend bổ sung được viết và rà soát bằng công cụ kiểm tra
   tĩnh (cú pháp, import, tham số), nhưng môi trường soạn thảo không có Flutter SDK, SQL Server hay
   các thư viện Python của dự án nên **chưa được biên dịch/chạy thực tế**. `flutter analyze`,
   `flutter test` và `pytest` ở các bước trên chính là lần kiểm chứng đầu tiên — nếu có lỗi, hãy gửi
   lại thông báo lỗi để sửa.
2. **Thông báo khi app bị tắt hẳn.** App nhận thông báo tức thời khi đang mở hoặc chạy nền. Nếu người
   dùng vuốt tắt app, thông báo được **lấy bù và hiện banner khi mở lại app**. Muốn đẩy thông báo cả
   khi app đã tắt hẳn cần tích hợp **Firebase Cloud Messaging** (cần tài khoản Firebase và file
   `google-services.json` của riêng bạn) — đây là hướng mở rộng tự nhiên, phần backend đã sẵn bảng
   `notifications` để gắn thêm kênh gửi FCM.
3. **Chỉ hỗ trợ Android** (đúng phạm vi đề cương: Android Studio). Mã Dart không phụ thuộc Android
   ngoài phần kết nối, nên có thể mở rộng iOS sau.
4. **Kết nối http trong mạng nội bộ.** Phù hợp cho phát triển và demo; khi triển khai thật cần đặt
   backend sau HTTPS và bỏ `usesCleartextTraffic`.
5. Web chưa có giao diện xem thông báo; API `/api/v1/notifications` đã sẵn để bổ sung nếu cần.
