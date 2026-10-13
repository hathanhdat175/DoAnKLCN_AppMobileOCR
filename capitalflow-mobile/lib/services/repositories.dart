import 'dart:typed_data';

import '../core/api_client.dart';
import '../core/formatters.dart';
import '../models/models.dart';

/// Các lời gọi REST theo từng phân hệ. Mọi thao tác ghi tiền (ví, giao dịch)
/// đều đi kèm `Idempotency-Key` đúng như bản web để backend chống ghi trùng.

class FinanceRepository {
  FinanceRepository(this.api);

  final ApiClient api;

  // ── Ví & tài khoản ────────────────────────────────────────────────────────

  Future<List<Wallet>> wallets() async {
    return asJsonList(await api.get('/accounts')).map(Wallet.fromJson).toList();
  }

  Future<Wallet> createWallet({
    required String name,
    required String accountType,
    required int balance,
    String? institutionName,
  }) async {
    final data = await api.post(
      '/accounts',
      money: true,
      body: {
        'name': name,
        'account_type': accountType,
        'balance': balance,
        'currency': 'VND',
        if (institutionName != null && institutionName.isNotEmpty) 'institution_name': institutionName,
      },
    );
    return Wallet.fromJson(Map<String, dynamic>.from(data as Map));
  }

  Future<Wallet> updateWallet(
    String id, {
    required String name,
    required String accountType,
    required String institutionName,
    int? balance,
  }) async {
    final data = await api.patch(
      '/accounts/$id',
      money: true,
      body: {
        'name': name,
        'account_type': accountType,
        'institution_name': institutionName,
        if (balance != null) 'balance': balance,
      },
    );
    return Wallet.fromJson(Map<String, dynamic>.from(data as Map));
  }

  /// Xóa mềm ví. Backend trả 409 nếu ví còn số dư và chưa truyền `force`.
  Future<void> deleteWallet(String id, {bool force = false}) async {
    await api.delete('/accounts/$id', money: true, query: {if (force) 'force': 'true'});
  }

  // ── Danh mục ──────────────────────────────────────────────────────────────

  Future<List<FinanceCategory>> categories() async {
    return asJsonList(await api.get('/categories')).map(FinanceCategory.fromJson).toList();
  }

  Future<void> createCategory({
    required String name,
    required String type,
    required String icon,
    required String color,
    String? keywords,
  }) async {
    await api.post('/categories', body: {
      'name': name,
      'type': type,
      'icon': icon,
      'color': color,
      'keywords': (keywords == null || keywords.trim().isEmpty) ? null : keywords.trim(),
    });
  }

  Future<void> updateCategory(
    String id, {
    required String name,
    required String icon,
    required String color,
    String? keywords,
  }) async {
    await api.patch('/categories/$id', body: {
      'name': name,
      'icon': icon,
      'color': color,
      'keywords': (keywords == null || keywords.trim().isEmpty) ? null : keywords.trim(),
    });
  }

  Future<void> deleteCategory(String id) async {
    await api.delete('/categories/$id');
  }

  /// Gợi ý danh mục tự động từ diễn giải (lịch sử phân loại + từ khóa danh mục).
  Future<CategorySuggestion> suggestCategory({
    required String type,
    required String description,
    String? note,
    List<String> itemNames = const [],
  }) async {
    final data = await api.post('/categories/suggest', body: {
      'type': type,
      'description': description.length > 255 ? description.substring(0, 255) : description,
      if (note != null && note.isNotEmpty) 'note': note,
      if (itemNames.isNotEmpty) 'item_names': itemNames.take(50).toList(),
    });
    return CategorySuggestion.fromJson(Map<String, dynamic>.from(data as Map));
  }

  // ── Giao dịch ─────────────────────────────────────────────────────────────

  Future<TxnPage> transactions({
    int page = 1,
    int pageSize = 30,
    String? type,
    String? accountId,
    String? categoryId,
    DateTime? startDate,
    DateTime? endDate,
  }) async {
    final data = await api.get('/transactions', query: {
      'page': page,
      'page_size': pageSize,
      'type': type,
      'account_id': accountId,
      'category_id': categoryId,
      'start_date': startDate == null ? null : isoDate(startDate),
      'end_date': endDate == null ? null : isoDate(endDate),
    });
    return TxnPage.fromJson(Map<String, dynamic>.from(data as Map));
  }

  Future<Txn> createTransaction({
    required String accountId,
    required String type,
    required int amount,
    required DateTime date,
    required String description,
    String? categoryId,
    String? note,
  }) async {
    final data = await api.post(
      '/transactions',
      money: true,
      body: {
        'account_id': accountId,
        'type': type,
        'amount': amount,
        'transaction_date': isoDate(date),
        'description': description,
        if (categoryId != null) 'category_id': categoryId,
        if (note != null && note.isNotEmpty) 'note': note,
      },
    );
    return Txn.fromJson(Map<String, dynamic>.from(data as Map));
  }

