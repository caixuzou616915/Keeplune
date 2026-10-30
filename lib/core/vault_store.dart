import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as p;

import 'crypto.dart';
import 'models.dart';

class PendingAttachment {
  const PendingAttachment(this.metadata, this.bytes);
  final VaultAttachment metadata;
  final Uint8List bytes;
}

class _Opened {
  const _Opened(this.key, this.entries, this.settings);
  final List<int> key;
  final List<VaultEntry> entries;
  final VaultSettings settings;
}

class VaultStore {
  VaultStore(this.directory);
  final Directory directory;
  static const maxAttachmentBytes = 32 * 1024 * 1024;
  static const maxBackupBytes = 256 * 1024 * 1024;
  static const maxMetadataBytes = 8 * 1024 * 1024;
  Map<String, dynamic>? _snapshot;
  List<int>? _key;
  List<VaultEntry> _entries = [];
  VaultSettings _settings = const VaultSettings();
  int _epoch = 0;
  int _revision = 0;
  bool _writing = false;
  bool _damaged = false;
  String? initializationError;

  bool get exists => _snapshot != null || _damaged;
  bool get unlocked => _key != null;
  int get epoch => _epoch;
  List<VaultEntry> get entries => List.unmodifiable(_entries);
  VaultSettings get settings => _settings;

  Future<void> initialize() async {
    await directory.create(recursive: true);
    final files = await directory
        .list()
        .where(
          (f) =>
              f is File &&
              RegExp(r'^commit-\d{12}\.json$').hasMatch(p.basename(f.path)),
        )
        .cast<File>()
        .toList();
    files.sort((a, b) => a.path.compareTo(b.path));
    if (files.isEmpty) return;
    final latest = files.last;
    _revision = int.parse(p.basename(latest.path).substring(7, 19));
    try {
      if (await latest.length() > maxMetadataBytes * 2) {
        throw const VaultException('资料库文件超出安全大小限制。');
      }
      _snapshot = _decode(await latest.readAsBytes());
      _checkHeader(_snapshot!);
    } on VaultException catch (failure) {
      _snapshot = null;
      _damaged = true;
      initializationError = '${failure.message} 请保留原文件并从加密备份恢复。';
    }
  }

  void lock() {
    _epoch++;
    _key?.fillRange(0, _key!.length, 0);
    _key = null;
    _entries = [];
    _settings = const VaultSettings();
  }

  void _checkSession(int token) {
    if (token != _epoch) {
      throw const VaultException('资料库已锁定，操作已取消。');
    }
  }

  Map<String, dynamic> _requireSnapshot() {
    if (_snapshot == null) {
      throw const VaultException('资料库缺失或损坏，请保留原文件并从加密备份恢复。');
    }
    return _snapshot!;
  }

  Future<T> _write<T>(Future<T> Function() action) async {
    if (_writing) throw const VaultException('另一个写入操作正在进行，请稍后重试。');
    _writing = true;
    try {
      return await action();
    } finally {
      _writing = false;
    }
  }

  static Map<String, dynamic> _decode(List<int> bytes) {
    try {
      return jsonDecode(utf8.decode(bytes)) as Map<String, dynamic>;
    } on FormatException {
      throw const VaultException('文件格式损坏或不受支持。');
    } on TypeError {
      throw const VaultException('文件结构不正确。');
    }
  }

  static bool _validId(String value) =>
      RegExp(r'^[a-f0-9]{32}$').hasMatch(value);

  static String _metadataContext(Map<String, dynamic> header) => jsonEncode({
    for (final name in [
      'format',
      'version',
      'kdf',
      'vaultId',
      'storageId',
      'salt',
      'passwordWrap',
      'recoveryWrap',
    ])
      name: header[name],
  });

  static void _checkHeader(Map<String, dynamic> snapshot) {
    if (snapshot['format'] != 'offline-vault' ||
        snapshot['version'] != 1 ||
        snapshot['kdf'] != 'argon2id-19456-2-1' ||
        snapshot['vaultId'] is! String ||
        !_validId(snapshot['vaultId'] as String) ||
        snapshot['storageId'] is! String ||
        !_validId(snapshot['storageId'] as String) ||
        snapshot['salt'] is! String ||
        snapshot['passwordWrap'] is! String ||
        snapshot['recoveryWrap'] is! String ||
        snapshot['payload'] is! String) {
      throw const VaultException('不支持的资料库版本或文件头。');
    }
    try {
      if (base64Decode(snapshot['salt'] as String).length != 16) {
        throw const FormatException();
      }
    } on FormatException {
      throw const VaultException('密码派生参数损坏。');
    }
  }

