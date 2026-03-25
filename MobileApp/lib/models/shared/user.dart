class User {
  final int id;
  final String email;
  final String? name;
  final String? title;
  final String role;
  final bool chatbotEnabled;
  final String? profileColor;
  final List<int>? countryIds;

  User({
    required this.id,
    required this.email,
    this.name,
    this.title,
    required this.role,
    this.chatbotEnabled = false,
    this.profileColor,
    this.countryIds,
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] ?? 0,
      email: json['email'] ?? '',
      name: json['name'],
      title: json['title'],
      role: json['role'] ?? 'focal_point',
      chatbotEnabled: json['chatbot_enabled'] ?? false,
      profileColor: json['profile_color'],
      countryIds: json['country_ids'] != null
          ? List<int>.from(json['country_ids'])
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'email': email,
      'name': name,
      'title': title,
      'role': role,
      'chatbot_enabled': chatbotEnabled,
      'profile_color': profileColor,
      'country_ids': countryIds,
    };
  }

  String get displayName => name ?? email.split('@').first;
}
