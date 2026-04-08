import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/shared/notification_provider.dart';
import '../providers/shared/auth_provider.dart';
import '../providers/shared/tab_customization_provider.dart';
import '../utils/constants.dart';
import '../utils/theme_extensions.dart';
import '../utils/navigation_helper.dart';
import '../l10n/app_localizations.dart';
import 'tab_customization_dialog.dart';

class AppBottomNavigationBar extends StatelessWidget {
  /// Pass as [currentIndex] when no tab should appear selected.
  static const int noTabSelected = -1;

  /// Settings **page** index on [MainNavigationScreen] PageView (always 4).
  /// Not the bottom bar slot when AI is shown; use [navIndexFromPageIndex] for highlights.
  static const int settingsTabIndex = 4;

  /// Bottom bar index for the AI tab when [chatbotEnabled] is true.
  static const int aiChatNavIndex = 3;

  /// Bottom bar slot for the Admin/Analysis tab (shifts right when AI is shown).
  static int adminTabNavIndex({required bool chatbotEnabled}) =>
      chatbotEnabled ? 4 : 3;

  /// Converts a PageView page index to the corresponding bottom-nav highlight
  /// index. AI chat occupies its own PageView slot (index 3 when enabled), so
  /// nav index == page index — this is an identity function.
  static int navIndexFromPageIndex(
    int pageIndex, {
    required bool chatbotEnabled,
  }) =>
      pageIndex;

  /// Converts a bottom-nav tap index to the corresponding PageView page index.
  /// AI chat is now a real PageView page, so nav index == page index — identity.
  /// Never returns -1 (AI chat is a valid page).
  static int pageIndexFromNavIndex(
    int navIndex, {
    required bool chatbotEnabled,
  }) =>
      navIndex;

  final int currentIndex;
  final Function(int)? onTap;
  final bool? isFocalPoint;
  final bool useDefaultNavigation;

  /// When `null`, uses [AuthProvider] `user.chatbotEnabled`.
  final bool? chatbotEnabled;

  /// When non-null the bar renders exactly these tabs (customization-aware).
  /// Pass `null` to fall back to the built-in role-based layout.
  final List<TabDefinition>? visibleTabs;

  /// When `true`, long-pressing the bar opens the tab customization dialog.
  final bool enableCustomization;

  const AppBottomNavigationBar({
    super.key,
    required this.currentIndex,
    this.onTap,
    this.isFocalPoint,
    this.useDefaultNavigation = true,
    this.chatbotEnabled,
    this.visibleTabs,
    this.enableCustomization = false,
  });

  bool _effectiveChatbot(BuildContext context) {
    if (chatbotEnabled != null) return chatbotEnabled!;
    return Provider.of<AuthProvider>(context).user?.chatbotEnabled ?? false;
  }

  void _handleTap(BuildContext context, int index) {
    if (onTap != null) {
      onTap!(index);
    } else if (useDefaultNavigation) {
      final c = _effectiveChatbot(context);
      // AI chat is now a PageView page — navigate to it like any other tab.
      final pageIndex = pageIndexFromNavIndex(index, chatbotEnabled: c);
      NavigationHelper.navigateToMainTab(context, pageIndex);
    }
  }

  bool _isAdmin(BuildContext context) {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    return authProvider.user?.isAdmin ?? false;
  }

  bool _isAuthenticated(BuildContext context) {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    return authProvider.isAuthenticated;
  }

  bool _isFocalPoint(BuildContext context) {
    if (isFocalPoint != null) return isFocalPoint!;
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    return authProvider.user?.isFocalPoint ?? false;
  }

  @override
  Widget build(BuildContext context) {
    // ── Customized path ─────────────────────────────────────────────────────
    if (visibleTabs != null && visibleTabs!.isNotEmpty) {
      return _buildCustomized(context, visibleTabs!);
    }
    // ── Legacy / hardcoded path (admin sub-screens, etc.) ───────────────────
    return _buildLegacy(context);
  }

  // =========================================================================
  // Customized layout — driven by [visibleTabs]
  // =========================================================================

