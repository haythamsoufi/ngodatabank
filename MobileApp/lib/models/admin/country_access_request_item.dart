class AccessRequestUserRef {
  final int? id;
  final String? email;
  final String? name;

  const AccessRequestUserRef({
    this.id,
    this.email,
    this.name,
  });

  factory AccessRequestUserRef.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return const AccessRequestUserRef();
    }
    return AccessRequestUserRef(
      id: json['id'] as int?,
      email: json['email'] as String?,
      name: json['name'] as String?,
    );
  }
}

class AccessRequestCountryRef {
  final int? id;
  final String? name;
  final String? iso2;

  const AccessRequestCountryRef({
    this.id,
    this.name,
    this.iso2,
  });

  factory AccessRequestCountryRef.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return const AccessRequestCountryRef();
    }
    return AccessRequestCountryRef(
      id: json['id'] as int?,
      name: json['name'] as String?,
      iso2: json['iso2'] as String?,
    );
  }
}

class CountryAccessRequestItem {
  final int id;
  final String status;
  final String? requestMessage;
  final String? createdAt;
  final String? processedAt;
  final String? adminNotes;
  final AccessRequestUserRef user;
  final AccessRequestCountryRef country;
  final AccessRequestUserRef? processedBy;

  const CountryAccessRequestItem({
    required this.id,
    required this.status,
    this.requestMessage,
    this.createdAt,
    this.processedAt,
    this.adminNotes,
    required this.user,
    required this.country,
    this.processedBy,
  });

  factory CountryAccessRequestItem.fromJson(Map<String, dynamic> json) {
    return CountryAccessRequestItem(
      id: json['id'] as int,
      status: json['status'] as String? ?? '',
      requestMessage: json['request_message'] as String?,
      createdAt: json['created_at'] as String?,
      processedAt: json['processed_at'] as String?,
      adminNotes: json['admin_notes'] as String?,
      user: AccessRequestUserRef.fromJson(
        json['user'] as Map<String, dynamic>?,
      ),
      country: AccessRequestCountryRef.fromJson(
        json['country'] as Map<String, dynamic>?,
      ),
      processedBy: json['processed_by'] != null
          ? AccessRequestUserRef.fromJson(
              json['processed_by'] as Map<String, dynamic>?,
            )
          : null,
    );
  }
}
