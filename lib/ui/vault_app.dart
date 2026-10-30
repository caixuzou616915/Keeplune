import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import '../app_controller.dart';
import '../core/crypto.dart';
import '../core/models.dart';
import '../core/vault_store.dart';
import '../services/file_access.dart';
import 'entry_pages.dart';
import 'settings_page.dart';

class VaultApp extends StatefulWidget {
  const VaultApp({super.key, required this.controller});
  final AppController controller;
  @override
  State<VaultApp> createState() => _VaultAppState();
}

class _VaultAppState extends State<VaultApp> {
  XFile? _pendingFile;
  String? _pendingEntry;
  String? _pendingRole;
  XFile? _pendingBackup;
  AppController get c => widget.controller;

  Future<void> _pickBackup() async {
    _pendingFile = null;
    _pendingEntry = null;
    _pendingRole = null;
    c.lock();
    await c.run(() async {
      final selected = await FileAccess.pickBackup();
      if (selected != null && mounted) {
        setState(() => _pendingBackup = selected);
      }
    });
  }

  Future<void> _pickAttachment(String entryId, String role) async {
    // Close all decrypted UI before opening another application's file provider.
    c.lock();
    await c.run(() async {
      final selected = await FileAccess.pickMedia(role != 'file');
      if (selected == null) return;
      _pendingFile = selected;
      _pendingEntry = entryId;
      _pendingRole = role;
      c.notice = '已选择附件。重新解锁后会加密导入，原文件不会被删除。';
    });
  }

  Future<void> _afterUnlock() async {
    final file = _pendingFile;
    final entryId = _pendingEntry;
    final role = _pendingRole;
    _pendingFile = null;
    _pendingEntry = null;
    _pendingRole = null;
    if (file != null && entryId != null && role != null) {
      final original = c.store.entries
          .where((e) => e.id == entryId)
          .firstOrNull;
      if (original == null) throw const VaultException('待导入附件的条目已不存在。');
      final bytes = await FileAccess.readLimited(
        file,
        VaultStore.maxAttachmentBytes,
      );
      try {
        if (!c.store.unlocked) throw const VaultException('资料库已锁定，请重新选择附件。');
        final type = FileAccess.mediaType(file.name);
        VaultStore.validateMedia(bytes, type);
        final metadata = VaultAttachment(
          id: VaultCrypto.id(),
          name: file.name,
          role: role,
          type: type,
          size: bytes.length,
        );
        final json = original.toJson();
        json['attachments'] = [
          ...original.attachments
              .where((a) => role == 'file' || a.role != role)
              .map((a) => a.toJson()),
          metadata.toJson(),
        ];
        await c.store.saveEntry(VaultEntry.fromJson(json), [
          PendingAttachment(metadata, bytes),
        ]);
      } finally {
        bytes.fillRange(0, bytes.length, 0);
      }
      c.notice = '附件已加密导入。';
    }
    await c.refreshReminders();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: c,
    builder: (context, _) => MaterialApp(
      key: ValueKey(c.viewGeneration),
      title: '离线资料柜',
      debugShowCheckedModeBanner: false,
      locale: const Locale('zh', 'CN'),
      supportedLocales: const [Locale('zh', 'CN'), Locale('en')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF176B62)),
        scaffoldBackgroundColor: const Color(0xFFF6F8F7),
        inputDecorationTheme: const InputDecorationTheme(
          border: OutlineInputBorder(),
        ),
      ),
      builder: (context, child) => Listener(
        onPointerDown: (_) => c.activity(),
        onPointerSignal: (_) => c.activity(),
        child: Focus(
          onKeyEvent: (_, _) {
            c.activity();
            return KeyEventResult.ignored;
          },
          child: Stack(
            children: [
              child!,
              if (c.obscured)
                const Positioned.fill(
                  child: ColoredBox(
                    color: Color(0xFFF6F8F7),
                    child: Center(child: Icon(Icons.lock_outline, size: 56)),
                  ),
                ),
            ],
          ),
        ),
      ),
      home: c.store.unlocked
          ? VaultHome(
              controller: c,
              onPickAttachment: _pickAttachment,
              onRestore: _pickBackup,
            )
          : _pendingBackup != null
          ? RestorePage(
              controller: c,
              file: _pendingBackup!,
              onCancel: () => setState(() => _pendingBackup = null),
              afterRestore: () async {
                _pendingBackup = null;
                await _afterUnlock();
              },
            )
          : UnlockPage(
              controller: c,
              afterUnlock: _afterUnlock,
              onRestore: _pickBackup,
            ),
    ),
  );
}

