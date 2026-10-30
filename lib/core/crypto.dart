import 'dart:convert';
import 'dart:isolate';
import 'dart:math';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';

class VaultException implements Exception {
  const VaultException(this.message);
  final String message;
  @override
  String toString() => message;
}

class VaultCrypto {
  static const memory = 19456;
  static const iterations = 2;
  static final _random = Random.secure();

  static Uint8List randomBytes(int length) =>
      Uint8List.fromList(List.generate(length, (_) => _random.nextInt(256)));

  static String id() =>
      randomBytes(16).map((b) => b.toRadixString(16).padLeft(2, '0')).join();

  static Future<List<int>> passwordKey(String password, List<int> salt) =>
      Isolate.run(() async {
        final key = await Argon2id(
          parallelism: 1,
          memory: memory,
          iterations: iterations,
          hashLength: 32,
        ).deriveKey(secretKey: SecretKey(utf8.encode(password)), nonce: salt);
        return key.extractBytes();
      });

  static Future<List<int>> subkey(List<int> key, String purpose) async =>
      (await Hkdf(hmac: Hmac.sha256(), outputLength: 32).deriveKey(
        secretKey: SecretKey(key),
        nonce: utf8.encode('offline-vault-v1'),
        info: utf8.encode(purpose),
      )).extractBytes();

  static Future<String> seal(
    List<int> data,
    List<int> key,
    String context,
  ) async {
    final box = await AesGcm.with256bits().encrypt(
      data,
      secretKey: SecretKey(key),
      nonce: randomBytes(12),
      aad: utf8.encode(context),
    );
    return base64Encode(box.concatenation());
  }

  static Future<Uint8List> open(
    String encoded,
    List<int> key,
    String context,
  ) async {
    try {
      final bytes = base64Decode(encoded);
      if (bytes.length < 28) throw const FormatException('Short ciphertext');
      final plain = await AesGcm.with256bits().decrypt(
        SecretBox.fromConcatenation(bytes, nonceLength: 12, macLength: 16),
        secretKey: SecretKey(key),
        aad: utf8.encode(context),
      );
      return Uint8List.fromList(plain);
    } on SecretBoxAuthenticationError {
      throw const VaultException('密码或恢复密钥不正确，或者资料已损坏。');
    } on FormatException {
      throw const VaultException('加密数据格式损坏。');
    }
  }

  static String newRecoveryKey() {
    final hex = randomBytes(32)
        .map((b) => b.toRadixString(16).padLeft(2, '0'))
        .join()
        .toUpperCase();
    return List.generate(8, (i) => hex.substring(i * 8, i * 8 + 8)).join('-');
  }

  static List<int> parseRecoveryKey(String input) {
    final hex = input.replaceAll(RegExp(r'[\s-]'), '').toLowerCase();
    if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(hex)) {
      throw const VaultException('恢复密钥应为 8 组、每组 8 位的字符。');
    }
    return List.generate(
      32,
      (i) => int.parse(hex.substring(i * 2, i * 2 + 2), radix: 16),
    );
  }

  static void checkPassword(String password) {
    if (password.length < 12 || password.length > 256) {
      throw const VaultException('密码长度需为 12–256 个字符，建议使用长口令。');
    }
  }
}
