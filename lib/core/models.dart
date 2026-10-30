enum EntryKind { certificate, document }

enum ExpiryKind { unknown, permanent, dated }

DateTime dateOnly(DateTime value) =>
    DateTime(value.year, value.month, value.day);

String formatDate(DateTime value) =>
    '${value.year}-${value.month.toString().padLeft(2, '0')}-${value.day.toString().padLeft(2, '0')}';

int daysUntil(DateTime expiry, DateTime now) {
  final a = DateTime.utc(expiry.year, expiry.month, expiry.day);
  final b = DateTime.utc(now.year, now.month, now.day);
  return a.difference(b).inDays;
}

class VaultAttachment {
  const VaultAttachment({
    required this.id,
    required this.name,
    required this.role,
    required this.type,
    required this.size,
  });
  final String id;
  final String name;
  final String role;
  final String type;
  final int size;

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'role': role,
    'type': type,
    'size': size,
  };
  factory VaultAttachment.fromJson(Map<String, dynamic> json) =>
      VaultAttachment(
        id: json['id'] as String,
        name: json['name'] as String,
        role: json['role'] as String,
        type: json['type'] as String,
        size: json['size'] as int,
      );
}

class VaultEntry {
  VaultEntry({
    required this.id,
    required this.kind,
    required this.name,
    this.holder = '',
    this.certificateType = '',
    this.number = '',
    this.category = '',
    this.tags = const [],
    this.notes = '',
    this.expiryKind = ExpiryKind.unknown,
    this.expiry,
    this.remind = true,
    this.attachments = const [],
    DateTime? updatedAt,
  }) : updatedAt = updatedAt ?? DateTime.now();

  final String id;
  final EntryKind kind;
  final String name;
  final String holder;
  final String certificateType;
  final String number;
  final String category;
  final List<String> tags;
  final String notes;
  final ExpiryKind expiryKind;
  final DateTime? expiry;
  final bool remind;
  final List<VaultAttachment> attachments;
  final DateTime updatedAt;

  String get expiryLabel => switch (expiryKind) {
    ExpiryKind.unknown => '未设置有效期',
    ExpiryKind.permanent => '长期有效',
    ExpiryKind.dated => '有效至 ${formatDate(expiry!)}',
  };

  bool matches(String query) => [
    name,
    holder,
    certificateType,
    category,
    notes,
    ...tags,
  ].join('\n').toLowerCase().contains(query.toLowerCase().trim());

  Map<String, dynamic> toJson() => {
    'id': id,
    'kind': kind.name,
    'name': name,
    'holder': holder,
    'certificateType': certificateType,
    'number': number,
    'category': category,
    'tags': tags,
    'notes': notes,
    'expiryKind': expiryKind.name,
    'expiry': expiry == null ? null : formatDate(expiry!),
    'remind': remind,
    'attachments': attachments.map((a) => a.toJson()).toList(),
    'updatedAt': updatedAt.toIso8601String(),
  };

  factory VaultEntry.fromJson(Map<String, dynamic> json) => VaultEntry(
    id: json['id'] as String,
    kind: EntryKind.values.byName(json['kind'] as String),
    name: json['name'] as String,
    holder: json['holder'] as String,
    certificateType: json['certificateType'] as String,
    number: json['number'] as String,
    category: json['category'] as String,
    tags: (json['tags'] as List).cast<String>(),
    notes: json['notes'] as String,
    expiryKind: ExpiryKind.values.byName(json['expiryKind'] as String),
    expiry: json['expiry'] == null
        ? null
        : DateTime.parse(json['expiry'] as String),
    remind: json['remind'] as bool,
    attachments: (json['attachments'] as List)
        .map((a) => VaultAttachment.fromJson(a as Map<String, dynamic>))
        .toList(),
    updatedAt: DateTime.parse(json['updatedAt'] as String),
  );
}

class VaultSettings {
  const VaultSettings({this.lockMinutes = 2, this.notifications = false});
  final int lockMinutes;
  final bool notifications;
  Map<String, dynamic> toJson() => {
    'lockMinutes': lockMinutes,
    'notifications': notifications,
  };
  factory VaultSettings.fromJson(Map<String, dynamic> json) => VaultSettings(
    lockMinutes: json['lockMinutes'] as int,
    notifications: json['notifications'] as bool,
  );
}
