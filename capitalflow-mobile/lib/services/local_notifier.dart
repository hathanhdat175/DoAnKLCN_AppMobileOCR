import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest_all.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

/// Hiển thị thông báo hệ thống của Android (banner + khay thông báo) và đặt lịch
/// nhắc ghi chép chi tiêu hằng ngày.
///
/// Mọi lỗi của plugin đều được nuốt lại: thiếu quyền thông báo không được phép
/// làm gián đoạn các chức năng tài chính của ứng dụng.
class LocalNotifier {
  static const int reminderId = 900001;

  static const String _channelGeneral = 'capitalflow_activity';
  static const String _channelAlerts = 'capitalflow_alerts';
  static const String _channelReminder = 'capitalflow_reminder';

  final FlutterLocalNotificationsPlugin _plugin = FlutterLocalNotificationsPlugin();

  bool _ready = false;

  /// Gọi khi người dùng chạm vào một thông báo hệ thống; tham số là id thông báo.
  void Function(String? payload)? onTap;

  Future<void> init() async {
    if (_ready) return;
    try {
      tzdata.initializeTimeZones();
      const android = AndroidInitializationSettings('@mipmap/ic_launcher');
      const settings = InitializationSettings(android: android);
      await _plugin.initialize(
        settings,
        onDidReceiveNotificationResponse: (NotificationResponse response) {
          onTap?.call(response.payload);
        },
      );
      _ready = true;
    } catch (_) {
      _ready = false;
    }
  }

  /// Xin quyền hiển thị thông báo (bắt buộc từ Android 13). Trả về `true` nếu được cấp.
  Future<bool> requestPermission() async {
    await init();
    if (!_ready) return false;
    try {
      final android =
          _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
      final granted = await android?.requestNotificationsPermission();
      return granted ?? true;
    } catch (_) {
      return false;
    }
  }

  /// Hiện một thông báo ngay lập tức. [important] dùng kênh ưu tiên cao cho cảnh báo ngân sách.
  Future<void> show({
    required int id,
    required String title,
    required String body,
    String? payload,
    bool important = false,
  }) async {
    await init();
    if (!_ready) return;
    try {
      final details = NotificationDetails(
        android: AndroidNotificationDetails(
          important ? _channelAlerts : _channelGeneral,
          important ? 'Cảnh báo ngân sách' : 'Hoạt động tài khoản',
          channelDescription: important
              ? 'Cảnh báo khi chi tiêu chạm hoặc vượt hạn mức ngân sách'
              : 'Thông báo khi dữ liệu tài chính thay đổi trên web hoặc thiết bị khác',
          importance: Importance.high,
          priority: Priority.high,
          styleInformation: BigTextStyleInformation(body),
        ),
      );
      await _plugin.show(id, title, body, details, payload: payload);
    } catch (_) {
      // Không có quyền hoặc plugin lỗi: bỏ qua, thông báo vẫn nằm trong ứng dụng.
    }
  }

  /// Đặt lịch nhắc hằng ngày vào [hour]:[minute] theo giờ của thiết bị.
  Future<bool> scheduleDailyReminder({required int hour, required int minute}) async {
    await init();
    if (!_ready) return false;
    try {
      final now = DateTime.now();
      var next = DateTime(now.year, now.month, now.day, hour, minute);
      if (!next.isAfter(now)) next = next.add(const Duration(days: 1));
      // Quy về một mốc UTC tuyệt đối; lặp lại theo "giờ trong ngày" nên luôn rơi vào
      // đúng giờ địa phương đã chọn (Việt Nam không đổi giờ theo mùa).
      final utc = next.toUtc();
      final scheduled = tz.TZDateTime.utc(utc.year, utc.month, utc.day, utc.hour, utc.minute);
      const details = NotificationDetails(
        android: AndroidNotificationDetails(
          _channelReminder,
          'Nhắc ghi chép chi tiêu',
          channelDescription: 'Nhắc bạn ghi lại các khoản thu chi trong ngày',
          importance: Importance.defaultImportance,
          priority: Priority.defaultPriority,
        ),
      );
      await _plugin.cancel(reminderId);
      await _plugin.zonedSchedule(
        reminderId,
        'Đừng quên ghi chép chi tiêu hôm nay',
        'Dành một phút ghi lại các khoản thu chi để ngân sách luôn chính xác.',
        scheduled,
        details,
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        matchDateTimeComponents: DateTimeComponents.time,
        payload: 'reminder',
      );
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> cancelDailyReminder() async {
    await init();
    if (!_ready) return;
    try {
      await _plugin.cancel(reminderId);
    } catch (_) {
      // Không có lịch nào để hủy.
    }
  }
}