  Future<void> create(String password, String recoveryKey) => _write(() async {
    if (exists) throw const VaultException('资料库已存在。');
    VaultCrypto.checkPassword(password);
    final token = _epoch;
    final key = VaultCrypto.randomBytes(32);
    final salt = VaultCrypto.randomBytes(16);
    final vaultId = VaultCrypto.id();
    final passwordKey = await VaultCrypto.passwordKey(password, salt);
    final recovery = await VaultCrypto.subkey(
      VaultCrypto.parseRecoveryKey(recoveryKey),
      'recovery',
    );
    final header = <String, dynamic>{
      'format': 'offline-vault',
      'version': 1,
      'kdf': 'argon2id-19456-2-1',
      'vaultId': vaultId,
      'storageId': VaultCrypto.id(),
      'salt': base64Encode(salt),
      'passwordWrap': await VaultCrypto.seal(
        key,
        passwordKey,
        '$vaultId:password',
      ),
      'recoveryWrap': await VaultCrypto.seal(
        key,
        recovery,
        '$vaultId:recovery',
      ),
    };
    _checkSession(token);
    await _commit(header, key, [], const VaultSettings(), token);
  });

  static Future<_Opened> _openSnapshot(
    Map<String, dynamic> snapshot,
    String credential,
    bool recovery,
  ) async {
    _checkHeader(snapshot);
    if (!recovery && (credential.isEmpty || credential.length > 256)) {
      throw const VaultException('密码不能为空，且不能超过 256 个字符。');
    }
    final id = snapshot['vaultId'] as String;
    final wrappingKey = recovery
        ? await VaultCrypto.subkey(
            VaultCrypto.parseRecoveryKey(credential),
            'recovery',
          )
        : await VaultCrypto.passwordKey(
            credential,
            base64Decode(snapshot['salt'] as String),
          );
    final key = await VaultCrypto.open(
      snapshot[recovery ? 'recoveryWrap' : 'passwordWrap'] as String,
      wrappingKey,
      '$id:${recovery ? 'recovery' : 'password'}',
    );
    final plain = await VaultCrypto.open(
      snapshot['payload'] as String,
      await VaultCrypto.subkey(key, 'metadata'),
      _metadataContext(snapshot),
    );
    if (plain.length > maxMetadataBytes) {
      throw const VaultException('资料库条目超过安全大小限制。');
    }
    try {
      final data = _decode(plain);
      final entries = (data['entries'] as List)
          .map((e) => VaultEntry.fromJson(e as Map<String, dynamic>))
          .toList();
      final settings = VaultSettings.fromJson(
        data['settings'] as Map<String, dynamic>,
      );
      _validate(entries, settings);
      return _Opened(key, entries, settings);
    } on TypeError {
      throw const VaultException('资料库内容结构损坏。');
    } on ArgumentError {
      throw const VaultException('资料库包含不支持的字段。');
    } on FormatException {
      throw const VaultException('资料库日期或字段损坏。');
    }
  }

  static void _validate(List<VaultEntry> entries, VaultSettings settings) {
    final ids = <String>{};
    final attachments = <String>{};
    var encodedAttachments = 0;
    if (![1, 2, 5, 10].contains(settings.lockMinutes)) {
      throw const VaultException('自动锁定设置不受支持。');
    }
    for (final e in entries) {
      if (!_validId(e.id) ||
          !ids.add(e.id) ||
          e.name.trim().isEmpty ||
          (e.expiryKind == ExpiryKind.dated) != (e.expiry != null)) {
        throw const VaultException('条目数据不完整或重复。');
      }
      for (final a in e.attachments) {
        encodedAttachments += ((a.size + 30) ~/ 3) * 4 + 128;
        if (!_validId(a.id) ||
            !attachments.add(a.id) ||
            a.size < 1 ||
            a.size > maxAttachmentBytes ||
            !['pdf', 'jpg', 'png'].contains(a.type) ||
            !['front', 'back', 'file'].contains(a.role)) {
          throw const VaultException('附件信息损坏或格式不受支持。');
        }
      }
      if (encodedAttachments > maxBackupBytes - maxMetadataBytes * 2) {
        throw const VaultException('附件总容量将超过加密备份上限，请先减少附件后保存。');
      }
    }
  }

