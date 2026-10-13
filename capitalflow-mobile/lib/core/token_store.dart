import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Lưu access token và refresh token trong vùng lưu trữ bảo mật của thiết bị
/// (Android Keystore). Token được giữ thêm trong bộ nhớ để gắn vào request
/// mà không phải đọc đĩa mỗi lần.
class TokenStore {
  static const String _keyAccess = 'cf_access_token';
  static const String _keyRefresh = 'cf_refresh_token';

  // ignore: prefer_const_constructors
  final FlutterSecureStorage _storage = FlutterSecureStorage();

  String? _access;
  String? _refresh;

  String? get accessToken => _access;
  String? get refreshToken => _refresh;
  bool get hasSession => (_refresh ?? '').isNotEmpty;

  /// Nạp token đã lưu khi mở ứng dụng. Nếu vùng lưu trữ bị hỏng (ví dụ sau khi
  /// khôi phục bản sao lưu) thì coi như chưa đăng nhập thay vì làm treo ứng dụng.
  Future<void> load() async {
    try {
      _access = await _storage.read(key: _keyAccess);
      _refresh = await _storage.read(key: _keyRefresh);
    } catch (_) {
      _access = null;
      _refresh = null;
      try {
        await _storage.deleteAll();
      } catch (_) {
        // Không còn gì để dọn; người dùng sẽ đăng nhập lại.
      }
    }
  }

  Future<void> save({required String access, required String refresh}) async {
    _access = access;
    _refresh = refresh;
    try {
      await _storage.write(key: _keyAccess, value: access);
      await _storage.write(key: _keyRefresh, value: refresh);
    } catch (_) {
      // Vẫn giữ phiên trong bộ nhớ; lần mở ứng dụng sau sẽ cần đăng nhập lại.
    }
  }

  Future<void> clear() async {
    _access = null;
    _refresh = null;
    try {
      await _storage.delete(key: _keyAccess);
      await _storage.delete(key: _keyRefresh);
    } catch (_) {
      // Bỏ qua: token trong bộ nhớ đã được xóa.
    }
  }
}
