import 'dart:async';

import 'package:flutter/widgets.dart';

import '../core/api_client.dart';
import '../core/app_config.dart';
import '../core/token_store.dart';
import '../models/models.dart';
import 'app_data.dart';
import 'app_settings.dart';
import 'local_notifier.dart';
import 'realtime_socket.dart';
import 'repositories.dart';

/// Trung tâm thông báo của ứng dụng.
///
/// Nhận thông báo từ backend theo hai đường song song:
///  1. WebSocket — gần như tức thời khi web/worker vừa ghi dữ liệu;
///  2. Đồng bộ định kỳ qua REST — đường dự phòng khi WebSocket gián đoạn, đồng thời
///     lấy bù những thông báo phát sinh lúc ứng dụng bị đóng.
/// Thông báo trùng được loại theo id. Thông báo đến từ nơi khác (web, hệ thống)
/// sẽ hiện banner hệ thống và làm các màn hình tải lại dữ liệu.
class NotificationCenter extends ChangeNotifier with WidgetsBindingObserver {
  NotificationCenter({
    required ApiClient api,
    required this.config,
    required this.tokens,
    required this.settings,
    required this.notifier,
    required this.data,
  })  : _api = api,
        _repo = NotificationRepository(api);

  final ApiClient _api;
  final NotificationRepository _repo;
  final AppConfig config;
  final TokenStore tokens;
  final AppSettings settings;
  final LocalNotifier notifier;
  final AppData data;

  static const int _maxItems = 200;
  static const Duration _tickInterval = Duration(seconds: 5);

  final List<AppNotification> _items = <AppNotification>[];
  final Set<String> _seen = <String>{};

  RealtimeSocket? _socket;
  Timer? _timer;
  bool _running = false;
  bool _syncing = false;
  bool _loading = false;
  bool _realtime = false;
  bool _caughtUp = false;
  int _unread = 0;
  int _ticks = 0;
  String? _lastSync;
  DateTime? _alertFloor;
  String? _error;

  List<AppNotification> get items => List<AppNotification>.unmodifiable(_items);
  int get unread => _unread;
  bool get loading => _loading;
  String? get error => _error;

  /// `true` khi kênh WebSocket đang kết nối; `false` nghĩa là đang dùng đồng bộ định kỳ.
  bool get realtimeConnected => _realtime;

  // ── Vòng đời ──────────────────────────────────────────────────────────────

  /// Bắt đầu nhận thông báo sau khi đăng nhập.
  void start() {
    if (_running) return;
    _running = true;
    _caughtUp = false;
    _ticks = 0;
    _lastSync = settings.lastSync;
    final alerted = settings.lastAlerted;
    _alertFloor = alerted == null ? null : DateTime.tryParse(alerted);

    WidgetsBinding.instance.addObserver(this);
    config.addListener(_onServerChanged);

    _socket = RealtimeSocket(
      url: () => config.webSocketUrl,
      accessToken: () => tokens.accessToken,
      refreshSession: _api.refreshSession,
      since: () => _lastSync,
      onNotification: _onRealtime,
      onConnectionChanged: (connected) {
        _realtime = connected;
        notifyListeners();
      },
    )..start();

    _timer = Timer.periodic(_tickInterval, (_) => _tick());
    _bootstrap();
  }

