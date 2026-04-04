import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:provider/provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../models/shared/user.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/ios_constants.dart';
import '../../widgets/admin_user_banner.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/ios_list_tile.dart';
import '../../l10n/app_localizations.dart';

class AdminScreen extends StatelessWidget {
  final bool showBottomNav;

  const AdminScreen({
    super.key,
    this.showBottomNav = false,
  });

  bool _isAdmin(User? user) {
    if (user == null) return false;
    return user.role == 'admin' || user.role == 'system_manager';
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthProvider>(
      builder: (context, authProvider, child) {
        final user = authProvider.user;

        final localizations = AppLocalizations.of(context)!;

        // Only show admin screen for admins
        if (!_isAdmin(user)) {
          return Scaffold(
            appBar: AppAppBar(
              title: localizations.adminPanel,
            ),
            body: Center(
              child: Text(localizations.accessDenied),
            ),
          );
        }

        final theme = Theme.of(context);
        return Scaffold(
          appBar: AppAppBar(
            title: localizations.adminPanel,
          ),
          backgroundColor: theme.scaffoldBackgroundColor,
          body: Container(
            color: IOSColors.getGroupedBackground(context),
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(
                horizontal: IOSSpacing.md,
                vertical: IOSSpacing.md,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  AdminUserBanner(user: user),

                  SizedBox(height: IOSSpacing.lg),
                  // General Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.general,
                    icon: Icons.dashboard_rounded,
                    color: const Color(AppConstants.semanticAdminHubBlue),
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.people_rounded,
                        title: localizations.manageUsers,
                        route: AppRoutes.users,
                        iconColor: const Color(AppConstants.semanticAdminHubBlue),
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.description_rounded,
                        title: localizations.documentManagement,
                        route: AppRoutes.documentManagement,
                        iconColor: const Color(AppConstants.semanticAdminHubBlue),
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.translate_rounded,
                        title: localizations.translationManagement,
                        route: AppRoutes.translationManagement,
                        iconColor: const Color(AppConstants.semanticAdminHubBlue),
                      ),
                    ],
                  ),

                  SizedBox(height: IOSSpacing.md),

                  // Form & Data Management Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.formDataManagement,
                    icon: Icons.article_rounded,
                    color: const Color(AppConstants.semanticAdminHubPurple),
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.article_rounded,
                        title: localizations.manageTemplates,
                        route: AppRoutes.templates,
                        iconColor: const Color(AppConstants.semanticAdminHubPurple),
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.assignment_rounded,
                        title: localizations.manageAssignments,
                        route: AppRoutes.assignments,
                        iconColor: const Color(AppConstants.semanticAdminHubPurple),
                      ),
                    ],
                  ),

                  SizedBox(height: IOSSpacing.md),

                  // Website Management Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.frontendManagement,
                    icon: Icons.folder_open_rounded,
                    color: const Color(AppConstants.semanticAdminHubAmber),
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.folder_open_rounded,
                        title: localizations.manageResources,
                        route: AppRoutes.resourcesManagement,
                        iconColor: const Color(AppConstants.semanticAdminHubAmber),
                      ),
                    ],
                  ),

                  SizedBox(height: IOSSpacing.md),

                  // Reference Data Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.referenceData,
                    icon: Icons.account_tree_rounded,
                    color: const Color(AppConstants.semanticAdminHubRed),
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.account_tree_rounded,
                        title: localizations.organizationalStructure,
                        route: AppRoutes.organizationalStructure,
                        iconColor: const Color(AppConstants.semanticAdminHubRed),
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.storage_rounded,
                        title: localizations.indicatorBank,
                        route: AppRoutes.indicatorBankAdmin,
                        iconColor: const Color(AppConstants.semanticAdminHubRed),
                      ),
                    ],
                  ),

                  SizedBox(height: IOSSpacing.md),

                  // Analytics & Monitoring Section
                  _buildSectionCard(
                    context: context,
                    title: localizations.analyticsMonitoring,
                    icon: Icons.bar_chart_rounded,
                    color: const Color(AppConstants.semanticAdminHubCyan),
                    children: [
                      _buildMenuItem(
                        context: context,
                        icon: Icons.bar_chart_rounded,
                        title: localizations.userAnalytics,
                        route: AppRoutes.userAnalytics,
                        iconColor: const Color(AppConstants.semanticAdminHubCyan),
                      ),
                      _buildMenuItem(
                        context: context,
                        icon: Icons.history_rounded,
                        title: localizations.auditTrail,
                        route: AppRoutes.auditTrail,
                        iconColor: const Color(AppConstants.semanticAdminHubCyan),
                      ),
                    ],
                  ),

                  SizedBox(height: IOSSpacing.xl),
                ],
              ),
            ),
          ),
          bottomNavigationBar: showBottomNav
              ? AppBottomNavigationBar(
                  currentIndex:
                      -1, // -1 means no tab is active (Admin screen is on top)
                  // onTap is optional - if not provided, uses NavigationHelper.navigateToMainTab by default
                )
              : null,
        );
      },
    );
  }

  Widget _buildSectionCard({
    required BuildContext context,
    required String title,
    required IconData icon,
    required Color color,
    required List<Widget> children,
  }) {
    final theme = Theme.of(context);
    return IOSGroupedList(
      header: Row(
        children: [
          Container(
            padding: EdgeInsets.all(IOSSpacing.sm),
            decoration: BoxDecoration(
              color: color.withOpacity(0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              icon,
              color: color,
              size: 16,
            ),
          ),
          SizedBox(width: IOSSpacing.sm),
          Text(
            title,
            style: IOSTextStyle.footnote(context).copyWith(
              fontWeight: FontWeight.w600,
              color: theme.colorScheme.onSurface.withOpacity(0.6),
            ),
          ),
        ],
      ),
      margin: EdgeInsets.zero,
      children: children,
    );
  }

  Widget _buildMenuItem({
    required BuildContext context,
    required IconData icon,
    required String title,
    String? route,
    String? webviewRoute,
    required Color iconColor,
  }) {
    final theme = Theme.of(context);
    return IOSListTile(
      leading: Container(
        padding: EdgeInsets.all(IOSSpacing.sm + 2),
        decoration: BoxDecoration(
          color: iconColor.withOpacity(0.1),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Icon(
          icon,
          color: iconColor,
          size: 18,
        ),
      ),
      title: Text(
        title,
        style: IOSTextStyle.callout(context).copyWith(
          fontWeight: FontWeight.w500,
          letterSpacing: -0.2,
        ),
      ),
      trailing: Icon(
        cupertino.CupertinoIcons.chevron_right,
        color: theme.colorScheme.onSurface.withOpacity(0.3),
        size: 13,
      ),
      onTap: () {
        if (route != null) {
          Navigator.of(context).pushNamed(route);
        } else if (webviewRoute != null) {
          Navigator.of(context).pushNamed(
            AppRoutes.webview,
            arguments: webviewRoute,
          );
        }
      },
    );
  }
}
