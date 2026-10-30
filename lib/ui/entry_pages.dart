import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../app_controller.dart';
import '../core/crypto.dart';
import '../core/models.dart';
import 'vault_app.dart';

class EntryEditor extends StatefulWidget {
  const EntryEditor({super.key, required this.controller, this.entry});
  final AppController controller;
  final VaultEntry? entry;
  @override
  State<EntryEditor> createState() => _EntryEditorState();
}

class _EntryEditorState extends State<EntryEditor> {
  final _form = GlobalKey<FormState>();
  late final Map<String, TextEditingController> _fields;
  late EntryKind _kind;
  late ExpiryKind _expiryKind;
  DateTime? _expiry;
  bool _remind = true;
  AppController get c => widget.controller;

  @override
  void initState() {
    super.initState();
    final e = widget.entry;
    _fields = {
      '名称': TextEditingController(text: e?.name),
      '持有人': TextEditingController(text: e?.holder),
      '证件类型': TextEditingController(text: e?.certificateType),
      '号码': TextEditingController(text: e?.number),
      '分类': TextEditingController(text: e?.category),
      '标签（以逗号分隔）': TextEditingController(text: e?.tags.join(', ')),
      '备注': TextEditingController(text: e?.notes),
    };
    _kind = e?.kind ?? EntryKind.certificate;
    _expiryKind = e?.expiryKind ?? ExpiryKind.unknown;
    _expiry = e?.expiry;
    _remind = e?.remind ?? true;
  }

  @override
  void dispose() {
    for (final controller in _fields.values) {
      controller.dispose();
    }
    super.dispose();
  }

