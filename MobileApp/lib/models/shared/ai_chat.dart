class AiChatMessage {
  final String role; // 'user' | 'assistant' | 'error'
  final String content;
  final DateTime createdAt;
  final String? errorType; // 'quota_exceeded' | 'server_error' | 'network_error'
  final double? retryDelay; // seconds

  AiChatMessage({
    required this.role,
    required this.content,
    DateTime? createdAt,
    this.errorType,
    this.retryDelay,
  }) : createdAt = createdAt ?? DateTime.now();
}

class AiConversationSummary {
  final String id;
  final String? title;
  final DateTime? updatedAt;
  final DateTime? lastMessageAt;

  AiConversationSummary({
    required this.id,
    this.title,
    this.updatedAt,
    this.lastMessageAt,
  });

  factory AiConversationSummary.fromJson(Map<String, dynamic> json) {
    DateTime? _dt(String? s) => s == null ? null : DateTime.tryParse(s);
    return AiConversationSummary(
      id: json['id']?.toString() ?? '',
      title: json['title']?.toString(),
      updatedAt: _dt(json['updated_at']?.toString()),
      lastMessageAt: _dt(json['last_message_at']?.toString()),
    );
  }
}
