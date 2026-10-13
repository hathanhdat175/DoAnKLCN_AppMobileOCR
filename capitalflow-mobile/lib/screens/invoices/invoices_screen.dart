import 'dart:async';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../core/formatters.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../services/app_data.dart';
import '../../widgets/auto_refresh.dart';
import '../../widgets/common.dart';
import 'invoice_common.dart';
import 'invoice_review_screen.dart';

/// Cách bắt đầu khi mở màn hóa đơn từ nút tắt ở trang chủ.
enum InvoiceStartAction { camera, gallery }

/// Hóa đơn AI: chụp hoặc tải hóa đơn lên, lưu trữ, tra cứu và theo dõi trạng thái nhận dạng OCR.
class InvoicesScreen extends StatefulWidget {
  const InvoicesScreen({super.key, this.startAction});

  final InvoiceStartAction? startAction;

  @override
  State<InvoicesScreen> createState() => _InvoicesScreenState();
}

class _InvoicesScreenState extends State<InvoicesScreen> with AutoRefresh<InvoicesScreen> {
  static const List<MapEntry<String, String>> _filters = [
    MapEntry('ALL', 'Tất cả'),
    MapEntry('REVIEW_REQUIRED', 'Cần kiểm tra'),
    MapEntry('PROCESSING', 'Đang quét'),
    MapEntry('UPLOADED', 'Chờ quét'),
    MapEntry('CONFIRMED', 'Đã ghi sổ'),
    MapEntry('FAILED', 'Quét lỗi'),
  ];

  final ImagePicker _picker = ImagePicker();

  List<InvoiceSummary> _invoices = <InvoiceSummary>[];
  String _filter = 'ALL';
  String _query = '';
  bool _loading = true;
  bool _uploading = false;
  String? _error;
  Timer? _pollTimer;
  int _request = 0;

  @override
  void initState() {
    super.initState();
    final action = widget.startAction;
    if (action != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        if (action == InvoiceStartAction.camera) {
          _pickImage(ImageSource.camera);
        } else {
          _pickImage(ImageSource.gallery);
        }
      });
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  @override
  Future<void> reload() async {
    final request = ++_request;
    final appData = context.read<AppData>();
    try {
      final invoices = await appData.invoices.list(status: _filter == 'ALL' ? null : _filter, pageSize: 100);
      if (!mounted || request != _request) return;
      setState(() {
        _invoices = invoices;
        _error = null;
        _loading = false;
      });
      _schedulePolling();
    } catch (error) {
      if (!mounted || request != _request) return;
      setState(() {
        _error = errorText(error);
        _loading = false;
      });
    }
  }

  /// Khi còn hóa đơn đang quét, tự kiểm tra lại mỗi 4 giây cho tới khi worker xử lý xong.
  void _schedulePolling() {
    _pollTimer?.cancel();
    _pollTimer = null;
    if (_invoices.any((invoice) => invoice.status == 'PROCESSING')) {
      _pollTimer = Timer(const Duration(seconds: 4), () {
        if (mounted) reload();
      });
    }
  }

  void _setFilter(String value) {
    if (value == _filter) return;
    setState(() {
      _filter = value;
      _loading = true;
      _invoices = <InvoiceSummary>[];
    });
    reload();
  }

  // ── Chụp / chọn tệp và tải lên ────────────────────────────────────────────

  void _openAddSheet() {
    showPickerSheet<void>(
      context,
      title: 'Thêm hóa đơn',
      children: (sheetContext) => [
        SheetOption(
          title: 'Chụp ảnh hóa đơn',
          subtitle: 'Dùng camera để chụp hóa đơn giấy',
          leading: const IconBadge(icon: Icons.photo_camera_outlined, color: AppColors.blue, size: 40),
          onTap: () {
            Navigator.of(sheetContext).pop();
            _pickImage(ImageSource.camera);
          },
        ),
        SheetOption(
          title: 'Chọn ảnh từ thư viện',
          subtitle: 'Ảnh hóa đơn đã chụp sẵn (JPG, PNG, WEBP)',
          leading: const IconBadge(icon: Icons.photo_library_outlined, color: AppColors.success, size: 40),
          onTap: () {
            Navigator.of(sheetContext).pop();
            _pickImage(ImageSource.gallery);
          },
        ),
        SheetOption(
          title: 'Chọn tệp PDF / XML',
          subtitle: 'Hóa đơn điện tử dạng PDF hoặc XML (đọc trực tiếp, không cần quét)',
          leading: const IconBadge(icon: Icons.description_outlined, color: AppColors.amber, size: 40),
          onTap: () {
            Navigator.of(sheetContext).pop();
            _pickFile();
          },
        ),
      ],
    );
  }

