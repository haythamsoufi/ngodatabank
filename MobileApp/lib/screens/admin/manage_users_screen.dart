import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../models/admin/admin_user_list_item.dart';
import '../../models/shared/user.dart';
import '../../providers/admin/manage_users_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../utils/ios_constants.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import 'admin_user_detail_screen.dart';

/// Read-only user directory for admins. Editing remains on the web backoffice only.
class ManageUsersScreen extends StatefulWidget {
  const ManageUsersScreen({super.key});

  @override
  State<ManageUsersScreen> createState() => _ManageUsersScreenState();
}

class _ManageUsersScreenState extends State<ManageUsersScreen> {
  final _searchController = TextEditingController();
  String _query = '';

  bool _isAdmin(User? user) {
    if (user == null) return false;
    return user.role == 'admin' || user.role == 'system_manager';
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (_isAdmin(context.read<AuthProvider>().user)) {
        context.read<ManageUsersProvider>().loadUsers();
      }
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _onRefresh() async {
    await context.read<ManageUsersProvider>().loadUsers();
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final auth = context.watch<AuthProvider>();
    final user = auth.user;

    if (!_isAdmin(user)) {
      return Scaffold(
        appBar: AppAppBar(title: localizations.manageUsers),
        body: Center(child: Text(localizations.accessDenied)),
        bottomNavigationBar: AppBottomNavigationBar(currentIndex: -1),
      );
    }

    final provider = context.watch<ManageUsersProvider>();
    final q = _query.trim().toLowerCase();
    final filtered = q.isEmpty
        ? provider.users
        : provider.users.where((u) {
            final name = u.displayName.toLowerCase();
            final email = u.email.toLowerCase();
            final roles = u.rolesLabel.toLowerCase();
            final countries = u.countries
                .map((c) => '${c.name ?? ''} ${c.code ?? ''}'.toLowerCase())
                .join(' ');
            return name.contains(q) ||
                email.contains(q) ||
                roles.contains(q) ||
                countries.contains(q);
          }).toList();

    return Scaffold(
      appBar: AppAppBar(title: localizations.manageUsers),
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Text(
              localizations.usersDirectoryReadOnly,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: localizations.searchUsers,
                prefixIcon: const Icon(Icons.search, size: 22),
                suffixIcon: _query.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _searchController.clear();
                          setState(() => _query = '');
                        },
                      )
                    : null,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                isDense: true,
              ),
              onChanged: (v) => setState(() => _query = v),
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: RefreshIndicator(
              onRefresh: _onRefresh,
              child: _buildBody(context, provider, filtered, localizations),
            ),
          ),
        ],
      ),
      bottomNavigationBar: AppBottomNavigationBar(currentIndex: -1),
    );
  }

  Widget _buildBody(
    BuildContext context,
    ManageUsersProvider provider,
    List<AdminUserListItem> filtered,
    AppLocalizations localizations,
  ) {
    if (provider.isLoading && provider.users.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          SizedBox(
            height: MediaQuery.of(context).size.height * 0.35,
            child: const Center(child: CircularProgressIndicator()),
          ),
          Center(child: Text(localizations.loadingUsers)),
        ],
      );
    }

    if (provider.error != null && provider.users.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(24),
        children: [
          Icon(Icons.lock_outline, size: 48, color: Theme.of(context).colorScheme.error),
          const SizedBox(height: 16),
          Text(
            provider.error!,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyLarge,
          ),
          const SizedBox(height: 24),
          Center(
            child: FilledButton.icon(
              onPressed: _onRefresh,
              icon: const Icon(Icons.refresh),
              label: Text(localizations.retry),
            ),
          ),
        ],
      );
    }

    if (filtered.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          SizedBox(
            height: MediaQuery.of(context).size.height * 0.25,
          ),
          Center(
            child: Text(
              localizations.noUsersFound,
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
        ],
      );
    }

    return ListView.separated(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
      itemCount: filtered.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, i) {
        final u = filtered[i];
        return ListTile(
          contentPadding: const EdgeInsets.symmetric(vertical: 8),
          onTap: () {
            Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (ctx) => AdminUserDetailScreen(summary: u),
              ),
            );
          },
          title: Text(
            u.displayName,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          subtitle: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 2),
              Text(
                u.email,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
              if (u.title != null && u.title!.trim().isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(
                  u.title!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                ),
              ],
              const SizedBox(height: 8),
              _UserDirectoryRoleChips(user: u, localizations: localizations),
            ],
          ),
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.chevron_right, color: Theme.of(context).colorScheme.outline),
              const SizedBox(width: 4),
              u.active
                  ? Icon(Icons.check_circle_outline, color: IOSColors.systemGreen, size: 22)
                  : Icon(Icons.cancel_outlined, color: Theme.of(context).colorScheme.outline, size: 22),
            ],
          ),
        );
      },
    );
  }
}

/// Role summary row: primary type (Admin / Focal Point), system manager, then grouped chips.
class _UserDirectoryRoleChips extends StatelessWidget {
  const _UserDirectoryRoleChips({
    required this.user,
    required this.localizations,
  });

  final AdminUserListItem user;
  final AppLocalizations localizations;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final assignment = user.assignmentRoles;
    final adminSys = user.adminAndSystemRoles;
    final other = user.otherRoles;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            Chip(
              visualDensity: VisualDensity.compact,
              label: Text(
                user.computedRoleType == 'admin'
                    ? localizations.adminRole
                    : localizations.focalPointRole,
              ),
              backgroundColor: user.computedRoleType == 'admin'
                  ? scheme.primaryContainer.withValues(alpha: 0.55)
                  : scheme.secondaryContainer.withValues(alpha: 0.5),
            ),
            if (user.isSystemManager)
              Chip(
                visualDensity: VisualDensity.compact,
                label: Text(localizations.systemManagerRole),
                backgroundColor: scheme.errorContainer.withValues(alpha: 0.55),
              ),
          ],
        ),
        if (assignment.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(
            localizations.userDirAssignmentRoles,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 4),
          Wrap(
            spacing: 4,
            runSpacing: 4,
            children: assignment
                .map(
                  (r) => Chip(
                    visualDensity: VisualDensity.compact,
                    materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    label: Text(
                      (r.name != null && r.name!.trim().isNotEmpty) ? r.name! : r.code,
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                    backgroundColor: IOSColors.systemGreen.withValues(alpha: 0.16),
                  ),
                )
                .toList(),
          ),
        ],
        if (adminSys.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(
            localizations.userDirAdminRoles,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 4),
          Wrap(
            spacing: 4,
            runSpacing: 4,
            children: adminSys
                .map(
                  (r) => Chip(
                    visualDensity: VisualDensity.compact,
                    materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    label: Text(
                      (r.name != null && r.name!.trim().isNotEmpty) ? r.name! : r.code,
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                    backgroundColor: r.code == 'system_manager'
                        ? scheme.errorContainer.withValues(alpha: 0.45)
                        : scheme.primaryContainer.withValues(alpha: 0.4),
                  ),
                )
                .toList(),
          ),
        ],
        if (other.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(
            localizations.userDirOtherRoles,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 4),
          Wrap(
            spacing: 4,
            runSpacing: 4,
            children: other
                .map(
                  (r) => Chip(
                    visualDensity: VisualDensity.compact,
                    materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    label: Text(
                      (r.name != null && r.name!.trim().isNotEmpty) ? r.name! : r.code,
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                  ),
                )
                .toList(),
          ),
        ],
        if (user.rbacRoles.isEmpty)
          Text(
            '—',
            style: Theme.of(context).textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant),
          ),
      ],
    );
  }
}
