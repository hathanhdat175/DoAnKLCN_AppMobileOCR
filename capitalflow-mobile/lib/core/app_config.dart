import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Cấu hình kết nối tới backend CapitalFlow (cùng API và CSDL với bản web).
///
/// Địa chỉ mặc định `http://10.0.2.2:8000` là cách máy ảo Android gọi về
/// `localhost:8000` của máy tính đang chạy FastAPI. Khi chạy trên điện thoại
/// thật, người dùng đổi địa chỉ này trong màn "Máy chủ".
class AppConfig extends ChangeNotifier {
  AppConfig(this._prefs) {
    _baseUrl = normalizeBaseUrl(_prefs.getString(_keyBaseUrl) ?? defaultBaseUrl);
  }

  static const String defaultBaseUrl = 'http://10.0.2.2:8000';
  static const String _keyBaseUrl = 'cf_api_base_url';

  final SharedPreferences _prefs;
  late String _baseUrl;

  /// Gốc máy chủ, ví dụ `http://192.168.1.10:8000`.
  String get baseUrl => _baseUrl;

  /// Gốc REST API phiên bản 1.
  String get apiRoot => '$_baseUrl/api/v1';

  /// Địa chỉ kênh WebSocket nhận thông báo thời gian thực.
  String get webSocketUrl {
    final uri = Uri.parse(apiRoot);
    final scheme = uri.scheme == 'https' ? 'wss' : 'ws';
    return uri.replace(scheme: scheme, path: '${uri.path}/notifications/ws').toString();
  }

  Future<void> setBaseUrl(String value) async {
    final normalized = normalizeBaseUrl(value);
    if (normalized == _baseUrl) return;
    _baseUrl = normalized;
    await _prefs.setString(_keyBaseUrl, normalized);
    notifyListeners();
  }

  /// Chuẩn hóa địa chỉ người dùng nhập: thêm `http://`, bỏ dấu `/` cuối và
  /// phần `/api` hoặc `/api/v1` nếu lỡ dán kèm.
  static String normalizeBaseUrl(String raw) {
    var value = raw.trim();
    if (value.isEmpty) return defaultBaseUrl;
    if (!value.startsWith('http://') && !value.startsWith('https://')) {
      value = 'http://$value';
    }
    value = value.replaceAll(RegExp(r'/+$'), '');
    value = value.replaceAll(RegExp(r'/api(/v1)?$'), '');
    value = value.replaceAll(RegExp(r'/+$'), '');
    return value;
  }
}
