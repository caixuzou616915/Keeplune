import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:offline_vault/core/crypto.dart';
import 'package:offline_vault/core/models.dart';
import 'package:offline_vault/core/vault_store.dart';

void main() {
  const password = 'correct horse battery staple';
  const nextPassword = 'a different long vault password';
  late Directory directory;
  late VaultStore store;
  late String recovery;
  final png = Uint8List.fromList([137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 0]);

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('offline_vault_test_');
    store = VaultStore(directory);
    recovery = VaultCrypto.newRecoveryKey();
    await store.initialize();
    await store.create(password, recovery);
  });
  tearDown(() async {
    store.lock();
    await directory.delete(recursive: true);
  });

  VaultEntry entry({List<VaultAttachment> attachments = const []}) =>
      VaultEntry(
        id: VaultCrypto.id(),
        kind: EntryKind.certificate,
        name: 'SECRET_CERTIFICATE_NAME',
        holder: 'SECRET_HOLDER',
        number: 'SECRET_NUMBER_12345',
        notes: 'SECRET_NOTES',
        attachments: attachments,
        expiryKind: ExpiryKind.dated,
        expiry: DateTime(2030, 10, 29),
      );

  test('persists encrypted metadata, locks and reloads', () async {
    final e = entry();
    await store.saveEntry(e, []);
    await for (final entity in directory.list()) {
      if (entity is File) {
        final content = await entity.readAsString();
        for (final secret in [
          e.name,
          e.holder,
          e.number,
          e.notes,
          password,
          recovery,
        ]) {
          expect(content, isNot(contains(secret)));
        }
      }
    }
    store.lock();
    expect(store.entries, isEmpty);
    final reopened = VaultStore(directory);
    await reopened.initialize();
    expect(reopened.unlocked, isFalse);
    await expectLater(
      reopened.unlock('wrong password'),
      throwsA(isA<VaultException>()),
    );
    await reopened.unlock(password);
    expect(reopened.entries.single.number, e.number);
    reopened.lock();
  });

  test(
    'recovery resets password and old backups retain original credential',
    () async {
      await store.saveEntry(entry(), []);
      final backup = await store.exportBackup();
      store.lock();
      await store.resetPassword(recovery, nextPassword);
      expect(store.unlocked, isTrue);
      store.lock();
      await expectLater(store.unlock(password), throwsA(isA<VaultException>()));
      await store.unlock(nextPassword);
      final otherDir = await Directory.systemTemp.createTemp('vault_restore_');
      try {
        final other = VaultStore(otherDir);
        await other.initialize();
        await other.restoreBackup(backup, password);
        expect(other.entries.single.name, 'SECRET_CERTIFICATE_NAME');
        other.lock();
      } finally {
        await otherDir.delete(recursive: true);
      }
    },
  );

  test(
    'password change requires current password and preserves attachments',
    () async {
      await store.saveEntry(entry(), []);
      await expectLater(
        store.changePassword('incorrect', nextPassword),
        throwsA(isA<VaultException>()),
      );
      await store.changePassword(password, nextPassword);
      store.lock();
      await expectLater(store.unlock(password), throwsA(isA<VaultException>()));
      await store.unlock(nextPassword);
      expect(store.entries.length, 1);
      await store.resetPassword(recovery, password);
      expect(store.entries.length, 1);
    },
  );

  test('encrypts attachments and rejects modifications', () async {
    final a = VaultAttachment(
      id: VaultCrypto.id(),
      name: 'SECRET_ORIGINAL_FILENAME.png',
      role: 'front',
      type: 'png',
      size: png.length,
    );
    await store.saveEntry(entry(attachments: [a]), [PendingAttachment(a, png)]);
    expect(await store.readAttachment(a), png);
    final blob = await directory
        .list()
        .where((e) => e.path.endsWith('.blob'))
        .cast<File>()
        .single;
    expect(blob.path, isNot(contains(a.name)));
    final bytes = base64Decode(await blob.readAsString());
    bytes[13] ^= 1;
    await blob.writeAsString(base64Encode(bytes));
    await expectLater(store.readAttachment(a), throwsA(isA<VaultException>()));
    await expectLater(store.exportBackup(), throwsA(isA<VaultException>()));
  });

  test('valid backup repairs corrupted local ciphertext without overwriting live files first', () async {
    final a = VaultAttachment(
      id: VaultCrypto.id(),
      name: 'front.png',
      role: 'front',
      type: 'png',
      size: png.length,
    );
    await store.saveEntry(entry(attachments: [a]), [PendingAttachment(a, png)]);
    final backup = await store.exportBackup();
    final oldBlob = await directory
        .list()
        .where((e) => e.path.endsWith('.blob'))
        .cast<File>()
        .single;
    await oldBlob.writeAsString('corrupted');
    await store.restoreBackup(backup, password);
    expect(
      await store.readAttachment(store.entries.single.attachments.single),
      png,
    );
    expect(await oldBlob.exists(), isFalse);
    store.lock();
    final reopened = VaultStore(directory);
    await reopened.initialize();
    await reopened.unlock(password);
    expect(
      await reopened.readAttachment(reopened.entries.single.attachments.single),
      png,
    );
    reopened.lock();
  });

  test(
    'round trips backup with recovery key, validates before replacement',
    () async {
      final a = VaultAttachment(
        id: VaultCrypto.id(),
        name: 'front.png',
        role: 'front',
        type: 'png',
        size: png.length,
      );
      final e = entry(attachments: [a]);
      await store.saveEntry(e, [PendingAttachment(a, png)]);
      final backup = await store.exportBackup();
      await store.deleteEntry(e.id);
      expect(store.entries, isEmpty);
      await store.restoreBackup(backup, recovery, recovery: true);
      expect(
        await store.readAttachment(store.entries.single.attachments.single),
        png,
      );
      final damaged = jsonDecode(utf8.decode(backup)) as Map<String, dynamic>;
      (damaged['blobs'] as Map<String, dynamic>)[a.id] = base64Encode(
        List.filled(50, 0),
      );
      await expectLater(
        store.restoreBackup(
          Uint8List.fromList(utf8.encode(jsonEncode(damaged))),
          password,
        ),
        throwsA(isA<VaultException>()),
      );
      expect(store.entries.single.id, e.id);
      expect(await store.readAttachment(a), png);
    },
  );

  test(
    'rejects hostile headers, invalid recovery keys and missing blobs',
    () async {
      final backup = jsonDecode(
        utf8.decode(await store.exportBackup()),
      ) as Map<String, dynamic>;
      final snapshot = backup['snapshot'] as Map<String, dynamic>;
      snapshot['kdf'] = 'argon2id-999999999-999-999';
      await expectLater(
        store.restoreBackup(
          Uint8List.fromList(utf8.encode(jsonEncode(backup))),
          password,
        ),
        throwsA(isA<VaultException>()),
      );
      await expectLater(
        store.resetPassword('not a recovery key', nextPassword),
        throwsA(isA<VaultException>()),
      );
      final a = VaultAttachment(
        id: '../escape',
        name: 'front.png',
        role: 'front',
        type: 'png',
        size: png.length,
      );
      await expectLater(
        store.saveEntry(entry(attachments: [a]), []),
        throwsA(isA<VaultException>()),
      );
      final missing = VaultAttachment(
        id: VaultCrypto.id(),
        name: 'missing.png',
        role: 'front',
        type: 'png',
        size: png.length,
      );
      await expectLater(
        store.saveEntry(entry(attachments: [missing]), []),
        throwsA(isA<VaultException>()),
      );
      expect(store.entries, isEmpty);
    },
  );

  test('authenticates recovery wrapping header and metadata', () async {
    final backup = jsonDecode(
      utf8.decode(await store.exportBackup()),
    ) as Map<String, dynamic>;
    final snapshot = backup['snapshot'] as Map<String, dynamic>;
    final bytes = base64Decode(snapshot['recoveryWrap'] as String);
    bytes[0] ^= 1;
    snapshot['recoveryWrap'] = base64Encode(bytes);
    await expectLater(
      store.restoreBackup(
        Uint8List.fromList(utf8.encode(jsonEncode(backup))),
        password,
      ),
      throwsA(isA<VaultException>()),
    );
  });

  test('ignores incomplete commits and does not fall back on corrupted latest commit', () async {
    final e = entry();
    await store.saveEntry(e, []);
    await File(
      '${directory.path}${Platform.pathSeparator}commit-999999999999.json.pending',
    ).writeAsString('interrupted write');
    final reopened = VaultStore(directory);
    await reopened.initialize();
    await reopened.unlock(password);
    expect(reopened.entries.single.id, e.id);
    reopened.lock();
    final commit = await directory
        .list()
        .where((e) => e.path.endsWith('.json'))
        .cast<File>()
        .single;
    await commit.writeAsString('corrupted');
    final damaged = VaultStore(directory);
    await damaged.initialize();
    expect(damaged.exists, isTrue);
    expect(damaged.initializationError, isNotNull);
    await expectLater(damaged.unlock(password), throwsA(isA<VaultException>()));
    await expectLater(
      damaged.create(password, recovery),
      throwsA(isA<VaultException>()),
    );
  });

  test('locking cancels an in-flight unlock', () async {
    store.lock();
    final attempt = store.unlock(password);
    store.lock();
    await expectLater(attempt, throwsA(isA<VaultException>()));
    expect(store.unlocked, isFalse);
    expect(store.entries, isEmpty);
  });

  test(
    'backup recovery is available when the committed metadata is unreadable',
    () async {
      final e = entry();
      await store.saveEntry(e, []);
      final backup = await store.exportBackup();
      store.lock();
      final commit = await directory
          .list()
          .where((e) => e.path.endsWith('.json'))
          .cast<File>()
          .single;
      await commit.writeAsString('not a valid vault');
      final damaged = VaultStore(directory);
      await damaged.initialize();
      expect(damaged.initializationError, isNotNull);
      await expectLater(
        damaged.create(password, recovery),
        throwsA(isA<VaultException>()),
      );
      await damaged.restoreBackup(backup, recovery, recovery: true);
      expect(damaged.initializationError, isNull);
      expect(damaged.entries.single.id, e.id);
      damaged.lock();
    },
  );

  test('locked operations fail and destroying requires password', () async {
    await expectLater(
      store.destroy('incorrect'),
      throwsA(isA<VaultException>()),
    );
    expect(store.exists, isTrue);
    store.lock();
    await expectLater(store.exportBackup(), throwsA(isA<VaultException>()));
    await expectLater(
      store.saveEntry(entry(), []),
      throwsA(isA<VaultException>()),
    );
    await store.destroy(password);
    expect(store.exists, isFalse);
    expect(await directory.list().toList(), isEmpty);
  });

  test('validates media signatures and attachment byte limits', () {
    expect(
      () => VaultStore.validateMedia(Uint8List.fromList([1, 2, 3]), 'pdf'),
      throwsA(isA<VaultException>()),
    );
    expect(
      () => VaultStore.validateMedia([], 'png'),
      throwsA(isA<VaultException>()),
    );
    expect(
      () => VaultStore.validateMedia(png, 'pdf'),
      throwsA(isA<VaultException>()),
    );
    expect(
      () => VaultStore.validateMedia(utf8.encode('%PDF-1.7\n'), 'pdf'),
      returnsNormally,
    );
  });

  test('attachment byte and total capacity bounds are enforced', () async {
    final tooLarge = Uint8List(VaultStore.maxAttachmentBytes + 1);
    expect(
      () => VaultStore.validateMedia(tooLarge, 'png'),
      throwsA(isA<VaultException>()),
    );
    final metadataOnly = List.generate(
      6,
      (i) => VaultAttachment(
        id: VaultCrypto.id(),
        name: '$i.pdf',
        role: 'file',
        type: 'pdf',
        size: VaultStore.maxAttachmentBytes,
      ),
    );
    await expectLater(
      store.saveEntry(entry(attachments: metadataOnly), []),
      throwsA(isA<VaultException>()),
    );
    expect(store.entries, isEmpty);
  });

  test(
    'AEAD uses fresh nonces and rejects a different object context',
    () async {
      final key = VaultCrypto.randomBytes(32);
      final first = await VaultCrypto.seal(png, key, 'first');
      final second = await VaultCrypto.seal(png, key, 'first');
      expect(first, isNot(second));
      expect(await VaultCrypto.open(first, key, 'first'), png);
      await expectLater(
        VaultCrypto.open(first, key, 'second'),
        throwsA(isA<VaultException>()),
      );
    },
  );
}
