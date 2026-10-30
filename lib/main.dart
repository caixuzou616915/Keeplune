import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'app_controller.dart';
import 'core/vault_store.dart';
import 'core/crypto.dart';
import 'services/file_access.dart';
import 'services/reminders.dart';
import 'services/pdf_preview.dart';
import 'services/offline_policy.dart';
import 'ui/vault_app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  HttpOverrides.global = OfflineHttpOverrides();
  try {
    final Directory support;
    if (Platform.isWindows) {
      final local = Platform.environment['LOCALAPPDATA'];
      if (local == null || local.isEmpty) {
        throw StateError('LOCALAPPDATA unavailable');
      }
      support = Directory(p.join(local, 'OfflineVault'));
    } else {
      support = await getApplicationSupportDirectory();
    }
    final directory = Directory(p.join(support.path, 'vault'));
    await directory.create(recursive: true);
    await FileAccess.protectDirectory(directory.path);
    final store = VaultStore(directory);
    await store.initialize();
    runApp(
      VaultApp(
        controller: AppController(
          store,
          ReminderService(),
          pdfPreviewBuilder: buildPdfPreview,
        ),
      ),
    );
  } catch (failure) {
    runApp(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Text(
                '${failure is VaultException ? failure.message : "资料库无法初始化（${failure.runtimeType}）。"}\n'
                '请检查存储权限与空间。请勿删除原资料库；修复环境后重新启动。',
                textAlign: TextAlign.center,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