  Widget _buildCustomized(BuildContext context, List<TabDefinition> tabs) {
    final int itemCount = tabs.length;
    final int selectedTabIndex = currentIndex < 0
        ? -1
        : (currentIndex >= itemCount ? itemCount - 1 : currentIndex);

    final l10n = AppLocalizations.of(context)!;

    return _barShell(
      context: context,
      enableCustomization: enableCustomization,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          for (int i = 0; i < tabs.length; i++)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: i,
                selectedTabIndex: selectedTabIndex,
                icon: tabs[i].icon,
                activeIcon: tabs[i].activeIcon,
                label: tabs[i].getLabel(l10n),
                showBadge: tabs[i].showBadge,
                onTap: () => _handleTap(context, i),
              ),
            ),
        ],
      ),
    );
  }

  // =========================================================================
  // Legacy layout — hardcoded per role (unchanged logic)
  // =========================================================================

  Widget _buildLegacy(BuildContext context) {
    final isAdmin = _isAdmin(context);
    final isAuthenticated = _isAuthenticated(context);
    final isFocalPoint = _isFocalPoint(context);
    final c = _effectiveChatbot(context);

    // When chatbot is enabled, every index after the AI slot (3) shifts right by 1.
    final int shiftedIdx = c ? 4 : 3;
    final int settingsIdx = c ? 5 : 4;

    // Tab layout:
    // Admin:          Notifications(0) Dashboard(1) Home(2) [AI(3)] Admin(3/4)
    // Auth non-admin: Resources/Notifs(0) Dashboard(1) Home(2) [AI(3)] Analysis(3/4) Settings(4/5)
    // Non-auth:       Resources(0) Indicators(1) Home(2) [AI(3)] Analysis(3/4) Settings(4/5)
    final int itemCount = (isAdmin ? 4 : 5) + (c ? 1 : 0);

    // Negative currentIndex → no tab highlighted (e.g. login overlay).
    // Do not coerce to 0 — that would incorrectly highlight the first tab.
    final int selectedTabIndex = currentIndex < 0
        ? -1
        : (currentIndex >= itemCount ? itemCount - 1 : currentIndex);

    final l10n = AppLocalizations.of(context)!;

    // The AI tab is identical in both admin and non-admin layouts — defined once here.
    Widget aiTab() => Flexible(
          flex: 1,
          child: _buildNavItem(
            context: context,
            index: aiChatNavIndex,
            selectedTabIndex: selectedTabIndex,
            icon: Icons.smart_toy_outlined,
            activeIcon: Icons.smart_toy,
            label: l10n.chatbot,
            showBadge: false,
            onTap: () => _handleTap(context, aiChatNavIndex),
          ),
        );

    return _barShell(
      context: context,
      enableCustomization: enableCustomization,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          if (isAdmin) ...[
            // Notifications (index 0) — admin only
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: 0,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.notifications_outlined,
                activeIcon: Icons.notifications,
                label: l10n.notifications,
                showBadge: true,
                onTap: () => _handleTap(context, 0),
              ),
            ),
            // Dashboard (index 1)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: 1,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.dashboard_outlined,
                activeIcon: Icons.dashboard,
                label: l10n.dashboard,
                showBadge: false,
                onTap: () => _handleTap(context, 1),
              ),
            ),
            // Home (index 2)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: 2,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.home_outlined,
                activeIcon: Icons.home,
                label: l10n.home,
                showBadge: false,
                onTap: () => _handleTap(context, 2),
              ),
            ),
            if (c) aiTab(),
            // Admin hub (index shifts when AI is shown)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: shiftedIdx,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.admin_panel_settings_outlined,
                activeIcon: Icons.admin_panel_settings,
                label: l10n.admin,
                showBadge: false,
                onTap: () => _handleTap(context, shiftedIdx),
              ),
            ),
          ] else ...[
            // Focal points see Notifications; other authenticated users see Resources.
            if (isAuthenticated)
              Flexible(
                flex: 1,
                child: _buildNavItem(
                  context: context,
                  index: 0,
                  selectedTabIndex: selectedTabIndex,
                  icon: isFocalPoint
                      ? Icons.notifications_outlined
                      : Icons.folder_outlined,
                  activeIcon:
                      isFocalPoint ? Icons.notifications : Icons.folder,
                  label: isFocalPoint ? l10n.notifications : l10n.resources,
                  showBadge: isFocalPoint,
                  onTap: () => _handleTap(context, 0),
                ),
              ),
            // Indicators — only for non-authenticated users (index 1)
            if (!isAuthenticated)
              Flexible(
                flex: 1,
                child: _buildNavItem(
                  context: context,
                  index: 1,
                  selectedTabIndex: selectedTabIndex,
                  icon: Icons.library_books_outlined,
                  activeIcon: Icons.library_books,
                  label: l10n.indicators,
                  showBadge: false,
                  onTap: () => _handleTap(context, 1),
                ),
              ),
            // Dashboard (auth) / Resources (non-auth) — centre slot
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: isAuthenticated ? 1 : 0,
                selectedTabIndex: selectedTabIndex,
                icon: isAuthenticated
                    ? Icons.dashboard_outlined
                    : Icons.folder_outlined,
                activeIcon:
                    isAuthenticated ? Icons.dashboard : Icons.folder,
                label: isAuthenticated ? l10n.dashboard : l10n.resources,
                showBadge: false,
                onTap: () => _handleTap(context, isAuthenticated ? 1 : 0),
              ),
            ),
            // Home (index 2)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: 2,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.home_outlined,
                activeIcon: Icons.home,
                label: l10n.home,
                showBadge: false,
                onTap: () => _handleTap(context, 2),
              ),
            ),
            if (c) aiTab(),
            // Disaggregation Analysis (index shifts when AI is shown)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: shiftedIdx,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.analytics_outlined,
                activeIcon: Icons.analytics,
                label: l10n.analysis,
                showBadge: false,
                onTap: () => _handleTap(context, shiftedIdx),
              ),
            ),
            // Settings (index shifts when AI is shown)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: settingsIdx,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.settings_outlined,
                activeIcon: Icons.settings,
                label: l10n.settings,
                showBadge: false,
                onTap: () => _handleTap(context, settingsIdx),
              ),
            ),
          ],
        ],
      ),
    );
  }

  // =========================================================================
  // Shared shell (border, safe area, optional long-press)
  // =========================================================================

  Widget _barShell({
    required BuildContext context,
    required bool enableCustomization,
    required Widget child,
  }) {
    Widget bar = Container(
      decoration: BoxDecoration(
        color: context.surfaceColor,
        border: Border(
          top: BorderSide(
            color: context.borderColor,
            width: 0.5,
          ),
        ),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: 58,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
            child: child,
          ),
        ),
      ),
    );

    if (enableCustomization) {
      bar = GestureDetector(
        onLongPress: () => TabCustomizationDialog.show(context),
        child: bar,
      );
    }

    return bar;
  }

  // =========================================================================
  // Individual nav item
  // =========================================================================

  Widget _buildNavItem({
    required BuildContext context,
    required int index,
    required int selectedTabIndex,
    required IconData icon,
    required IconData activeIcon,
    required String label,
    /// When true, wraps the icon in a [Consumer<NotificationProvider>] badge.
    required bool showBadge,
    required VoidCallback onTap,
  }) {
    final isSelected = selectedTabIndex >= 0 && selectedTabIndex == index;
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final primary = cs.primary;

    // Dark mode: pure primary (#011E41) on ~#1E1E1E bar — edges disappear.
    // Lighten the fill and add a hairline border so the pill reads clearly.
    final Color iconFg;
    final Color selectedPillColor;
    final BoxBorder? selectedPillBorder;
    if (isSelected) {
      if (context.isDarkTheme) {
        iconFg = cs.onPrimary;
        selectedPillColor = Color.alphaBlend(
          Colors.white.withValues(alpha: 0.34),
          primary,
        );
        selectedPillBorder = Border.all(
          color: Colors.white.withValues(alpha: 0.45),
          width: 1,
        );
      } else {
        iconFg = primary;
        selectedPillColor = primary.withValues(alpha: 0.12);
        selectedPillBorder = null;
      }
    } else {
      iconFg = context.iconColor
          .withValues(alpha: context.isDarkTheme ? 0.72 : 0.55);
      selectedPillColor = Colors.transparent;
      selectedPillBorder = null;
    }

    Widget iconChild;
    if (showBadge) {
      iconChild = Consumer<NotificationProvider>(
        builder: (context, provider, child) {
          return Stack(
            clipBehavior: Clip.none,
            alignment: Alignment.center,
            children: [
              Icon(
                isSelected ? activeIcon : icon,
                size: 24,
                color: iconFg,
              ),
              if (provider.unreadCount > 0)
                Positioned(
                  right: -6,
                  top: -6,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 4, vertical: 2),
                    decoration: BoxDecoration(
                      color: Color(AppConstants.ifrcRed),
                      shape: BoxShape.circle,
                    ),
                    constraints: const BoxConstraints(
                      minWidth: 16,
                      minHeight: 16,
                    ),
                    child: Center(
                      child: Text(
                        provider.unreadCount > 9
                            ? '9+'
                            : '${provider.unreadCount}',
                        style: TextStyle(
                          color: theme.colorScheme.onPrimary,
                          fontWeight: FontWeight.bold,
                          fontSize: 10,
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          );
        },
      );
    } else {
      iconChild = Icon(
        isSelected ? activeIcon : icon,
        size: 24,
        color: iconFg,
      );
    }

    return Semantics(
      label: label,
      button: true,
      selected: isSelected,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
          splashColor: context.isDarkTheme && isSelected
              ? Colors.white.withValues(alpha: 0.18)
              : primary.withValues(alpha: 0.12),
          highlightColor: context.isDarkTheme && isSelected
              ? Colors.white.withValues(alpha: 0.1)
              : primary.withValues(alpha: 0.06),
          child: SizedBox.expand(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                AnimatedScale(
                  scale: isSelected ? 1.0 : 0.94,
                  duration: AppConstants.animationFast,
                  curve: Curves.easeOutCubic,
                  child: AnimatedContainer(
                    duration: AppConstants.animationFast,
                    curve: Curves.easeOutCubic,
                    padding: const EdgeInsets.symmetric(
                        horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color:
                          isSelected ? selectedPillColor : Colors.transparent,
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusLarge),
                      border: isSelected ? selectedPillBorder : null,
                    ),
                    child: iconChild,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