  /// Dừng nhận thông báo và xóa dữ liệu trong bộ nhớ khi đăng xuất.
  void stop() {
    if (!_running) return;
    _running = false;
    WidgetsBinding.instance.removeObserver(this);
    config.removeListener(_onServerChanged);
    _timer?.cancel();
    _timer = null;
    _socket?.stop();
    _socket = null;
    _items.clear();
    _seen.clear();
    _unread = 0;
    _realtime = false;
    _lastSync = null;
    _alertFloor = null;
    _error = null;
    settings.setLastSync(null);
    settings.setLastAlerted(null);
    notifyListeners();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!_running) return;
    if (state == AppLifecycleState.resumed) {
      _socket?.reconnectNow();
      _sync(alert: true);
    }
  }

  void _onServerChanged() {
    if (!_running) return;
    _socket?.reconnectNow();
  }

  Future<void> _bootstrap() async {
    // Lấy bù trước (để hiện banner cho thông báo bị lỡ), sau đó nạp danh sách đầy đủ.
    await _sync(alert: true);
    await refresh();
  }

  void _tick() {
    if (!_running) return;
    _ticks++;
    // Có WebSocket: chỉ đối soát mỗi 30 giây. Không có: đồng bộ mỗi 5 giây.
    if (!_realtime || _ticks % 6 == 0) {
      _sync(alert: true);
    }
  }

  // ── Nhận dữ liệu ──────────────────────────────────────────────────────────

  void _onRealtime(Map<String, dynamic> payload, int? unread) {
    if (!_running) return;
    try {
      final notification = AppNotification.fromJson(payload);
      if (unread != null) _unread = unread;
      _ingest(<AppNotification>[notification], alert: true);
    } catch (_) {
      // Dữ liệu không đúng định dạng: lần đồng bộ REST kế tiếp sẽ lấy lại.
    }
  }

  Future<void> _sync({required bool alert}) async {
    if (!_running || _syncing) return;
    _syncing = true;
    try {
      final result = await _repo.sync(since: _lastSync);
      if (!_running) return;
      if (result.serverTime.isNotEmpty) {
        _lastSync = result.serverTime;
        settings.setLastSync(_lastSync);
      }
      final changedUnread = _unread != result.unread;
      _unread = result.unread;
      final added = _ingest(result.items, alert: alert);
      // Sau lần đồng bộ đầu tiên, mọi thông báo chưa thấy đều là thông báo mới của phiên này.
      _caughtUp = true;
      if (!added && changedUnread) notifyListeners();
    } catch (_) {
      // Mất mạng tạm thời: thử lại ở chu kỳ sau.
    } finally {
      _syncing = false;
    }
  }

  /// Thêm các thông báo chưa từng thấy vào danh sách. Trả `true` nếu có mục mới.
  bool _ingest(List<AppNotification> incoming, {required bool alert}) {
    final fresh = <AppNotification>[];
    for (final item in incoming) {
      if (_seen.add(item.id)) fresh.add(item);
    }
    if (fresh.isEmpty) return false;

    _items.addAll(fresh);
    _items.sort(_newestFirst);
    if (_items.length > _maxItems) _items.removeRange(_maxItems, _items.length);
    notifyListeners();

    // Thay đổi đến từ web/hệ thống: làm mới ví, danh mục và các màn hình đang mở.
    final external = fresh.where((item) => !item.fromThisApp && item.entityType != 'security');
    if (external.isNotEmpty) data.markChanged();

    if (alert) _alert(fresh);
    return true;
  }

  static int _newestFirst(AppNotification a, AppNotification b) {
    final left = a.createdAt;
    final right = b.createdAt;
    if (left == null && right == null) return 0;
    if (left == null) return 1;
    if (right == null) return -1;
    return right.compareTo(left);
  }

  void _alert(List<AppNotification> fresh) {
    // Mốc chống báo lặp chỉ áp dụng cho đợt lấy bù lúc mở ứng dụng: những thông báo
    // đã hiện banner ở lần chạy trước sẽ không hiện lại.
    final floor = _caughtUp ? null : _alertFloor;
    final candidates = <AppNotification>[];
    DateTime? newest = _alertFloor;
    for (final item in fresh) {
      final created = item.createdAt;
      if (created != null && (newest == null || created.isAfter(newest))) newest = created;
      if (item.isRead) continue;
      if (floor != null && created != null && !created.isAfter(floor)) continue;
      if (item.fromThisApp && !settings.alertOwnActions && !item.isAlert) continue;
      candidates.add(item);
    }
    if (newest != null && newest != _alertFloor) {
      _alertFloor = newest;
      settings.setLastAlerted(newest.toUtc().toIso8601String());
    }
    if (candidates.isEmpty || !settings.pushEnabled) return;

    if (candidates.length > 3) {
      final important = candidates.any((item) => item.isAlert);
      notifier.show(
        id: 800001,
        title: 'CapitalFlow · ${candidates.length} thông báo mới',
        body: candidates.take(3).map((item) => item.title).join('\n'),
        payload: 'list',
        important: important,
      );
      return;
    }
    for (final item in candidates) {
      notifier.show(
        id: item.id.hashCode & 0x7fffffff,
        title: item.title,
        body: item.body,
        payload: item.id,
        important: item.isAlert,
      );
    }
  }

  // ── Thao tác của người dùng ───────────────────────────────────────────────

  /// Tải lại danh sách thông báo mới nhất cho màn "Thông báo".
  Future<void> refresh() async {
    if (!_running) return;
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      final page = await _repo.list(pageSize: 60);
      if (!_running) return;
      _items
        ..clear()
        ..addAll(page.items);
      _items.sort(_newestFirst);
      for (final item in page.items) {
        _seen.add(item.id);
      }
      _unread = page.unread;
    } on ApiException catch (error) {
      _error = error.message;
    } catch (_) {
      _error = 'Không tải được thông báo. Vui lòng thử lại.';
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<void> markRead(AppNotification item) async {
    if (item.isRead) return;
    item.isRead = true;
    if (_unread > 0) _unread--;
    notifyListeners();
    try {
      _unread = await _repo.markRead(item.id);
      notifyListeners();
    } catch (_) {
      // Trạng thái sẽ được đối soát ở lần đồng bộ kế tiếp.
    }
  }

  Future<void> markAllRead() async {
    await _repo.markAllRead();
    for (final item in _items) {
      item.isRead = true;
    }
    _unread = 0;
    notifyListeners();
  }

  Future<void> remove(AppNotification item) async {
    final index = _items.indexOf(item);
    if (index < 0) return;
    _items.removeAt(index);
    if (!item.isRead && _unread > 0) _unread--;
    notifyListeners();
    try {
      await _repo.remove(item.id);
    } catch (_) {
      // Nếu xóa thất bại, mục sẽ xuất hiện lại khi tải lại danh sách.
    }
  }

  Future<void> clearRead() async {
    await _repo.clearRead();
    _items.removeWhere((item) => item.isRead);
    notifyListeners();
  }
}