  Future<void> unlock(String password) async {
    if (!exists) throw const VaultException('请先创建或恢复资料库。');
    final token = _epoch;
    final opened = await _openSnapshot(_requireSnapshot(), password, false);
    _checkSession(token);
    _key = List.of(opened.key);
    _entries = opened.entries;
    _settings = opened.settings;
  }

  Future<void> resetPassword(String recoveryKey, String password) => _write(
    () async {
      VaultCrypto.checkPassword(password);
      if (!exists) throw const VaultException('资料库不存在。');
      final token = _epoch;
      final opened = await _openSnapshot(_requireSnapshot(), recoveryKey, true);
      final header = await _newPasswordHeader(_snapshot!, opened.key, password);
      _checkSession(token);
      await _commit(header, opened.key, opened.entries, opened.settings, token);
    },
  );

  Future<Map<String, dynamic>> _newPasswordHeader(
    Map<String, dynamic> header,
    List<int> key,
    String password,
  ) async {
    final salt = VaultCrypto.randomBytes(16);
    final wrapping = await VaultCrypto.passwordKey(password, salt);
    return {
      ...header,
      'salt': base64Encode(salt),
      'passwordWrap': await VaultCrypto.seal(
        key,
        wrapping,
        '${header['vaultId']}:password',
      ),
    };
  }

  Future<void> changePassword(String current, String password) => _write(
    () async {
      _requireKey();
      VaultCrypto.checkPassword(password);
      final token = _epoch;
      final opened = await _openSnapshot(_snapshot!, current, false);
      final header = await _newPasswordHeader(_snapshot!, opened.key, password);
      _checkSession(token);
      await _commit(header, opened.key, _entries, _settings, token);
    },
  );

  List<int> _requireKey() {
    if (_key == null) throw const VaultException('请先解锁资料库。');
    return List.of(_key!);
  }

  File _blob(String vaultId, String id) {
    if (!_validId(vaultId) || !_validId(id)) {
      throw const VaultException('无效的附件路径。');
    }
    return File(p.join(directory.path, '$vaultId-$id.blob'));
  }

  Future<void> _commit(
    Map<String, dynamic> header,
    List<int> key,
    List<VaultEntry> entries,
    VaultSettings settings,
    int token,
  ) async {
    _validate(entries, settings);
    final plain = utf8.encode(
      jsonEncode({
        'entries': entries.map((e) => e.toJson()).toList(),
        'settings': settings.toJson(),
      }),
    );
    if (plain.length > maxMetadataBytes) {
      throw const VaultException('资料库索引已达到 8 MB 上限。');
    }
    final snapshot = {
      ...header,
      'payload': await VaultCrypto.seal(
        plain,
        await VaultCrypto.subkey(key, 'metadata'),
        _metadataContext(header),
      ),
    };
    final revision = _revision + 1;
    final target = File(
      p.join(
        directory.path,
        'commit-${revision.toString().padLeft(12, '0')}.json',
      ),
    );
    final staging = File('${target.path}.pending');
    await staging.writeAsString(jsonEncode(snapshot), flush: true);
    _checkSession(token);
    // Publishing a new immutable commit leaves the previous one intact on interruption.
    await staging.rename(target.path);
    _revision = revision;
    _snapshot = snapshot;
    _damaged = false;
    initializationError = null;
    if (token == _epoch) {
      _key = List.of(key);
      _entries = List.of(entries);
      _settings = settings;
    }
    await _collectGarbage(target.path, entries, header['storageId'] as String);
  }

  Future<void> _collectGarbage(
    String keep,
    List<VaultEntry> entries,
    String vaultId,
  ) async {
    final blobs = entries
        .expand((e) => e.attachments)
        .map((a) => '$vaultId-${a.id}.blob')
        .toSet();
    await for (final entity in directory.list()) {
      if (entity is! File || entity.path == keep) continue;
      final name = p.basename(entity.path);
      if (RegExp(r'^commit-\d{12}\.json(\.pending)?$').hasMatch(name) ||
          (RegExp(r'^[a-f0-9]{32}-[a-f0-9]{32}\.blob$').hasMatch(name) &&
              !blobs.contains(name))) {
        await entity.delete();
      }
    }
  }

