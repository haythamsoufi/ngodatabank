import 'package:flutter/material.dart';
import '../models/shared/user.dart';
import '../utils/avatar_initials.dart';
import 'profile_leading_avatar.dart';
import '../utils/constants.dart';
import '../utils/theme_extensions.dart';
import '../utils/ios_constants.dart';

/// Rounded edge on the side that meets the scaffold (opposite the drawer hinge).
ShapeBorder modernDrawerShape(BuildContext context) {
  const r = Radius.circular(AppConstants.radiusXLarge);
  return Directionality.of(context) == TextDirection.rtl
      ? const RoundedRectangleBorder(borderRadius: BorderRadius.only(topLeft: r, bottomLeft: r))
      : const RoundedRectangleBorder(borderRadius: BorderRadius.only(topRight: r, bottomRight: r));
}

/// Top block: title + optional signed-in user row.
class ModernDrawerHeader extends StatelessWidget {
  const ModernDrawerHeader({
    super.key,
    required this.title,
    this.user,
  });

  final String title;
  final User? user;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;

    return Padding(
      padding: const EdgeInsets.fromLTRB(
        IOSSpacing.lg,
        IOSSpacing.md + 4,
        IOSSpacing.lg,
        IOSSpacing.md,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: theme.textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.5,
                  color: cs.onSurface,
                ) ??
                IOSTextStyle.title2(context),
          ),
          if (user != null) ...[
            const SizedBox(height: IOSSpacing.md),
            Builder(
              builder: (context) {
                final u = user!;
                return Row(
                  children: [
                    ProfileLeadingAvatar(
                      initials: avatarInitialsForUser(u),
                      profileColorHex: u.profileColor,
                      size: 44,
                    ),
                    const SizedBox(width: IOSSpacing.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            u.displayName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          if (u.title != null && u.title!.isNotEmpty)
                            Text(
                              u.title!,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.isDarkTheme
                                    ? Colors.white.withValues(alpha: 0.65)
                                    : cs.onSurfaceVariant,
                              ),
                            ),
                        ],
                      ),
                    ),
                  ],
                );
              },
            ),
          ],
        ],
      ),
    );
  }
}

class ModernDrawerSectionTitle extends StatelessWidget {
  const ModernDrawerSectionTitle({
    super.key,
    required this.label,
  });

  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        IOSSpacing.lg,
        IOSSpacing.lg,
        IOSSpacing.lg,
        IOSSpacing.sm,
      ),
      child: Text(
        label,
        style: theme.textTheme.labelLarge?.copyWith(
              fontWeight: FontWeight.w600,
              letterSpacing: 1.2,
              color: theme.colorScheme.onSurfaceVariant,
            ) ??
            IOSTextStyle.footnote(context).copyWith(
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.5,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
      ),
    );
  }
}

/// One navigation row: soft icon tile, label, chevron.
class ModernDrawerTile extends StatelessWidget {
  const ModernDrawerTile({
    super.key,
    required this.icon,
    required this.title,
    required this.onTap,
    this.showChevron = true,
    this.iconBackgroundColor,
    this.iconColor,
  });

  final IconData icon;
  final String title;
  final VoidCallback onTap;
  final bool showChevron;
  final Color? iconBackgroundColor;
  final Color? iconColor;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final bg = iconBackgroundColor ?? cs.primary.withValues(alpha: theme.isDarkTheme ? 0.22 : 0.12);
    // Use [ThemeColors.navyIconColor]: in dark mode [ColorScheme.primary] stays brand navy and
    // reads as muddy on drawer surfaces; light mode matches primary (IFRC navy).
    final fg = iconColor ?? context.navyIconColor;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
          splashColor: cs.primary.withValues(alpha: 0.12),
          highlightColor: cs.primary.withValues(alpha: 0.06),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
            child: Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: bg,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  alignment: Alignment.center,
                  child: Icon(icon, color: fg, size: 22),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Text(
                    title,
                    style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w500,
                        ) ??
                        IOSTextStyle.body(context),
                  ),
                ),
                if (showChevron)
                  Icon(
                    Icons.chevron_right_rounded,
                    color: cs.onSurfaceVariant.withValues(alpha: 0.45),
                    size: 22,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
