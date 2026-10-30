import 'dart:io';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

import '../core/models.dart';
import '../core/crypto.dart';

List<DateTime> reminderDates(Iterable<VaultEntry> entries, DateTime now) {
  final dates = <DateTime>{};
  for (final entry in entries) {
    if (!entry.remind || entry.expiryKind != ExpiryKind.dated) continue;
    for (final days in [30, 7, 0]) {
      final date = DateTime(
        entry.expiry!.year,
        entry.expiry!.month,
        entry.expiry!.day - days,
        9,
      );
      if (date.isAfter(now)) dates.add(date);
    }
  }
  return dates.toList()..sort();
}

class ReminderService {
  final _plugin = FlutterLocalNotificationsPlugin();
  bool _ready = false;

  Future<void> initialize() async {
    tzdata.initializeTimeZones();
    final zone = await FlutterTimezone.getLocalTimezone();
    tz.setLocalLocation(tz.getLocation(zone.identifier));
    if (_ready) return;
    final initialized = await _plugin.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(
          requestAlertPermission: false,
          requestBadgePermission: false,
          requestSoundPermission: false,
        ),
        windows: WindowsInitializationSettings(
          appName: '离线资料柜',
          appUserModelId: 'OfflineVault.PersonalVault',
          guid: 'b6f03da1-df67-4c62-9c2a-aec57ddcb148',
        ),
      ),
    );
    if (initialized == false) {
      throw StateError('系统本地通知初始化失败。');
    }
    _ready = true;
  }

  Future<bool> requestPermission() async {
    await initialize();
    if (Platform.isAndroid) {
      return await _plugin
              .resolvePlatformSpecificImplementation<
                AndroidFlutterLocalNotificationsPlugin
              >()!
              .requestNotificationsPermission() ??
          false;
    }
    if (Platform.isIOS) {
      return await _plugin
              .resolvePlatformSpecificImplementation<
                IOSFlutterLocalNotificationsPlugin
              >()!
              .requestPermissions(alert: true, badge: false, sound: true) ??
          false;
    }
    return true;
  }

  Future<void> schedule(List<DateTime> dates, bool enabled) async {
    await initialize();
    await _plugin.cancelAll();
    if (!enabled) return;
    if (Platform.isAndroid &&
        await _plugin
                .resolvePlatformSpecificImplementation<
                  AndroidFlutterLocalNotificationsPlugin
                >()!
                .areNotificationsEnabled() !=
            true) {
      throw const VaultException('系统通知权限未开启，请在设置中允许后重新启用提醒。');
    }
    if (Platform.isIOS &&
        (await _plugin
                    .resolvePlatformSpecificImplementation<
                      IOSFlutterLocalNotificationsPlugin
                    >()!
                    .checkPermissions())
                ?.isEnabled !=
            true) {
      throw const VaultException('系统通知权限未开启，请在设置中允许后重新启用提醒。');
    }
    for (var i = 0; i < dates.length && i < 60; i++) {
      final d = dates[i];
      await _plugin.zonedSchedule(
        id: i + 1,
        title: '资料到期提醒',
        body: '你有资料即将到期，请打开资料柜查看。',
        scheduledDate: tz.TZDateTime(tz.local, d.year, d.month, d.day, 9),
        notificationDetails: const NotificationDetails(
          android: AndroidNotificationDetails(
            'expiry',
            '资料到期提醒',
            channelDescription: '仅在本机提醒，不包含资料名称或号码。',
            visibility: NotificationVisibility.private,
          ),
          iOS: DarwinNotificationDetails(),
          windows: WindowsNotificationDetails(),
        ),
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      );
    }
  }

  Future<void> cancelAll() async {
    await initialize();
    await _plugin.cancelAll();
  }
}