  Future<void> _pickImage(ImageSource source) async {
    if (_uploading) return;
    try {
      final file = await _picker.pickImage(source: source, imageQuality: 88, maxWidth: 2400, maxHeight: 2400);
      if (file == null) return;
      await _upload(await file.readAsBytes(), file.name);
    } catch (error) {
      showSnack(
        source == ImageSource.camera
            ? 'Không mở được camera. Hãy kiểm tra quyền truy cập camera của ứng dụng.'
            : 'Không đọc được ảnh đã chọn.',
        error: true,
      );
    }
  }

  Future<void> _pickFile() async {
    if (_uploading) return;
    try {
      const group = XTypeGroup(
        label: 'Hóa đơn',
        extensions: <String>['pdf', 'xml', 'jpg', 'jpeg', 'png', 'webp'],
        mimeTypes: <String>['application/pdf', 'text/xml', 'application/xml', 'image/jpeg', 'image/png', 'image/webp'],
      );
      final file = await openFile(acceptedTypeGroups: <XTypeGroup>[group]);
      if (file == null) return;
      await _upload(await file.readAsBytes(), file.name);
    } catch (error) {
      showSnack('Không đọc được tệp đã chọn.', error: true);
    }
  }

  Future<void> _upload(List<int> bytes, String originalName) async {
    if (bytes.isEmpty) {
      showSnack('Tệp rỗng, không thể tải lên.', error: true);
      return;
    }
    if (bytes.length > maxInvoiceBytes) {
      showSnack('Tệp quá lớn (tối đa 10 MB).', error: true);
      return;
    }
    final extension = detectInvoiceExtension(bytes, originalName);
    if (extension == null) {
      showSnack('Định dạng không hỗ trợ. Hãy dùng ảnh JPG/PNG/WEBP, PDF hoặc XML.', error: true);
      return;
    }
    if (!mounted) return;
    final appData = context.read<AppData>();
    setState(() => _uploading = true);
    try {
      final uploaded = await appData.invoices.upload(
        bytes: bytes,
        filename: invoiceUploadName(originalName, extension),
      );
      // Ảnh/PDF cần quét AI; XML đã được backend đọc trực tiếp nên bỏ qua bước này.
      var queued = false;
      if (uploaded.status == 'UPLOADED') {
        try {
          await appData.invoices.requestOcr(uploaded.id);
          queued = true;
        } catch (_) {
          // Người dùng có thể bấm "Quét AI" lại trong màn chi tiết.
        }
      }
      await appData.markChanged();
      if (!mounted) return;
      setState(() => _uploading = false);
      showSnack(queued ? 'Đã tải lên. AI đang nhận dạng hóa đơn...' : 'Đã tải hóa đơn lên.');
      await pushScreen<bool>(context, InvoiceReviewScreen(invoiceId: uploaded.id));
    } catch (error) {
      showSnack(errorText(error), error: true);
      if (mounted) setState(() => _uploading = false);
    }
  }

  // ── Giao diện ─────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final query = _query.trim().toLowerCase();
    final visible = query.isEmpty
        ? _invoices
        : _invoices.where((invoice) => invoice.displayName.toLowerCase().contains(query)).toList();