  Future<void> saveEntry(VaultEntry entry, List<PendingAttachment> pending) =>
      _write(() async {
        final key = _requireKey();
        final token = _epoch;
        final vaultId = _snapshot!['vaultId'] as String;
        final storageId = _snapshot!['storageId'] as String;
        final next = [..._entries.where((e) => e.id != entry.id), entry];
        _validate(next, _settings);
        for (final attachment in pending) {
          final a = attachment.metadata;
          if (!entry.attachments.any((item) => item.id == a.id) ||
              attachment.bytes.length != a.size) {
            throw const VaultException('附件内容与索引不一致。');
          }
          validateMedia(attachment.bytes, a.type);
          final blob = _blob(storageId, a.id);
          if (await blob.exists()) {
            throw const VaultException('附件标识冲突，请重新导入。');
          }
          final cipher = await VaultCrypto.seal(
            attachment.bytes,
            await VaultCrypto.subkey(key, 'attachment:${a.id}'),
            '$vaultId:${a.id}:1',
          );
          _checkSession(token);
          await blob.writeAsString(cipher, flush: true);
        }
        for (final a in entry.attachments) {
          if (!await _blob(storageId, a.id).exists()) {
            throw const VaultException('附件缺失，无法保存。');
          }
        }
        _checkSession(token);
        await _commit(_snapshot!, key, next, _settings, token);
      });

  static void validateMedia(List<int> bytes, String type) {
    if (bytes.isEmpty || bytes.length > maxAttachmentBytes) {
      throw const VaultException('单个附件须大于 0 且不超过 32 MB。');
    }
    final valid = switch (type) {
      'pdf' =>
        bytes.length >= 5 &&
            ascii.decode(bytes.take(5).toList(), allowInvalid: true) == '%PDF-',
      'png' =>
        bytes.length >= 8 &&
            bytes.take(8).join(',') == '137,80,78,71,13,10,26,10',
      'jpg' =>
        bytes.length >= 3 &&
            bytes[0] == 255 &&
            bytes[1] == 216 &&
            bytes[2] == 255,
      _ => false,
    };
    if (!valid) throw const VaultException('附件内容与文件类型不符，仅支持 JPG、PNG、PDF。');
  }

  Future<Uint8List> readAttachment(VaultAttachment attachment) async {
    final key = _requireKey();
    final token = _epoch;
    final id = _snapshot!['vaultId'] as String;
    if (!_entries.any((e) => e.attachments.any((a) => a.id == attachment.id))) {
      throw const VaultException('附件不属于当前资料库。');
    }
    final file = _blob(_snapshot!['storageId'] as String, attachment.id);
    if (!await file.exists()) throw const VaultException('附件文件缺失。');
    final bytes = await _decryptBlob(
      await _readCipher(file),
      id,
      attachment,
      key,
    );
    _checkSession(token);
    return bytes;
  }

  static Future<String> _readCipher(File file) async {
    if (await file.length() > maxAttachmentBytes * 2) {
      throw const VaultException('加密附件超出安全大小限制。');
    }
    return file.readAsString();
  }

  static Future<Uint8List> _decryptBlob(
    String cipher,
    String vaultId,
    VaultAttachment a,
    List<int> key,
  ) async {
    if (cipher.length > maxAttachmentBytes * 2) {
      throw const VaultException('加密附件超出安全大小限制。');
    }
    final bytes = await VaultCrypto.open(
      cipher,
      await VaultCrypto.subkey(key, 'attachment:${a.id}'),
      '$vaultId:${a.id}:1',
    );
    if (bytes.length != a.size) throw const VaultException('附件大小校验失败。');
    validateMedia(bytes, a.type);
    return bytes;
  }

  Future<void> deleteEntry(String id) => _write(() async {
    final key = _requireKey();
    final token = _epoch;
    await _commit(
      _snapshot!,
      key,
      _entries.where((e) => e.id != id).toList(),
      _settings,
      token,
    );
  });