  Future<Txn> updateTransaction(
    String id, {
    required String accountId,
    required String type,
    required int amount,
    required DateTime date,
    required String description,
    required String? categoryId,
    required String? note,
  }) async {
    final data = await api.patch(
      '/transactions/$id',
      money: true,
      body: {
        'account_id': accountId,
        'type': type,
        'amount': amount,
        'transaction_date': isoDate(date),
        'description': description,
        // Gửi cả giá trị null để người dùng có thể bỏ phân loại/ghi chú.
        'category_id': categoryId,
        'note': (note == null || note.isEmpty) ? null : note,
      },
    );
    return Txn.fromJson(Map<String, dynamic>.from(data as Map));
  }

  Future<void> deleteTransaction(String id) async {
    await api.delete('/transactions/$id', money: true);
  }

  Future<void> transfer({
    required String fromAccountId,
    required String toAccountId,
    required int amount,
    required DateTime date,
    String? note,
  }) async {
    await api.post(
      '/transactions/transfer',
      money: true,
      body: {
        'from_account_id': fromAccountId,
        'to_account_id': toAccountId,
        'amount': amount,
        'transaction_date': isoDate(date),
        if (note != null && note.isNotEmpty) 'note': note,
      },
    );
  }

  // ── Ngân sách ─────────────────────────────────────────────────────────────

  Future<List<BudgetProgress>> budgets() async {
    return asJsonList(await api.get('/budgets')).map(BudgetProgress.fromJson).toList();
  }

  Future<void> createBudget({
    required String name,
    required int amountLimit,
    required String periodType,
    required DateTime startDate,
    required DateTime endDate,
    required int warningPercent,
    String? categoryId,
  }) async {
    await api.post('/budgets', body: {
      'name': name,
      'amount_limit': amountLimit,
      'currency': 'VND',
      'period_type': periodType,
      'start_date': isoDate(startDate),
      'end_date': isoDate(endDate),
      'warning_percent': warningPercent,
      if (categoryId != null) 'category_id': categoryId,
    });
  }

  Future<void> updateBudget(
    String id, {
    required String name,
    required int amountLimit,
    required String periodType,
    required DateTime startDate,
    required DateTime endDate,
    required int warningPercent,
  }) async {
    await api.patch('/budgets/$id', body: {
      'name': name,
      'amount_limit': amountLimit,
      'period_type': periodType,
      'start_date': isoDate(startDate),
      'end_date': isoDate(endDate),
      'warning_percent': warningPercent,
    });
  }

  Future<void> deleteBudget(String id) async {
    await api.delete('/budgets/$id');
  }

  // ── Tổng quan & báo cáo ───────────────────────────────────────────────────

  Future<DashboardData> dashboard() async {
    final data = await api.get('/dashboard');
    return DashboardData.fromJson(Map<String, dynamic>.from(data as Map));
  }

  Future<AnalyticsData> analytics({required DateTime start, required DateTime end}) async {
    final data = await api.get('/analytics', query: {
      'start_date': isoDate(start),
      'end_date': isoDate(end),
    });
    return AnalyticsData.fromJson(Map<String, dynamic>.from(data as Map));
  }
}

class InvoiceRepository {
  InvoiceRepository(this.api);

  final ApiClient api;

  Future<List<InvoiceSummary>> list({String? status, int page = 1, int pageSize = 50}) async {
    final data = await api.get('/invoices', query: {
      'page': page,
      'page_size': pageSize,
      'status': status,
    });
    final map = Map<String, dynamic>.from(data as Map);
    return asJsonList(map['items']).map(InvoiceSummary.fromJson).toList();
  }

  Future<InvoiceDetail> detail(String id) async {
    final data = await api.get('/invoices/$id');
    return InvoiceDetail.fromJson(Map<String, dynamic>.from(data as Map));
  }

  /// Tải ảnh/PDF/XML hóa đơn lên; trả về id hóa đơn vừa tạo.
  Future<InvoiceSummary> upload({required List<int> bytes, required String filename}) async {
    final data = await api.uploadFile('/invoices', bytes: bytes, filename: filename);
    return InvoiceSummary.fromJson(Map<String, dynamic>.from(data as Map));
  }

  /// Đưa hóa đơn vào hàng đợi nhận dạng OCR (worker nền xử lý bằng Gemini).
  Future<void> requestOcr(String id) async {
    await api.post('/invoices/$id/ocr');
  }

  Future<Uint8List> fileBytes(String id) {
    return api.getBytes('/invoices/$id/file');
  }