  String _text(String key) => _fields[key]!.text.trim();

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    final entry = VaultEntry(
      id: widget.entry?.id ?? VaultCrypto.id(),
      kind: _kind,
      name: _text('名称'),
      holder: _kind == EntryKind.certificate ? _text('持有人') : '',
      certificateType: _kind == EntryKind.certificate ? _text('证件类型') : '',
      number: _kind == EntryKind.certificate ? _text('号码') : '',
      category: _text('分类'),
      tags: _text('标签（以逗号分隔）')
          .split(RegExp('[,，]'))
          .map((v) => v.trim())
          .where((v) => v.isNotEmpty)
          .toSet()
          .toList(),
      notes: _text('备注'),
      expiryKind: _expiryKind,
      expiry: _expiryKind == ExpiryKind.dated ? _expiry : null,
      remind: _remind,
      attachments: widget.entry?.attachments ?? [],
    );
    final success = await c.run(() async {
      if (_expiryKind == ExpiryKind.dated && _expiry == null) {
        throw const VaultException('请选择到期日期。');
      }
      await c.store.saveEntry(entry, []);
      await c.refreshReminders();
    });
    if (success && mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: c,
    builder: (context, _) => Scaffold(
      appBar: AppBar(title: Text(widget.entry == null ? '新增资料' : '编辑资料')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: Form(
            key: _form,
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                if (widget.entry == null) ...[
                  SegmentedButton<EntryKind>(
                    segments: const [
                      ButtonSegment(
                        value: EntryKind.certificate,
                        label: Text('证件'),
                      ),
                      ButtonSegment(
                        value: EntryKind.document,
                        label: Text('重要文件'),
                      ),
                    ],
                    selected: {_kind},
                    onSelectionChanged: c.busy
                        ? null
                        : (v) => setState(() => _kind = v.single),
                  ),
                  const SizedBox(height: 20),
                ],
                for (final field in _fields.entries)
                  if (_kind == EntryKind.certificate ||
                      !['持有人', '证件类型', '号码'].contains(field.key))
                    Padding(
                      padding: const EdgeInsets.only(bottom: 16),
                      child: TextFormField(
                        controller: field.value,
                        autocorrect: false,
                        enableSuggestions: false,
                        enableIMEPersonalizedLearning: false,
                        maxLength: field.key == '备注' ? 10000 : 256,
                        maxLines: field.key == '备注' ? 4 : 1,
                        decoration: InputDecoration(
                          labelText: field.key,
                          counterText: '',
                        ),
                        validator: (value) =>
                            field.key == '名称' &&
                                (value == null || value.trim().isEmpty)
                            ? '请填写名称'
                            : null,
                      ),
                    ),
                DropdownButtonFormField<ExpiryKind>(
                  initialValue: _expiryKind,
                  decoration: const InputDecoration(labelText: '有效期'),
                  items: const [
                    DropdownMenuItem(
                      value: ExpiryKind.unknown,
                      child: Text('未设置'),
                    ),
                    DropdownMenuItem(
                      value: ExpiryKind.permanent,
                      child: Text('长期有效'),
                    ),
                    DropdownMenuItem(
                      value: ExpiryKind.dated,
                      child: Text('指定到期日期'),
                    ),
                  ],
                  onChanged: c.busy
                      ? null
                      : (v) => setState(() => _expiryKind = v!),
                ),
                if (_expiryKind == ExpiryKind.dated) ...[
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: () async {
                      final picked = await showDatePicker(
                        context: context,
                        initialDate: _expiry ?? DateTime.now(),
                        firstDate: DateTime(1900),
                        lastDate: DateTime(2200),
                      );
                      if (picked != null && mounted) {
                        setState(() => _expiry = picked);
                      }
                    },
                    icon: const Icon(Icons.calendar_today_outlined),
                    label: Text(
                      _expiry == null ? '选择到期日期' : formatDate(_expiry!),
                    ),
                  ),
                  SwitchListTile(
                    title: const Text('启用此条目的到期提醒'),
                    subtitle: const Text('提前 30 天、7 天及到期当天；还需在设置中允许本地通知'),
                    value: _remind,
                    onChanged: (v) => setState(() => _remind = v),
                  ),
                ],
                const SizedBox(height: 16),
                const Text('先保存资料信息，再在详情页添加图片或 PDF。系统文件选择前会锁定资料库。'),
                StatusMessages(controller: c),
                FilledButton(
                  onPressed: c.busy ? null : _save,
                  child: const Text('加密保存'),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

class EntryDetails extends StatefulWidget {
  const EntryDetails({
    super.key,
    required this.controller,
    required this.id,
    required this.onPickAttachment,
  });
  final AppController controller;
  final String id;
  final PickAttachment onPickAttachment;
  @override
  State<EntryDetails> createState() => _EntryDetailsState();
}

class _EntryDetailsState extends State<EntryDetails> {
  bool _numberVisible = false;
  Timer? _hideTimer;
  AppController get c => widget.controller;
  @override
  void dispose() {
    _hideTimer?.cancel();
    super.dispose();
  }

  Future<void> _delete(VaultEntry e) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除资料？'),
        content: const Text('此操作会删除本机条目及其附件，不能撤销。已导出的备份不会受到影响。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    final ok = await c.run(() async {
      await c.store.deleteEntry(e.id);
      await c.refreshReminders();
    });
    if (ok && mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: c,
    builder: (context, _) {
      final e = c.store.entries.where((e) => e.id == widget.id).firstOrNull;
      if (e == null) {
        return const Scaffold(body: Center(child: Text('条目已删除或资料库已锁定')));
      }
      return Scaffold(
        appBar: AppBar(
          title: Text(e.name),
          actions: [
            IconButton(
              tooltip: '编辑',
              icon: const Icon(Icons.edit_outlined),
              onPressed: c.busy
                  ? null
                  : () => Navigator.push(
                      context,
                      MaterialPageRoute<void>(
                        builder: (_) => EntryEditor(controller: c, entry: e),
                      ),
                    ),
            ),
            IconButton(
              tooltip: '删除',
              icon: const Icon(Icons.delete_outline),
              onPressed: c.busy ? null : () => _delete(e),
            ),
          ],
        ),
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 800),
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                StatusMessages(controller: c),
                if (e.kind == EntryKind.certificate) ...[
                  ListTile(
                    title: const Text('持有人'),
                    subtitle: Text(e.holder.isEmpty ? '未填写' : e.holder),
                  ),
                  ListTile(
                    title: const Text('证件类型'),
                    subtitle: Text(
                      e.certificateType.isEmpty ? '未填写' : e.certificateType,
                    ),
                  ),
                  ListTile(
                    title: const Text('号码'),
                    subtitle: Text(
                      e.number.isEmpty
                          ? '未填写'
                          : _numberVisible
                          ? e.number
                          : '•••• •••• ••••',
                    ),
                    trailing: IconButton(
                      tooltip: _numberVisible ? '遮挡号码' : '显示 15 秒',
                      icon: Icon(
                        _numberVisible
                            ? Icons.visibility_off
                            : Icons.visibility,
                      ),
                      onPressed: () {
                        _hideTimer?.cancel();
                        setState(() => _numberVisible = !_numberVisible);
                        if (_numberVisible) {
                          _hideTimer = Timer(const Duration(seconds: 15), () {
                            if (mounted) setState(() => _numberVisible = false);
                          });
                        }
                      },
                    ),
                  ),
                ],
                ListTile(
                  title: const Text('分类'),
                  subtitle: Text(e.category.isEmpty ? '未分类' : e.category),
                ),
                ListTile(
                  title: const Text('有效期'),
                  subtitle: Text(e.expiryLabel),
                ),
                if (e.tags.isNotEmpty)
                  Wrap(
                    spacing: 8,
                    children: e.tags.map((t) => Chip(label: Text(t))).toList(),
                  ),
                if (e.notes.isNotEmpty)
                  ListTile(title: const Text('备注'), subtitle: Text(e.notes)),
                const Divider(height: 32),
                Text('加密附件', style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 8),
                const Text('仅在应用内解密预览。添加附件时会先锁定；选择后重新解锁即可导入。单文件不超过 32 MB。'),
                for (final a in e.attachments)
                  ListTile(
                    leading: Icon(
                      a.type == 'pdf'
                          ? Icons.picture_as_pdf_outlined
                          : Icons.image_outlined,
                    ),
                    title: Text(a.name),
                    subtitle: Text(
                      '${switch (a.role) {
                        'front' => '正面',
                        'back' => '反面',
                        _ => '文件',
                      }} · ${(a.size / 1024).ceil()} KB',
                    ),
                    onTap: c.busy
                        ? null
                        : () => Navigator.push(
                            context,
                            MaterialPageRoute<void>(
                              builder: (_) => AttachmentPreview(
                                controller: c,
                                attachment: a,
                              ),
                            ),
                          ),
                    trailing: IconButton(
                      tooltip: '移除此附件',
                      icon: const Icon(Icons.close),
                      onPressed: c.busy
                          ? null
                          : () async {
                              final confirmed = await showDialog<bool>(
                                context: context,
                                builder: (context) => AlertDialog(
                                  title: const Text('移除此附件？'),
                                  content: const Text(
                                    '加密副本将从本机删除，原始文件和已有备份不会更改。',
                                  ),
                                  actions: [
                                    TextButton(
                                      onPressed: () =>
                                          Navigator.pop(context, false),
                                      child: const Text('取消'),
                                    ),
                                    FilledButton(
                                      onPressed: () =>
                                          Navigator.pop(context, true),
                                      child: const Text('移除'),
                                    ),
                                  ],
                                ),
                              );
                              if (confirmed != true) return;
                              await c.run(() async {
                                final json = e.toJson();
                                json['attachments'] = e.attachments
                                    .where((v) => v.id != a.id)
                                    .map((v) => v.toJson())
                                    .toList();
                                await c.store.saveEntry(
                                  VaultEntry.fromJson(json),
                                  [],
                                );
                              });
                            },
                    ),
                  ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 12,
                  children: e.kind == EntryKind.certificate
                      ? [
                          OutlinedButton.icon(
                            onPressed: c.busy
                                ? null
                                : () => widget.onPickAttachment(e.id, 'front'),
                            icon: const Icon(
                              Icons.add_photo_alternate_outlined,
                            ),
                            label: const Text('添加／替换正面'),
                          ),
                          OutlinedButton.icon(
                            onPressed: c.busy
                                ? null
                                : () => widget.onPickAttachment(e.id, 'back'),
                            icon: const Icon(
                              Icons.add_photo_alternate_outlined,
                            ),
                            label: const Text('添加／替换反面'),
                          ),
                        ]
                      : [
                          OutlinedButton.icon(
                            onPressed: c.busy
                                ? null
                                : () => widget.onPickAttachment(e.id, 'file'),
                            icon: const Icon(Icons.attach_file),
                            label: const Text('导入图片或 PDF'),
                          ),
                        ],
                ),
              ],
            ),
          ),
        ),
      );
    },
  );
}

