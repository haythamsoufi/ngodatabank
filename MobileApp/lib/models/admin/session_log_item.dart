/// One row from [GET /admin/api/analytics/session-logs].
class SessionLogItem {
  const SessionLogItem({
    required this.sessionId,
    this.sessionStartIso,
    this.sessionEndIso,
    this.lastActivityIso,
    this.durationMinutes,
    required this.pageViews,
    required this.activityCount,
    required this.isActive,
    this.deviceType,
    this.browser,
    this.operatingSystem,
    this.ipAddress,
    this.userAgent,
    this.userName,
    this.userEmail,
  });

  final String sessionId;
  final String? sessionStartIso;
  final String? sessionEndIso;
  final String? lastActivityIso;
  final int? durationMinutes;
  final int pageViews;
  final int activityCount;
  final bool isActive;
  final String? deviceType;
  final String? browser;
  final String? operatingSystem;
  final String? ipAddress;
  final String? userAgent;
  final String? userName;
  final String? userEmail;

  factory SessionLogItem.fromJson(Map<String, dynamic> json) {
    final user = json['user'];
    String? uname;
    String? uemail;
    if (user is Map<String, dynamic>) {
      uname = user['name']?.toString();
      uemail = user['email']?.toString();
    }
    final dm = json['duration_minutes'];
    return SessionLogItem(
      sessionId: json['session_id']?.toString() ?? '',
      sessionStartIso: json['session_start']?.toString(),
      sessionEndIso: json['session_end']?.toString(),
      lastActivityIso: json['last_activity']?.toString(),
      durationMinutes: dm == null
          ? null
          : (dm is int ? dm : int.tryParse('$dm')),
      pageViews: json['page_views'] is int
          ? json['page_views'] as int
          : int.tryParse('${json['page_views'] ?? 0}') ?? 0,
      activityCount: json['activity_count'] is int
          ? json['activity_count'] as int
          : int.tryParse('${json['activity_count'] ?? 0}') ?? 0,
      isActive: json['is_active'] == true,
      deviceType: json['device_type']?.toString(),
      browser: json['browser']?.toString(),
      operatingSystem: json['operating_system']?.toString(),
      ipAddress: json['ip_address']?.toString(),
      userAgent: json['user_agent']?.toString(),
      userName: uname,
      userEmail: uemail,
    );
  }
}