class StatusMessages extends StatelessWidget {
  const StatusMessages({super.key, required this.controller});
  final AppController controller;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (controller.busy) const LinearProgressIndicator(),
      if (controller.error != null || controller.notice != null)
        Padding(
          padding: const EdgeInsets.all(12),
          child: Text(
            controller.error ?? controller.notice!,
            style: TextStyle(
              color: controller.error != null
                  ? Theme.of(context).colorScheme.error
                  : Theme.of(context).colorScheme.primary,
            ),
          ),
        ),
    ],
  );
}

class UnlockPage extends StatefulWidget {
  const UnlockPage({
    super.key,
    required this.controller,
    required this.afterUnlock,
    required this.onRestore,
  });
  final AppController controller;
  final Future<void> Function() afterUnlock;
  final Future<void> Function() onRestore;
  @override
  State<UnlockPage> createState() => _UnlockPageState();
}

class _UnlockPageState extends State<UnlockPage> {
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  final _recovery = TextEditingController();
  String? _newRecovery;
  bool _savedRecovery = false;
  bool _reset = false;
  AppController get c => widget.controller;

  @override
  void dispose() {
    _password.dispose();
    _confirm.dispose();
    _recovery.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final password = _password.text;
    final confirmation = _confirm.text;
    final recovery = _recovery.text;
    final creating = !c.store.exists;
    if (creating && _newRecovery == null) {
      await c.run(() async {
        VaultCrypto.checkPassword(password);
        if (password != confirmation) throw const VaultException('两次输入的密码不一致。');
        setState(() => _newRecovery = VaultCrypto.newRecoveryKey());
      });
      return;
    }
    await c.run(() async {
      if (creating || _reset) {
        if (password != confirmation) throw const VaultException('两次输入的密码不一致。');
      }
      if (creating) {
        if (!_savedRecovery ||
            recovery.replaceAll(RegExp(r'[\s-]'), '').toUpperCase() !=
                _newRecovery!.replaceAll('-', '')) {
          throw const VaultException('请抄写并重新输入完整恢复密钥，确认已离线保存。');
        }
        await c.store.create(password, _newRecovery!);
      } else if (_reset) {
        await c.store.resetPassword(recovery, password);
      } else {
        await c.store.unlock(password);
      }
      await widget.afterUnlock();
    });
  }

