import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../app_controller.dart';
import '../core/crypto.dart';
import '../core/models.dart';
import '../services/file_access.dart';
import 'vault_app.dart';

class SettingsPage extends StatelessWidget {
  const SettingsPage({
    super.key,
    required this.controller,
    required this.onRestore,
  });
  final AppController controller;
  final Future<void> Function() onRestore;

  Future<String?> _passwordDialog(BuildContext context, String title) async {
    final password = TextEditingController();
    try {
      return await showDialog<String>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(title),
          content: TextField(
            controller: password,
            obscureText: true,
            autocorrect: false,
            enableSuggestions: false,
            enableIMEPersonalizedLearning: false,
            decoration: const InputDecoration(labelText: '当前资料库密码'),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, password.text),
              child: const Text('确认'),
            ),
          ],
        ),
      );
    } finally {
      // Dialog transitions can retain TextFields until the next frame.
      WidgetsBinding.instance.addPostFrameCallback((_) => password.dispose());
    }
  }

  Future<void> _changePassword(BuildContext context) async {
    final current = await _passwordDialog(context, '验证当前密码');
    if (current == null || !context.mounted) return;
    final next = TextEditingController();
    final confirmation = TextEditingController();
    try {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('修改资料库密码'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('旧备份仍使用导出时的密码；恢复密钥不变。'),
              const SizedBox(height: 12),
              TextField(
                controller: next,
                obscureText: true,
                autocorrect: false,
                enableSuggestions: false,
                enableIMEPersonalizedLearning: false,
                decoration: const InputDecoration(labelText: '新密码（至少 12 个字符）'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: confirmation,
                obscureText: true,
                autocorrect: false,
                enableSuggestions: false,
                enableIMEPersonalizedLearning: false,
                decoration: const InputDecoration(labelText: '再次输入新密码'),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('修改'),
            ),
          ],
        ),
      );
      if (confirmed != true) return;
      final password = next.text;
      final repeated = confirmation.text;
      await controller.run(() async {
        if (password != repeated) throw const VaultException('两次输入的新密码不一致。');
        await controller.store.changePassword(current, password);
      }, success: '密码已修改。旧备份仍需使用原密码。');
    } finally {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        next.dispose();
        confirmation.dispose();
      });
    }
  }

  Future<void> _export(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('导出加密备份'),
        content: const Text(
          '备份可用当前密码或恢复密钥解锁。请保留对应凭证。\n\n'
          '请优先选择本地文件夹；系统文件选择器可能提供云盘，选择云盘将由系统上传。\n\n'
          '导出前会校验所有附件，选择保存位置前会锁定资料库。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('继续'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await controller.run(() async {
      final bytes = await controller.store.exportBackup();
      controller.lock();
      final saved = await FileAccess.saveBackup(bytes);
      controller.notice = saved ? '加密备份已导出。请妥善保存密码与恢复密钥。' : '已取消导出。';
    });
  }

  @override
  Widget build(BuildContext context) {
    final c = controller;
    final settings = c.store.settings;
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text('安全保护', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          key: ValueKey(settings.lockMinutes),
          initialValue: settings.lockMinutes,
          decoration: const InputDecoration(labelText: '闲置自动锁定'),
          items: [1, 2, 5, 10]
              .map((v) => DropdownMenuItem(value: v, child: Text('$v 分钟')))
              .toList(),
          onChanged: c.busy
              ? null
              : (value) => c.run(() async {
                  await c.store.updateSettings(
                    VaultSettings(
                      lockMinutes: value!,
                      notifications: settings.notifications,
                    ),
                  );
                }),
        ),
        ListTile(
          leading: const Icon(Icons.password),
          title: const Text('修改资料库密码'),
          onTap: c.busy ? null : () => _changePassword(context),
        ),
        const Text('进入后台、最小化或锁定会话时锁定。切换窗口会遮挡画面。文件选择前会先锁定。'),
        const Divider(height: 32),
        Text('本地提醒', style: Theme.of(context).textTheme.titleLarge),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('允许到期提醒'),
          subtitle: const Text('提前 30 天、7 天和当天上午 9 点提醒，锁屏不显示资料详情。'),
          value: settings.notifications,
          onChanged: c.busy
              ? null
              : (enabled) => c.run(() async {
                  if (enabled && !await c.reminders.requestPermission()) {
                    throw const VaultException('系统通知权限未授予，请在系统设置中允许后重试。');
                  }
                  if (!c.store.unlocked) {
                    throw const VaultException('请重新解锁后设置提醒。');
                  }
                  await c.store.updateSettings(
                    VaultSettings(
                      lockMinutes: settings.lockMinutes,
                      notifications: enabled,
                    ),
                  );
                  await c.refreshReminders();
                }),
        ),
        const Text(
          '每次解锁更新最近 60 个提醒日期，同一天合并提醒。长期不打开应用、系统省电或时区变化可能影响提醒，请定期查看到期事项。',
        ),
        const Divider(height: 32),
        Text('备份与迁移', style: Theme.of(context).textTheme.titleLarge),
        ListTile(
          leading: const Icon(Icons.save_alt),
          title: const Text('导出加密备份'),
          subtitle: const Text('最大 256 MB；不自动同步'),
          onTap: c.busy ? null : () => _export(context),
        ),
        ListTile(
          leading: const Icon(Icons.restore),
          title: const Text('从加密备份恢复'),
          subtitle: const Text('整体替换，不合并；恢复前会要求确认'),
          onTap: c.busy ? null : onRestore,
        ),
        const Divider(height: 32),
        Text('关于资料柜', style: Theme.of(context).textTheme.titleLarge),
        const ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text('离线资料柜 0.1.0'),
          subtitle: Text(
            '无账号、无服务器、无统计埋点。\n'
            '资料与附件仅在本机加密保存；搜索不包含图片文字或 PDF 正文。\n'
            '原始导入文件不会被删除，请自行管理原文件。',
          ),
        ),
        OutlinedButton.icon(
          icon: const Icon(Icons.delete_forever_outlined),
          label: const Text('删除本机资料库'),
          onPressed: c.busy
              ? null
              : () async {
                  final password = await _passwordDialog(
                    context,
                    '永久删除本机资料库？请输入密码确认',
                  );
                  if (password == null) return;
                  await c.run(() async {
                    await c.store.verifyPassword(password);
                    // Cancel reminders first; a platform error must not report a full deletion.
                    await c.reminders.cancelAll();
                    await c.store.destroy(password);
                  }, success: '本机资料库已删除。已导出的备份不会被删除。');
                },
        ),
      ],
    );
  }
}

