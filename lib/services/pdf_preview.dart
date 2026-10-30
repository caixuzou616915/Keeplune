import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:pdfrx/pdfrx.dart';

Widget buildPdfPreview(Uint8List bytes, String id) {
  Pdfrx.createHttpClient = () => throw StateError('离线模式不允许加载远程 PDF 或网络资源。');
  return PdfViewer.data(
    bytes,
    sourceName: id,
    params: const PdfViewerParams(
      textSelectionParams: null,
      linkHandlerParams: null,
      maxImageBytesCachedOnMemory: 32 * 1024 * 1024,
    ),
  );
}