class AttachmentPreview extends StatefulWidget {
  const AttachmentPreview({
    super.key,
    required this.controller,
    required this.attachment,
  });
  final AppController controller;
  final VaultAttachment attachment;
  @override
  State<AttachmentPreview> createState() => _AttachmentPreviewState();
}

class _AttachmentPreviewState extends State<AttachmentPreview> {
  Uint8List? _bytes;
  String? _error;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final bytes = await widget.controller.store.readAttachment(
        widget.attachment,
      );
      if (!mounted) {
        bytes.fillRange(0, bytes.length, 0);
        return;
      }
      setState(() => _bytes = bytes);
    } catch (failure) {
      if (mounted) {
        setState(
          () => _error = failure is VaultException
              ? failure.message
              : '附件读取失败（${failure.runtimeType}）。',
        );
      }
    }
  }

  @override
  void dispose() {
    _bytes?.fillRange(0, _bytes!.length, 0);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.attachment.name)),
    body: _error != null
        ? Center(child: Text(_error!))
        : _bytes == null
        ? const Center(child: CircularProgressIndicator())
        : widget.attachment.type == 'pdf'
        ? widget.controller.pdfPreviewBuilder(_bytes!, widget.attachment.id)
        : InteractiveViewer(
            minScale: 0.5,
            maxScale: 5,
            child: Center(
              child: Image.memory(
                _bytes!,
                gaplessPlayback: false,
                errorBuilder: (_, _, _) => const Text('图片内容无法解码，请检查原文件。'),
              ),
            ),
          ),
  );
}