class RestorePage extends StatefulWidget {
  const RestorePage({
    super.key,
    required this.controller,
    required this.file,
    required this.onCancel,
    required this.afterRestore,
  });
  final AppController controller;
  final XFile file;
  final VoidCallback onCancel;
  final Future<void> Function() afterRestore;
  @override
  State<RestorePage> createState() => _RestorePageState();
}

class _RestorePageState extends State<RestorePage> {
  final _credential = TextEditingController();
  bool _recovery = false;
  bool _replace = false;
  @override
  void dispose() {
    _credential.dispose();
    super.dispose();
  }

  Future<void> _restore() async {
    final credential = _credential.text;
    final recovery = _recovery;
    await widget.controller.run(() async {
      if (widget.controller.store.exists && !_replace) {
        throw const VaultException('请确认整体替换现有资料库。建议先取消并导出原资料库备份。');
      }
      final bytes = await FileAccess.readBackup(widget.file);
      await widget.controller.store.restoreBackup(
        bytes,
        credential,
        recovery: recovery,
      );
      await widget.afterRestore();
    }, success: '加密备份已校验并恢复。请检查资料并定期备份。');
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('恢复加密备份')),
    body: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560),
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.all(24),
          children: [
            Text(
              widget.file.name,
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 12),
            const Text('使用导出该备份时的密码或恢复密钥。恢复会先校验所有附件；不支持合并资料库。'),
            const SizedBox(height: 16),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('使用恢复密钥'),
              value: _recovery,
              onChanged: widget.controller.busy
                  ? null
                  : (v) => setState(() {
                      _recovery = v;
                      _credential.clear();
                    }),
            ),
            TextField(
              controller: _credential,
              obscureText: true,
              autocorrect: false,
              enableSuggestions: false,
              enableIMEPersonalizedLearning: false,
              decoration: InputDecoration(
                labelText: _recovery ? '恢复密钥' : '备份对应的密码',
              ),
            ),
            if (widget.controller.store.exists)
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('我知道这会整体替换本机资料库，且已另行保存所需备份'),
                value: _replace,
                onChanged: widget.controller.busy
                    ? null
                    : (v) => setState(() => _replace = v!),
              ),
            StatusMessages(controller: widget.controller),
            FilledButton(
              onPressed: widget.controller.busy ? null : _restore,
              child: const Text('校验并恢复'),
            ),
            TextButton(
              onPressed: widget.controller.busy ? null : widget.onCancel,
              child: const Text('取消'),
            ),
          ],
        ),
      ),
    ),
  );
}