  @override
  Widget build(BuildContext context) {
    final creating = !c.store.exists;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: ListView(
              shrinkWrap: true,
              padding: const EdgeInsets.all(28),
              children: [
                const Icon(
                  Icons.shield_outlined,
                  size: 64,
                  color: Color(0xFF176B62),
                ),
                const SizedBox(height: 16),
                Text(
                  '离线资料柜',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
                const SizedBox(height: 8),
                const Text('不注册 · 不上传 · 仅在本机加密保存', textAlign: TextAlign.center),
                const SizedBox(height: 28),
                Text(
                  creating
                      ? '创建本地资料库'
                      : _reset
                      ? '使用恢复密钥重设密码'
                      : '解锁本地资料库',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _password,
                  obscureText: true,
                  autocorrect: false,
                  enableSuggestions: false,
                  enableIMEPersonalizedLearning: false,
                  readOnly: _newRecovery != null,
                  decoration: InputDecoration(
                    labelText: creating || _reset ? '设置密码（至少 12 个字符）' : '资料库密码',
                  ),
                  onSubmitted: (_) {
                    if (!c.busy) _submit();
                  },
                ),
                if (creating || _reset) ...[
                  const SizedBox(height: 12),
                  TextField(
                    controller: _confirm,
                    obscureText: true,
                    autocorrect: false,
                    enableSuggestions: false,
                    enableIMEPersonalizedLearning: false,
                    readOnly: _newRecovery != null,
                    decoration: const InputDecoration(labelText: '再次输入密码'),
                  ),
                ],
                if (_newRecovery != null) ...[
                  const SizedBox(height: 16),
                  const Text(
                    '请把以下恢复密钥抄写在纸上或保存在独立的安全位置。'
                    '它可以解锁资料库。密码与恢复密钥都丢失时无法找回资料。',
                  ),
                  const SizedBox(height: 12),
                  Text(
                    _newRecovery!,
                    style: const TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 18,
                    ),
                  ),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('我已离线保存恢复密钥'),
                    value: _savedRecovery,
                    onChanged: c.busy
                        ? null
                        : (value) => setState(() => _savedRecovery = value!),
                  ),
                ],
                if (_newRecovery != null || _reset) ...[
                  const SizedBox(height: 12),
                  TextField(
                    controller: _recovery,
                    obscureText: true,
                    autocorrect: false,
                    enableSuggestions: false,
                    enableIMEPersonalizedLearning: false,
                    decoration: const InputDecoration(labelText: '输入完整恢复密钥'),
                  ),
                ],
                const SizedBox(height: 20),
                StatusMessages(controller: c),
                FilledButton(
                  onPressed: c.busy ? null : _submit,
                  child: Text(
                    creating
                        ? _newRecovery == null
                              ? '下一步：保存恢复密钥'
                              : '创建资料库'
                        : _reset
                        ? '重设密码并解锁'
                        : '解锁',
                  ),
                ),
                if (!creating)
                  TextButton(
                    onPressed: c.busy
                        ? null
                        : () => setState(() {
                            _reset = !_reset;
                            _password.clear();
                            _confirm.clear();
                            _recovery.clear();
                          }),
                    child: Text(_reset ? '返回密码解锁' : '忘记密码？使用恢复密钥'),
                  ),
                TextButton(
                  onPressed: c.busy ? null : widget.onRestore,
                  child: const Text('从加密备份恢复'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

typedef PickAttachment = Future<void> Function(String entryId, String role);

class VaultHome extends StatefulWidget {
  const VaultHome({
    super.key,
    required this.controller,
    required this.onPickAttachment,
    required this.onRestore,
  });
  final AppController controller;
  final PickAttachment onPickAttachment;
  final Future<void> Function() onRestore;
  @override
  State<VaultHome> createState() => _VaultHomeState();
}

class _VaultHomeState extends State<VaultHome> {
  int _tab = 0;
  String _query = '';
  String? _category;
  EntryKind? _kind;
  AppController get c => widget.controller;

  void _edit([VaultEntry? entry]) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => EntryEditor(controller: c, entry: entry),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 840;
    final entries = c.store.entries
        .where(
          (e) =>
              e.matches(_query) &&
              (_kind == null || e.kind == _kind) &&
              (_category == null || e.category == _category) &&
              (_tab != 1 || e.expiryKind == ExpiryKind.dated),
        )
        .toList();
    entries.sort(
      (a, b) => _tab == 1
          ? a.expiry!.compareTo(b.expiry!)
          : b.updatedAt.compareTo(a.updatedAt),
    );
    final categories =
        c.store.entries
            .map((e) => e.category)
            .where((v) => v.isNotEmpty)
            .toSet()
            .toList()
          ..sort();
    final content = _tab == 2
        ? SettingsPage(controller: c, onRestore: widget.onRestore)
        : Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 8),
                child: TextField(
                  onChanged: (value) => setState(() => _query = value),
                  autocorrect: false,
                  enableSuggestions: false,
                  enableIMEPersonalizedLearning: false,
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.search),
                    hintText: '搜索名称、持有人、分类、标签或备注',
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: Wrap(
                  spacing: 8,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    ChoiceChip(
                      label: const Text('全部'),
                      selected: _kind == null,
                      onSelected: (_) => setState(() => _kind = null),
                    ),
                    ChoiceChip(
                      label: const Text('证件'),
                      selected: _kind == EntryKind.certificate,
                      onSelected: (_) =>
                          setState(() => _kind = EntryKind.certificate),
                    ),
                    ChoiceChip(
                      label: const Text('文件'),
                      selected: _kind == EntryKind.document,
                      onSelected: (_) =>
                          setState(() => _kind = EntryKind.document),
                    ),
                    PopupMenuButton<String>(
                      tooltip: '按分类筛选',
                      onSelected: (value) => setState(
                        () => _category = value.isEmpty ? null : value,
                      ),
                      itemBuilder: (_) => [
                        const PopupMenuItem(value: '', child: Text('全部分类')),
                        ...categories.map(
                          (v) => PopupMenuItem(value: v, child: Text(v)),
                        ),
                      ],
                      child: Chip(label: Text(_category ?? '全部分类 ▾')),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: entries.isEmpty
                    ? Center(
                        child: Text(
                          _tab == 1
                              ? '暂无到期事项\n设置有效期后将在这里显示'
                              : '资料只属于你\n点击“新增资料”开始整理',
                          textAlign: TextAlign.center,
                        ),
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.fromLTRB(16, 0, 16, 100),
                        itemCount: entries.length,
                        itemBuilder: (context, i) {
                          final e = entries[i];
                          final days = e.expiry == null
                              ? null
                              : daysUntil(e.expiry!, DateTime.now());
                          return Card(
                            child: ListTile(
                              contentPadding: const EdgeInsets.all(14),
                              leading: CircleAvatar(
                                child: Icon(
                                  e.kind == EntryKind.certificate
                                      ? Icons.badge_outlined
                                      : Icons.description_outlined,
                                ),
                              ),
                              title: Text(e.name),
                              subtitle: Text(
                                [
                                  if (e.holder.isNotEmpty) e.holder,
                                  if (e.category.isNotEmpty) e.category,
                                  e.expiryLabel,
                                ].join(' · '),
                              ),
                              trailing: days == null
                                  ? const Icon(Icons.chevron_right)
                                  : Text(
                                      days < 0
                                          ? '已过期'
                                          : days == 0
                                          ? '今日到期'
                                          : '$days 天',
                                      style: TextStyle(
                                        color: days <= 7
                                            ? Theme.of(context)
                                                  .colorScheme
                                                  .error
                                            : null,
                                      ),
                                    ),
                              onTap: () => Navigator.of(context).push(
                                MaterialPageRoute<void>(
                                  builder: (_) => EntryDetails(
                                    controller: c,
                                    id: e.id,
                                    onPickAttachment: widget.onPickAttachment,
                                  ),
                                ),
                              ),
                            ),
                          );
                        },
                      ),
              ),
            ],
          );
    return Scaffold(
      appBar: AppBar(
        title: Text(['资料柜', '到期事项', '设置'][_tab]),
        actions: [
          IconButton(
            tooltip: '立即锁定',
            onPressed: c.lock,
            icon: const Icon(Icons.lock_outline),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Column(
        children: [
          StatusMessages(controller: c),
          Expanded(
            child: Row(
              children: [
                if (wide)
                  NavigationRail(
                    selectedIndex: _tab,
                    labelType: NavigationRailLabelType.all,
                    onDestinationSelected: (value) =>
                        setState(() => _tab = value),
                    destinations: const [
                      NavigationRailDestination(
                        icon: Icon(Icons.folder_outlined),
                        label: Text('资料柜'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.event_outlined),
                        label: Text('到期事项'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.settings_outlined),
                        label: Text('设置'),
                      ),
                    ],
                  ),
                Expanded(child: content),
              ],
            ),
          ),
        ],
      ),
      floatingActionButton: _tab == 2
          ? null
          : FloatingActionButton.extended(
              onPressed: c.busy ? null : () => _edit(),
              icon: const Icon(Icons.add),
              label: const Text('新增资料'),
            ),
      bottomNavigationBar: wide
          ? null
          : NavigationBar(
              selectedIndex: _tab,
              onDestinationSelected: (value) => setState(() => _tab = value),
              destinations: const [
                NavigationDestination(
                  icon: Icon(Icons.folder_outlined),
                  label: '资料柜',
                ),
                NavigationDestination(
                  icon: Icon(Icons.event_outlined),
                  label: '到期事项',
                ),
                NavigationDestination(
                  icon: Icon(Icons.settings_outlined),
                  label: '设置',
                ),
              ],
            ),
    );
  }
}
