import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'core/crypto.dart';
import 'core/vault_store.dart';
import 'services/reminders.dart';

class AppController extends ChangeNotifier with WidgetsBindingObserver {
  AppController(this.store, this.reminders, {required this.pdfPreviewBuilder}) {
    error = store.initializationError;
    WidgetsBinding.instance.addObserver(this);
    if (Platform.isWindows) {
      const MethodChannel('app.offlinevault/security')
          .setMethodCallHandler((call) async {
            if (call.method == 'sessionLocked') {
              lock();
            } else if (call.method == 'protectionWarning') {
              notice = '系统无法启用完整的窗口捕获保护或会话锁定监听，请勿在共享屏幕时打开敏感资料。';
              notifyListeners();
            }
          });
    }
  }
  final VaultStore store;
  final ReminderService reminders;
  final Widget Function(Uint8List bytes, String id) pdfPreviewBuilder;
  bool busy = false;
  bool obscured = false;
  String? error;
  String? notice;
  int viewGeneration = 0;
  Timer? _timer;
  DateTime? _lastActivity;

  void activity() {
    if (!store.unlocked) return;
    final now = DateTime.now();
    if (_lastActivity != null &&
        now.difference(_lastActivity!) < const Duration(seconds: 1)) {
      return;
    }
    _lastActivity = now;
    _timer?.cancel();
    _timer = Timer(Duration(minutes: store.settings.lockMinutes), lock);
  }

  void lock() {
    store.lock();
    viewGeneration++;
    _timer?.cancel();
    _lastActivity = null;
    PaintingBinding.instance.imageCache.clear();
    PaintingBinding.instance.imageCache.clearLiveImages();
    error = null;
    notice = null;
    notifyListeners();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    obscured = state != AppLifecycleState.resumed;
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden ||
        state == AppLifecycleState.detached) {
      lock();
    } else {
      if (state == AppLifecycleState.resumed) activity();
      notifyListeners();
    }
  }

  String _message(Object failure) => switch (failure) {
    VaultException() => failure.message,
    FileSystemException() =>
      '本地文件读写失败，请检查存储空间和文件权限。原始错误：${failure.osError?.errorCode ?? "未知"}',
    PlatformException() => '系统操作失败：${failure.message ?? failure.code}',
    _ => '操作失败（${failure.runtimeType}）。请保留当前资料库并重试；持续失败时不要删除原文件。',
  };

  Future<bool> run(Future<void> Function() action, {String? success}) async {
    if (busy) return false;
    busy = true;
    error = null;
    notice = null;
    notifyListeners();
    try {
      await action();
      if (success != null && notice == null) notice = success;
      activity();
      return true;
    } catch (failure) {
      // Do not log exceptions or stack traces containing user paths or document data.
      error = _message(failure);
      return false;
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<void> refreshReminders() async {
    if (!store.unlocked) return;
    final dates = reminderDates(store.entries, DateTime.now());
    final enabled = store.settings.notifications;
    try {
      await reminders.schedule(dates, enabled);
    } catch (failure) {
      notice = '资料已保存在本机，但提醒排程失败：${_message(failure)}';
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    store.lock();
    super.dispose();
  }
}