    Widget content;
    if (_loading && _invoices.isEmpty) {
      content = ListView(children: const [SizedBox(height: 120), LoadingView()]);
    } else if (_error != null && _invoices.isEmpty) {
      content = ListView(children: [const SizedBox(height: 60), ErrorView(message: _error!, onRetry: reload)]);
    } else if (visible.isEmpty) {
      content = ListView(
        children: [
          const SizedBox(height: 30),
          EmptyView(
            icon: Icons.document_scanner_outlined,
            title: _filter == 'ALL' && query.isEmpty ? 'Chưa có hóa đơn nào' : 'Không có hóa đơn phù hợp',
            message: _filter == 'ALL' && query.isEmpty
                ? 'Chụp hoặc tải hóa đơn lên, AI sẽ nhận dạng cửa hàng, ngày, sản phẩm, tổng tiền và thuế VAT.'
                : 'Hãy thử đổi bộ lọc hoặc từ khóa tìm kiếm.',
            actionLabel: _filter == 'ALL' && query.isEmpty ? 'Thêm hóa đơn' : null,
            onAction: _filter == 'ALL' && query.isEmpty ? _openAddSheet : null,
          ),
        ],
      );
    } else {
      content = ListView.builder(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 96),
        itemCount: visible.length,
        itemBuilder: (context, index) {
          final invoice = visible[index];
          return Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: _InvoiceCard(
              invoice: invoice,
              onTap: () => pushScreen<bool>(context, InvoiceReviewScreen(invoiceId: invoice.id)),
            ),
          );
        },
      );
    }

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: appBar('Hóa đơn AI'),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _uploading ? null : _openAddSheet,
        icon: const Icon(Icons.add_a_photo_outlined),
        label: const Text('Thêm hóa đơn'),
      ),
      body: Stack(
        children: [
          Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
                child: TextField(
                  textInputAction: TextInputAction.search,
                  onChanged: (value) => setState(() => _query = value),
                  decoration: fieldDecoration('Tìm theo cửa hàng hoặc tên tệp', icon: Icons.search),
                ),
              ),
              SizedBox(
                height: 40,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: _filters.length,
                  separatorBuilder: (_, __) => const SizedBox(width: 8),
                  itemBuilder: (context, index) {
                    final option = _filters[index];
                    final selected = option.key == _filter;
                    return ChoiceChip(
                      label: Text(option.value),
                      selected: selected,
                      showCheckmark: false,
                      onSelected: (_) => _setFilter(option.key),
                      selectedColor: AppColors.soft,
                      backgroundColor: AppColors.surface,
                      side: BorderSide(color: selected ? AppColors.blue : AppColors.line),
                      labelStyle: TextStyle(
                        fontSize: 13,
                        fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                        color: selected ? AppColors.blue : AppColors.muted,
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: RefreshIndicator(onRefresh: reload, color: AppColors.blue, child: content),
              ),
            ],
          ),
          if (_uploading)
            Positioned.fill(
              child: ColoredBox(
                color: const Color(0x99172033),
                child: Center(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 22),
                    decoration: BoxDecoration(color: AppColors.surface, borderRadius: BorderRadius.circular(16)),
                    child: const Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        SizedBox(width: 30, height: 30, child: CircularProgressIndicator(strokeWidth: 3)),
                        SizedBox(height: 14),
                        Text('Đang tải hóa đơn lên...', style: TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600)),
                      ],
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _InvoiceCard extends StatelessWidget {
  const _InvoiceCard({required this.invoice, required this.onTap});

  final InvoiceSummary invoice;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final style = invoiceStatusStyle(invoice.status);
    final typeIcon = invoice.isXml
        ? Icons.code
        : invoice.isImage
            ? Icons.image_outlined
            : Icons.picture_as_pdf_outlined;
    final details = <String>[
      if (invoice.invoiceDate != null) 'Ngày ${formatDate(invoice.invoiceDate)}',
      'Tải lên ${relativeTime(invoice.createdAt)}',
    ];
    final total = invoice.totalAmount;

    return AppCard(
      onTap: onTap,
      child: Row(
        children: [
          IconBadge(icon: typeIcon, color: style.color, size: 46),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  invoice.displayName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 3),
                Text(
                  details.join(' · '),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 12.5, color: AppColors.muted),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    InvoiceStatusChip(invoice.status),
                    const Spacer(),
                    if (total != null && total > 0)
                      Text(formatMoney(total), style: moneyStyle.copyWith(fontSize: 15, color: AppColors.ink)),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
