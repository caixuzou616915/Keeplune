import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:offline_vault/app_controller.dart';
import 'package:offline_vault/core/crypto.dart';
import 'package:offline_vault/core/models.dart';
import 'package:offline_vault/core/vault_store.dart';
import 'package:offline_vault/services/reminders.dart';
import 'package:offline_vault/ui/vault_app.dart';

void main() {
  late Directory directory;
  late VaultStore store;
  late AppController controller;
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('vault_ui_test_');
    store = VaultStore(directory);
    await store.initialize();
  });
  tearDown(() async {
    controller.dispose();
    await directory.delete(recursive: true);
  });

  testWidgets('first launch has no account UI and validates passwords', (
    tester,
  ) async {
    controller = AppController(
      store,
      ReminderService(),
      pdfPreviewBuilder: (_, _) => const SizedBox(),
    );
    await tester.pumpWidget(VaultApp(controller: controller));
    expect(find.text('创建本地资料库'), findsOneWidget);
    expect(find.text('不注册 · 不上传 · 仅在本机加密保存'), findsOneWidget);
    await tester.tap(find.text('下一步：保存恢复密钥'));
    await tester.pumpAndSettle();
    expect(find.textContaining('密码长度需为'), findsOneWidget);
    expect(store.exists, isFalse);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('lock disposes detail routes and hides unmasked numbers', (
    tester,
  ) async {
    await tester.runAsync(
      () => store.create(
        'a sufficiently long password',
        VaultCrypto.newRecoveryKey(),
      ),
    );
    final entry = VaultEntry(
      id: VaultCrypto.id(),
      kind: EntryKind.certificate,
      name: '测试证件',
      number: 'PRIVATE_NUMBER',
      holder: '测试持有人',
    );
    await tester.runAsync(() => store.saveEntry(entry, []));
    controller = AppController(
      store,
      ReminderService(),
      pdfPreviewBuilder: (_, _) => const SizedBox(),
    );
    await tester.pumpWidget(VaultApp(controller: controller));
    await tester.tap(find.text('测试证件'));
    await tester.pumpAndSettle();
    expect(find.text('PRIVATE_NUMBER'), findsNothing);
    await tester.tap(find.byTooltip('显示 15 秒'));
    await tester.pump();
    expect(find.text('PRIVATE_NUMBER'), findsOneWidget);
    controller.didChangeAppLifecycleState(AppLifecycleState.paused);
    controller.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(find.text('PRIVATE_NUMBER'), findsNothing);
    expect(find.text('解锁本地资料库'), findsOneWidget);
    expect(store.unlocked, isFalse);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('idle timer locks an unlocked vault', (tester) async {
    await tester.runAsync(
      () => store.create(
        'a sufficiently long password',
        VaultCrypto.newRecoveryKey(),
      ),
    );
    controller = AppController(
      store,
      ReminderService(),
      pdfPreviewBuilder: (_, _) => const SizedBox(),
    );
    await tester.pumpWidget(VaultApp(controller: controller));
    controller.activity();
    await tester.pump(const Duration(minutes: 2, seconds: 1));
    await tester.pumpAndSettle();
    expect(store.unlocked, isFalse);
    expect(find.text('解锁本地资料库'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
}
