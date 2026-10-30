import 'dart:io';
import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../core/crypto.dart';
import '../core/vault_store.dart';

class FileAccess {
  static const _platform = MethodChannel('app.offlinevault/security');
  static const mediaGroup = XTypeGroup(
    label: '图片或 PDF',
    extensions: ['jpg', 'jpeg', 'png', 'pdf'],
    uniformTypeIdentifiers: ['public.jpeg', 'public.png', 'com.adobe.pdf'],
    mimeTypes: ['image/jpeg', 'image/png', 'application/pdf'],
  );
  static const imageGroup = XTypeGroup(
    label: '图片',
    extensions: ['jpg', 'jpeg', 'png'],
    uniformTypeIdentifiers: ['public.jpeg', 'public.png'],
    mimeTypes: ['image/jpeg', 'image/png'],
  );

  static Future<Uint8List> readLimited(XFile file, int maximum) async {
    if (file.path.startsWith('native:')) {
      final bytes = await _platform.invokeMethod<Uint8List>(
        'readSelectedFile',
        {'uri': file.path.substring(7), 'maximum': maximum},
      );
      if (bytes == null || bytes.length > maximum) {
        throw const VaultException('无法读取所选文件或文件超过大小限制。');
      }
      return bytes;
    }
    if (await file.length() > maximum) {
      throw VaultException('文件超过 ${maximum ~/ (1024 * 1024)} MB 上限。');
    }
    final builder = BytesBuilder(copy: false);
    await for (final chunk in file.openRead()) {
      if (builder.length + chunk.length > maximum) {
        throw const VaultException('文件大小发生变化，导入已取消。');
      }
      builder.add(chunk);
    }
    return builder.takeBytes();
  }

  static Future<void> protectDirectory(String path) async {
    if (Platform.isIOS) {
      await _platform.invokeMethod<void>('protectDirectory', {'path': path});
    }
  }

  static Future<bool> saveBackup(Uint8List bytes) async {
    final name =
        'vault-${DateTime.now().toIso8601String().substring(0, 10)}.ovault';
    if (Platform.isAndroid || Platform.isIOS) {
      final temp = File(
        p.join(
          (await getTemporaryDirectory()).path,
          '${VaultCrypto.id()}.ovault',
        ),
      );
      try {
        await temp.writeAsBytes(bytes, flush: true);
        return await _platform.invokeMethod<bool>('exportBackup', {
              'path': temp.path,
              'name': name,
            }) ??
            false;
      } finally {
        if (await temp.exists()) await temp.delete();
      }
    }
    final location = await getSaveLocation(suggestedName: name);
    if (location == null) return false;
    await XFile.fromData(
      bytes,
      mimeType: 'application/octet-stream',
      name: name,
    ).saveTo(location.path);
    return true;
  }

  static String mediaType(String name) {
    final ext = p.extension(name).toLowerCase();
    return switch (ext) {
      '.jpeg' || '.jpg' => 'jpg',
      '.png' => 'png',
      '.pdf' => 'pdf',
      _ => throw const VaultException('仅支持 JPG、PNG、PDF。'),
    };
  }

  static Future<XFile?> _pickNative(String kind) async {
    final selected = await _platform.invokeMapMethod<String, String>(
      'pickFile',
      {'kind': kind},
    );
    if (selected == null) return null;
    final uri = selected['uri'];
    final name = selected['name'];
    if (uri == null || name == null) throw const VaultException('系统返回了无效文件信息。');
    return XFile('native:$uri', name: name);
  }

  static Future<XFile?> pickMedia(bool imagesOnly) =>
      Platform.isAndroid || Platform.isIOS
      ? _pickNative(imagesOnly ? 'image' : 'media')
      : openFile(acceptedTypeGroups: [imagesOnly ? imageGroup : mediaGroup]);

  static Future<XFile?> pickBackup() => Platform.isAndroid || Platform.isIOS
      ? _pickNative('backup')
      : openFile(
          acceptedTypeGroups: const [
            XTypeGroup(
              label: '加密备份',
              extensions: ['ovault'],
              uniformTypeIdentifiers: ['public.data'],
              mimeTypes: ['application/octet-stream', 'application/json'],
            ),
          ],
        );

  static Future<Uint8List> readBackup(XFile file) =>
      readLimited(file, VaultStore.maxBackupBytes);
}