  /// Xác nhận hóa đơn sau khi người dùng đã kiểm tra/chỉnh sửa kết quả OCR;
  /// backend tạo một khoản chi tương ứng và trừ số dư ví.
  Future<void> confirm(
    String id, {
    required String accountId,
    required int totalAmount,
    required String merchantName,
    required List<InvoiceLine> items,
    String? categoryId,
    DateTime? invoiceDate,
    String? invoiceNumber,
    String? merchantTaxCode,
    String? vatRate,
    int? subtotalAmount,
    int? taxAmount,
    String? note,
  }) async {
    String? clean(String? value) {
      final text = (value ?? '').trim();
      return text.isEmpty ? null : text;
    }

    await api.post('/invoices/$id/confirm', body: {
      'account_id': accountId,
      'total_amount': totalAmount,
      'merchant_name': merchantName.trim(),
      'items': items.where((line) => line.name.trim().isNotEmpty).map((line) => line.toJson()).toList(),
      if (categoryId != null) 'category_id': categoryId,
      if (invoiceDate != null) 'invoice_date': isoDate(invoiceDate),
      if (clean(invoiceNumber) != null) 'invoice_number': clean(invoiceNumber),
      if (clean(merchantTaxCode) != null) 'merchant_tax_code': clean(merchantTaxCode),
      if (clean(vatRate) != null) 'vat_rate': clean(vatRate),
      if (subtotalAmount != null) 'subtotal_amount': subtotalAmount,
      if (taxAmount != null) 'tax_amount': taxAmount,
      if (clean(note) != null) 'note': clean(note),
    });
  }

  Future<void> delete(String id) async {
    await api.delete('/invoices/$id');
  }
}

class NotificationPageResult {
  NotificationPageResult({required this.items, required this.total, required this.unread});

  final List<AppNotification> items;
  final int total;
  final int unread;
}

class NotificationSyncResult {
  NotificationSyncResult({required this.items, required this.unread, required this.serverTime});

  final List<AppNotification> items;
  final int unread;

  /// Mốc thời gian của máy chủ, gửi lại ở lần đồng bộ kế tiếp.
  final String serverTime;
}

class NotificationRepository {
  NotificationRepository(this.api);

  final ApiClient api;

  Future<NotificationPageResult> list({int page = 1, int pageSize = 30, bool unreadOnly = false}) async {
    final data = await api.get('/notifications', query: {
      'page': page,
      'page_size': pageSize,
      if (unreadOnly) 'unread_only': 'true',
    });
    final map = Map<String, dynamic>.from(data as Map);
    return NotificationPageResult(
      items: asJsonList(map['items']).map(AppNotification.fromJson).toList(),
      total: asInt(map['total']),
      unread: asInt(map['unread']),
    );
  }

  /// Lấy thông báo mới kể từ mốc `since` (đường dự phòng khi WebSocket gián đoạn).
  Future<NotificationSyncResult> sync({String? since}) async {
    final data = await api.get('/notifications/sync', query: {'since': since, 'limit': 100});
    final map = Map<String, dynamic>.from(data as Map);
    return NotificationSyncResult(
      items: asJsonList(map['items']).map(AppNotification.fromJson).toList(),
      unread: asInt(map['unread']),
      serverTime: (map['server_time'] ?? '').toString(),
    );
  }

  Future<int> markRead(String id) async {
    final data = await api.post('/notifications/$id/read');
    return asInt(Map<String, dynamic>.from(data as Map)['unread']);
  }

  Future<void> markAllRead() async {
    await api.post('/notifications/read-all');
  }

  Future<void> remove(String id) async {
    await api.delete('/notifications/$id');
  }

  Future<void> clearRead() async {
    await api.delete('/notifications', query: {'only_read': 'true'});
  }
}

class AdminRepository {
  AdminRepository(this.api);

  final ApiClient api;

  Future<AdminOverview> overview() async {
    final data = await api.get('/admin/overview');
    return AdminOverview.fromJson(Map<String, dynamic>.from(data as Map));
  }

  Future<List<AdminUser>> users({String? search, String? status, int page = 1, int pageSize = 50}) async {
    final data = await api.get('/admin/users', query: {
      'page': page,
      'page_size': pageSize,
      'search': search,
      'status': status,
    });
    final map = Map<String, dynamic>.from(data as Map);
    return asJsonList(map['items']).map(AdminUser.fromJson).toList();
  }

  Future<String> createUser({required String email, required String fullName, required String role}) async {
    final data = await api.post('/admin/users', body: {
      'email': email,
      'full_name': fullName,
      'role': role,
    });
    return (Map<String, dynamic>.from(data as Map)['message'] ?? 'Đã tạo tài khoản.').toString();
  }

  Future<void> ban(String userId) async {
    await api.patch('/admin/users/$userId/ban');
  }

  Future<void> unban(String userId) async {
    await api.patch('/admin/users/$userId/unban');
  }

  Future<void> resetPassword(String userId) async {
    await api.post('/admin/users/$userId/reset-password');
  }
}