  Future<void> updateSettings(VaultSettings settings) => _write(() async {
    final key = _requireKey();
    await _commit(_snapshot!, key, _entries, settings, _epoch);
  });

  Future<Uint8List> exportBackup() => _write(() async {
    final key = _requireKey();
    final token = _epoch;
    final id = _snapshot!['vaultId'] as String;
    final blobs = <String, String>{};
    var total = 0;
    for (final a in _entries.expand((e) => e.attachments)) {
      final file = _blob(_snapshot!['storageId'] as String, a.id);
      if (!await file.exists()) throw const VaultException('附件缺失，备份已取消。');
      total += await file.length();
      if (total > maxBackupBytes - maxMetadataBytes * 2) {
        throw const VaultException('备份超过 256 MB 上限，请先减少附件。');
      }
      final cipher = await _readCipher(file);
      await _decryptBlob(cipher, id, a, key);
      blobs[a.id] = cipher;
    }
    final bytes = Uint8List.fromList(
      utf8.encode(
        jsonEncode({
          'format': 'offline-vault-backup',
          'version': 1,
          'snapshot': _snapshot,
          'blobs': blobs,
        }),
      ),
    );
    if (bytes.length > maxBackupBytes) {
      throw const VaultException('备份超过 256 MB 上限。');
    }
    _checkSession(token);
    return bytes;
  });

  Future<void> restoreBackup(
    Uint8List bytes,
    String credential, {
    bool recovery = false,
  }) => _write(() async {
    final token = _epoch;
    if (bytes.length > maxBackupBytes) {
      throw const VaultException('备份超过 256 MB 上限。');
    }
    final backup = _decode(bytes);
    if (backup['format'] != 'offline-vault-backup' ||
        backup['version'] != 1 ||
        backup['snapshot'] is! Map<String, dynamic> ||
        backup['blobs'] is! Map<String, dynamic>) {
      throw const VaultException('不是受支持的加密备份文件。');
    }
    final snapshot = backup['snapshot'] as Map<String, dynamic>;
    final opened = await _openSnapshot(snapshot, credential, recovery);
    final sourceId = snapshot['vaultId'] as String;
    final blobs = backup['blobs'] as Map<String, dynamic>;
    final expected = opened.entries.expand((e) => e.attachments).toList();
    if (expected.length != blobs.length) {
      throw const VaultException('备份附件清单不一致。');
    }
    for (final a in expected) {
      if (blobs[a.id] is! String) throw const VaultException('备份附件缺失。');
      await _decryptBlob(blobs[a.id] as String, sourceId, a, opened.key);
      _checkSession(token);
    }
    final stagedId = VaultCrypto.id();
    final staged = <File>[];
    try {
      for (final a in expected) {
        final target = _blob(stagedId, a.id);
        staged.add(target);
        await target.writeAsString(blobs[a.id] as String, flush: true);
        _checkSession(token);
      }
      _checkSession(token);
      await _commit(
        {...snapshot, 'storageId': stagedId},
        opened.key,
        opened.entries,
        opened.settings,
        token,
      );
    } finally {
      if (_snapshot?['storageId'] != stagedId) {
        for (final file in staged) {
          if (await file.exists()) await file.delete();
        }
      }
    }
  });

  Future<void> verifyPassword(String password) async {
    if (!exists) throw const VaultException('资料库不存在。');
    final token = _epoch;
    await _openSnapshot(_requireSnapshot(), password, false);
    _checkSession(token);
  }

  Future<void> destroy(String password) => _write(() async {
    if (!exists) throw const VaultException('资料库不存在。');
    final token = _epoch;
    await _openSnapshot(_requireSnapshot(), password, false);
    _checkSession(token);
    // Remove only files owned by the vault format, never the application directory.
    await for (final file in directory.list()) {
      final name = p.basename(file.path);
      if (file is File &&
          (RegExp(r'^commit-\d{12}\.json(\.pending)?$').hasMatch(name) ||
              RegExp(r'^[a-f0-9]{32}-[a-f0-9]{32}\.(blob|staging)$')
                  .hasMatch(name))) {
        await file.delete();
      }
    }
    lock();
    _snapshot = null;
    _damaged = false;
    initializationError = null;
    _revision = 0;
  });
}
