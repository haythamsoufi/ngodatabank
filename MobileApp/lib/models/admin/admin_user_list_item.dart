class AdminUserListItem {
  final int id;
  final String email;
  final String? name;
  final String? title;
  final bool active;
  final List<AdminUserRbacRole> rbacRoles;

  AdminUserListItem({
    required this.id,
    required this.email,
    this.name,
    this.title,
    required this.active,
    required this.rbacRoles,
  });

  factory AdminUserListItem.fromJson(Map<String, dynamic> json) {
    final rolesRaw = json['rbac_roles'];
    final roles = <AdminUserRbacRole>[];
    if (rolesRaw is List) {
      for (final e in rolesRaw) {
        if (e is Map<String, dynamic>) {
          roles.add(AdminUserRbacRole.fromJson(e));
        }
      }
    }
    return AdminUserListItem(
      id: json['id'] is int ? json['id'] as int : int.tryParse('${json['id']}') ?? 0,
      email: json['email']?.toString() ?? '',
      name: json['name']?.toString(),
      title: json['title']?.toString(),
      active: json['active'] == true,
      rbacRoles: roles,
    );
  }

  String get displayName {
    final n = name?.trim();
    if (n != null && n.isNotEmpty) return n;
    return email;
  }

  String get rolesLabel {
    if (rbacRoles.isEmpty) return '—';
    return rbacRoles.map((r) => r.name ?? r.code).where((s) => s.isNotEmpty).join(', ');
  }
}

class AdminUserRbacRole {
  final int? id;
  final String code;
  final String? name;

  AdminUserRbacRole({this.id, required this.code, this.name});

  factory AdminUserRbacRole.fromJson(Map<String, dynamic> json) {
    return AdminUserRbacRole(
      id: json['id'] is int ? json['id'] as int : int.tryParse('${json['id']}'),
      code: json['code']?.toString() ?? '',
      name: json['name']?.toString(),
    );
  }
}
