import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:offline_vault/core/crypto.dart';
import 'package:offline_vault/services/file_access.dart';
import 'package:offline_vault/services/offline_policy.dart';

void main() {
  test(
    'runtime HTTP clients are rejected without attempting network access',
    () {
      HttpOverrides.runWithHttpOverrides(
        () => expect(() => HttpClient(), throwsA(isA<HttpException>())),
        OfflineHttpOverrides(),
      );
    },
  );

  test('file reads enforce the precise size limit', () async {
    final directory = await Directory.systemTemp.createTemp(
      'vault_file_limit_',
    );
    try {
      final file = File('${directory.path}${Platform.pathSeparator}source.png');
      await file.writeAsBytes(List.generate(16, (i) => i));
      expect(await FileAccess.readLimited(XFile(file.path), 16), hasLength(16));
      await expectLater(
        FileAccess.readLimited(XFile(file.path), 15),
        throwsA(isA<VaultException>()),
      );
    } finally {
      await directory.delete(recursive: true);
    }
  });

  test(
    'file type handling is case insensitive and refuses arbitrary formats',
    () {
      expect(FileAccess.mediaType('FILE.JPEG'), 'jpg');
      expect(FileAccess.mediaType('FILE.PDF'), 'pdf');
      expect(
        () => FileAccess.mediaType('file.exe'),
        throwsA(isA<VaultException>()),
      );
      expect(
        () => FileAccess.mediaType('file'),
        throwsA(isA<VaultException>()),
      );
    },
  );
}
