import 'dart:io';

class OfflineHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) =>
      throw const HttpException('此应用为离线资料柜，不允许网络访问。');
}
