import 'package:flutter_test/flutter_test.dart';
import 'package:offline_vault/core/models.dart';
import 'package:offline_vault/services/reminders.dart';

void main() {
  VaultEntry dated(DateTime date, {bool remind = true}) => VaultEntry(
    id: 'test',
    kind: EntryKind.document,
    name: '保险单',
    category: '保险',
    tags: ['汽车'],
    notes: '续保',
    expiryKind: ExpiryKind.dated,
    expiry: date,
    remind: remind,
  );

  test('calendar day differences ignore DST and time of day', () {
    expect(daysUntil(DateTime(2028, 3, 1), DateTime(2028, 2, 28, 23, 59)), 2);
    expect(daysUntil(DateTime(2026, 10, 29), DateTime(2026, 10, 29, 23)), 0);
    expect(daysUntil(DateTime(2026, 10, 28), DateTime(2026, 10, 29)), -1);
  });

  test(
    'reminders have precise offsets, are deduplicated and omit past times',
    () {
      final entry = dated(DateTime(2026, 12, 1));
      final dates = reminderDates([entry, entry], DateTime(2026, 10, 29));
      expect(dates, [
        DateTime(2026, 11, 1, 9),
        DateTime(2026, 11, 24, 9),
        DateTime(2026, 12, 1, 9),
      ]);
      expect(reminderDates([entry], DateTime(2026, 11, 24, 10)), [
        DateTime(2026, 12, 1, 9),
      ]);
      expect(
        reminderDates([
          dated(DateTime(2026, 12, 1), remind: false),
        ], DateTime(2026, 1)),
        isEmpty,
      );
    },
  );

  test('unknown and permanent expiry never schedule notifications', () {
    final entries = [
      VaultEntry(
        id: 'a',
        kind: EntryKind.certificate,
        name: '长期证件',
        expiryKind: ExpiryKind.permanent,
      ),
      VaultEntry(id: 'b', kind: EntryKind.document, name: '无日期文件'),
    ];
    expect(reminderDates(entries, DateTime.now()), isEmpty);
    expect(entries.first.expiryLabel, '长期有效');
    expect(entries.last.expiryLabel, '未设置有效期');
  });

  test('search covers metadata but not sensitive number', () {
    final e = dated(DateTime(2030, 1));
    expect(e.matches('汽车'), isTrue);
    expect(e.matches('保险'), isTrue);
    expect(e.matches('续保'), isTrue);
    expect(e.matches('其他'), isFalse);
    final json = e.toJson();
    json['number'] = '999999SECRET';
    expect(VaultEntry.fromJson(json).matches('999999SECRET'), isFalse);
    expect(VaultEntry.fromJson(json).expiry, e.expiry);
  });
}
