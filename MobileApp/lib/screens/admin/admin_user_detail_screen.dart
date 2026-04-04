import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../models/admin/admin_user_detail.dart';
import '../../models/admin/admin_user_list_item.dart';
import '../../providers/admin/manage_users_provider.dart';
import '../../utils/ios_constants.dart';
import '../../widgets/app_bar.dart';

/// Read-only profile aligned with backoffice user form tabs (details, entity grants, RBAC).
class AdminUserDetailScreen extends StatefulWidget {
  const AdminUserDetailScreen({super.key, required this.summary});

  final AdminUserListItem summary;

  @override
  State<AdminUserDetailScreen> createState() => _AdminUserDetailScreenState();
}

class _AdminUserDetailScreenState extends State<AdminUserDetailScreen> {
  AdminUserDetail? _detail;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final detail =
        await context.read<ManageUsersProvider>().fetchUserDetail(widget.summary.id);
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (detail == null) {
        _error = AppLocalizations.of(context)!.failedLoadUserProfile;
      } else {
        _detail = detail;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final detail = _detail;
    final title = detail?.displayName ?? widget.summary.displayName;

    return Scaffold(
      appBar: AppAppBar(title: title),
      body: _loading && detail == null
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const CircularProgressIndicator(),
                  const SizedBox(height: 16),
                  Text(loc.loadingUserProfile),
                ],
              ),
            )
          : _error != null && detail == null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.error_outline, size: 48, color: Theme.of(context).colorScheme.error),
                        const SizedBox(height: 16),
                        Text(_error!, textAlign: TextAlign.center),
                        const SizedBox(height: 24),
                        FilledButton.icon(
                          onPressed: _load,
                          icon: const Icon(Icons.refresh),
                          label: Text(loc.retry),
                        ),
                      ],
                    ),
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
                    children: [
                      if (detail != null) ...[
                        _accountCard(context, loc, detail),
                        const SizedBox(height: 16),
                        _sectionTitle(context, loc.assignedRolesTitle),
                        const SizedBox(height: 8),
                        _rolesOverview(context, loc, detail),
                        const SizedBox(height: 20),
                        _sectionTitle(context, loc.permissionsByRole),
                        const SizedBox(height: 8),
                        if (detail.rbacRoles.isEmpty)
                          Text(
                            loc.noRolesAssigned,
                            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                                ),
                          )
                        else
                          ...detail.rbacRoles.map((r) => _roleExpansion(context, r)),
                        const SizedBox(height: 20),
                        _sectionTitle(context, loc.allPermissionsUnion),
                        const SizedBox(height: 8),
                        _effectivePermissions(context, detail.effectivePermissions),
                        const SizedBox(height: 20),
                        _sectionTitle(context, loc.entityPermissionsTitle),
                        const SizedBox(height: 8),
                        _entityList(context, loc, detail.entityPermissions),
                        const SizedBox(height: 24),
                        Text(
                          loc.manageUsersDetailFooter,
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                color: Theme.of(context).colorScheme.onSurfaceVariant,
                              ),
                        ),
                      ],
                    ],
                  ),
                ),
    );
  }

  Widget _sectionTitle(BuildContext context, String text) {
    return Text(
      text,
      style: Theme.of(context).textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w600,
          ),
    );
  }

  Widget _accountCard(BuildContext context, AppLocalizations loc, AdminUserDetail d) {
    final colorHex = d.profileColor;
    Color? tint;
    if (colorHex != null && colorHex.startsWith('#') && colorHex.length >= 7) {
      try {
        tint = Color(int.parse(colorHex.replaceFirst('#', '0xFF')));
      } catch (_) {}
    }

    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (tint != null)
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: tint,
                      border: Border.all(color: Theme.of(context).dividerColor),
                    ),
                  )
                else
                  Icon(Icons.person_outline, size: 44, color: Theme.of(context).colorScheme.outline),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        d.displayName,
                        style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 4),
                      Text(d.email, style: Theme.of(context).textTheme.bodyMedium),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 8,
                        runSpacing: 6,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          _statusChip(context, loc, d.active),
                          _roleTypeChip(context, loc, d),
                          if (d.isSystemManager) _systemManagerChip(context, loc),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
            if (d.title != null && d.title!.trim().isNotEmpty) ...[
              const Divider(height: 24),
              Text(loc.title, style: Theme.of(context).textTheme.labelMedium),
              const SizedBox(height: 4),
              Text(d.title!, style: Theme.of(context).textTheme.bodyMedium),
            ],
            const Divider(height: 24),
            Row(
              children: [
                Icon(
                  d.chatbotEnabled ? Icons.check_circle_outline : Icons.cancel_outlined,
                  size: 20,
                  color: d.chatbotEnabled ? IOSColors.systemGreen : Theme.of(context).colorScheme.outline,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(loc.chatbot, style: Theme.of(context).textTheme.bodyMedium),
                ),
              ],
            ),
            if (colorHex != null && colorHex.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(loc.profileColor, style: Theme.of(context).textTheme.labelMedium),
              const SizedBox(height: 4),
              Text(colorHex, style: Theme.of(context).textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }

  Widget _statusChip(BuildContext context, AppLocalizations loc, bool active) {
    return Chip(
      visualDensity: VisualDensity.compact,
      label: Text(active ? loc.activeStatus : loc.inactiveStatus),
      avatar: Icon(
        active ? Icons.check_circle_outline : Icons.cancel_outlined,
        size: 18,
        color: active ? IOSColors.systemGreen : Theme.of(context).colorScheme.outline,
      ),
    );
  }

  Widget _roleTypeChip(BuildContext context, AppLocalizations loc, AdminUserDetail d) {
    final isAdmin = d.computedRoleType == 'admin';
    return Chip(
      visualDensity: VisualDensity.compact,
      label: Text(isAdmin ? loc.adminRole : loc.focalPointRole),
      backgroundColor: isAdmin
          ? Theme.of(context).colorScheme.primaryContainer.withValues(alpha: 0.5)
          : Theme.of(context).colorScheme.secondaryContainer.withValues(alpha: 0.45),
    );
  }

  Widget _systemManagerChip(BuildContext context, AppLocalizations loc) {
    return Chip(
      visualDensity: VisualDensity.compact,
      label: Text(loc.systemManagerRole),
      backgroundColor: Theme.of(context).colorScheme.errorContainer.withValues(alpha: 0.55),
    );
  }

  Widget _rolesOverview(BuildContext context, AppLocalizations loc, AdminUserDetail d) {
    final assignment = d.rbacRoles.where((r) => r.code.startsWith('assignment_')).toList();
    final adminSys = d.rbacRoles
        .where((r) => r.code == 'system_manager' || r.code.startsWith('admin_'))
        .toList();
    final other = d.rbacRoles
        .where(
          (r) =>
              r.code != 'system_manager' &&
              !r.code.startsWith('admin_') &&
              !r.code.startsWith('assignment_'),
        )
        .toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (assignment.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(
            loc.userDirAssignmentRoles,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: assignment.map((r) => _roleNameChip(context, r.name, r.code)).toList(),
          ),
        ],
        if (adminSys.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(
            loc.userDirAdminRoles,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: adminSys.map((r) => _roleNameChip(context, r.name, r.code)).toList(),
          ),
        ],
        if (other.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(
            loc.userDirOtherRoles,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: other.map((r) => _roleNameChip(context, r.name, r.code)).toList(),
          ),
        ],
        if (assignment.isEmpty && adminSys.isEmpty && other.isEmpty)
          Text(
            loc.noRolesAssigned,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
      ],
    );
  }

  Widget _roleNameChip(BuildContext context, String name, String code) {
    final label = name.trim().isNotEmpty ? name : code;
    final isSys = code == 'system_manager';
    final isAssignment = code.startsWith('assignment_');
    Color? bg;
    if (isSys) {
      bg = Theme.of(context).colorScheme.errorContainer.withValues(alpha: 0.45);
    } else if (isAssignment) {
      bg = IOSColors.systemGreen.withValues(alpha: 0.18);
    } else if (code.startsWith('admin_')) {
      bg = Theme.of(context).colorScheme.primaryContainer.withValues(alpha: 0.4);
    }
    return Chip(
      label: Text(label, maxLines: 2, overflow: TextOverflow.ellipsis),
      visualDensity: VisualDensity.compact,
      backgroundColor: bg,
    );
  }

  Widget _roleExpansion(BuildContext context, AdminRbacRoleDetail r) {
    final label = r.name.trim().isNotEmpty ? r.name : r.code;
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ExpansionTile(
        title: Text(label, maxLines: 2, overflow: TextOverflow.ellipsis),
        subtitle: r.description != null && r.description!.trim().isNotEmpty
            ? Text(
                r.description!,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              )
            : Text(
                r.code,
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
              ),
        children: [
          if (r.permissions.isEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: Text(
                AppLocalizations.of(context)!.noPermissionsListed,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            )
          else
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: r.permissions
                      .map(
                        (p) => Padding(
                          padding: const EdgeInsets.only(bottom: 6),
                          child: Text(
                            p.name.trim().isNotEmpty ? '${p.name} (${p.code})' : p.code,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                      )
                      .toList(),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _effectivePermissions(BuildContext context, List<AdminUserPermission> perms) {
    if (perms.isEmpty) {
      return Text(
        AppLocalizations.of(context)!.noPermissionsListed,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
      );
    }
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Column(
          children: perms
              .map(
                (p) => ListTile(
                  dense: true,
                  title: Text(p.name.trim().isNotEmpty ? p.name : p.code),
                  subtitle: Text(p.code, style: Theme.of(context).textTheme.labelSmall),
                ),
              )
              .toList(),
        ),
      ),
    );
  }

  Widget _entityList(BuildContext context, AppLocalizations loc, List<AdminEntityPermissionRow> rows) {
    if (rows.isEmpty) {
      return Text(
        loc.noEntitiesAssigned,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
      );
    }
    return Card(
      margin: EdgeInsets.zero,
      child: Column(
        children: rows
            .map(
              (e) => ListTile(
                dense: true,
                title: Text(
                  e.entityName?.trim().isNotEmpty == true
                      ? e.entityName!
                      : '${_formatEntityType(e.entityType)} #${e.entityId}',
                ),
                subtitle: Text(
                  '${_formatEntityType(e.entityType)} · ID ${e.entityId}',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ),
            )
            .toList(),
      ),
    );
  }

  String _formatEntityType(String raw) {
    if (raw.isEmpty) return raw;
    return raw.replaceAll('_', ' ');
  }
}
