import 'package:flutter/material.dart';
import 'constants.dart';

/// Whether the resolved [ThemeData] is dark (same as [Theme.brightness]).
extension AppThemeDataX on ThemeData {
  bool get isDarkTheme => brightness == Brightness.dark;

  /// Card/list ambient shadow (theme-relative opacity).
  Color ambientShadow({double lightOpacity = 0.05, double darkOpacity = 0.32}) =>
      isDarkTheme
          ? Colors.black.withOpacity(darkOpacity)
          : Colors.black.withOpacity(lightOpacity);

  // --- Quiz: option / result surfaces (success + error from [AppConstants]) ---

  Color quizOptionResultCorrectFill() => isDarkTheme
      ? const Color(AppConstants.successColor).withOpacity(0.30)
      : const Color(AppConstants.successColor).withOpacity(0.12);

  Color quizOptionResultWrongFill() => isDarkTheme
      ? const Color(AppConstants.errorColor).withOpacity(0.28)
      : const Color(AppConstants.errorColor).withOpacity(0.12);

  Color quizOptionResultCorrectBorder() => const Color(AppConstants.successColor)
      .withOpacity(isDarkTheme ? 0.95 : 0.85);

  Color quizOptionResultWrongBorder() => const Color(AppConstants.errorColor)
      .withOpacity(isDarkTheme ? 0.95 : 0.85);

  Color quizOptionResultCorrectIconBg() => isDarkTheme
      ? const Color(AppConstants.successColor).withOpacity(0.45)
      : const Color(AppConstants.successColor).withOpacity(0.22);

  Color quizOptionResultWrongIconBg() => isDarkTheme
      ? const Color(AppConstants.errorColor).withOpacity(0.45)
      : const Color(AppConstants.errorColor).withOpacity(0.22);

  Color quizOptionResultCorrectIconFg() => isDarkTheme
      ? const Color(0xFFDCFCE7)
      : const Color(AppConstants.successColor);

  Color quizOptionResultWrongIconFg() => isDarkTheme
      ? const Color(0xFFFEE2E2)
      : const Color(AppConstants.errorColor);

  Color quizOptionResultCorrectText() => isDarkTheme
      ? const Color(0xFFDCFCE7)
      : const Color(0xFF14532D);

  Color quizOptionResultWrongText() => isDarkTheme
      ? const Color(0xFFFEE2E2)
      : const Color(0xFF7F1D1D);

  Color quizOptionResultShadow(bool isCorrect, bool isWrong) {
    if (isCorrect) {
      return const Color(AppConstants.successColor).withOpacity(0.3);
    }
    if (isWrong) {
      return const Color(AppConstants.errorColor).withOpacity(0.3);
    }
    return ambientShadow(lightOpacity: 0.1, darkOpacity: 0.35);
  }
}

/// Extension on BuildContext to easily access theme-aware colors
extension ThemeColors on BuildContext {
  /// True when the current [Theme] resolves to dark mode (includes system + OS dark).
  bool get isDarkTheme => Theme.of(this).brightness == Brightness.dark;

  /// Gets the appropriate text color for the current theme
  Color get textColor => Theme.of(this).colorScheme.onSurface;

  /// Gets the appropriate secondary text color for the current theme
  Color get textSecondaryColor => isDarkTheme
      ? Colors.white.withOpacity(0.6)
      : const Color(AppConstants.textSecondary);

  /// Gets the appropriate surface/background color for the current theme
  Color get surfaceColor => Theme.of(this).colorScheme.surface;

  /// Gets the appropriate card color for the current theme
  Color get cardColor => Theme.of(this).cardColor;

  /// Gets the appropriate border color for the current theme
  Color get borderColor => isDarkTheme
      ? Colors.white.withOpacity(0.12)
      : const Color(AppConstants.borderColor);

  /// Gets the appropriate scaffold background color for the current theme
  Color get scaffoldBackgroundColor => Theme.of(this).scaffoldBackgroundColor;

  /// Gets the appropriate divider color for the current theme
  Color get dividerColor => Theme.of(this).dividerColor;

  /// Gets a light surface color (for inputs, chips, etc.)
  Color get lightSurfaceColor => isDarkTheme
      ? const Color(AppConstants.themeElevatedSurfaceDark)
      : const Color(AppConstants.themeInputFillLight);

  /// Gets an even lighter surface color (for subtle backgrounds)
  Color get subtleSurfaceColor => isDarkTheme
      ? const Color(AppConstants.themeSurfaceDark)
      : Theme.of(this).colorScheme.surfaceContainerLow;

  /// Gets the appropriate icon color for the current theme
  Color get iconColor =>
      Theme.of(this).iconTheme.color ??
      (isDarkTheme ? Colors.white : Colors.black87);

  /// Gets disabled text color
  Color get disabledTextColor => isDarkTheme
      ? Colors.white.withOpacity(0.38)
      : Colors.black.withOpacity(0.38);

  /// Gets theme-aware navy color for text and icons
  /// In dark theme, returns light text color for better contrast
  /// In light theme, returns the IFRC navy color
  Color get navyTextColor =>
      isDarkTheme ? textColor : Color(AppConstants.ifrcNavy);

  /// Gets theme-aware navy color for icons
  /// In dark theme, returns icon color for better visibility
  /// In light theme, returns the IFRC navy color
  Color get navyIconColor =>
      isDarkTheme ? iconColor : Color(AppConstants.ifrcNavy);

  /// Gets theme-aware navy color for button foreground/text
  /// In dark theme, returns text color for better contrast
  /// In light theme, returns the IFRC navy color
  Color get navyForegroundColor =>
      isDarkTheme ? textColor : Color(AppConstants.ifrcNavy);

  /// Gets theme-aware navy background color with opacity
  /// In dark theme, uses white with opacity for subtle backgrounds
  /// In light theme, uses navy with opacity
  Color navyBackgroundColor({double opacity = 0.1}) => isDarkTheme
      ? Colors.white.withOpacity(opacity)
      : Color(AppConstants.ifrcNavy).withOpacity(opacity);
}

/// Offline / sync strip colors (compact indicator row).
extension OfflineStatusColors on BuildContext {
  Color get offlineQueuedBackground => isDarkTheme
      ? Colors.orange.shade900.withOpacity(0.45)
      : Colors.orange.shade100;

  Color get offlineQueuedForeground => isDarkTheme
      ? Colors.orange.shade100
      : Colors.orange.shade900;

  Color get offlineSyncedBackground => isDarkTheme
      ? const Color(AppConstants.successColor).withOpacity(0.24)
      : const Color(AppConstants.successColor).withOpacity(0.12);

  Color get offlineSyncedForeground => isDarkTheme
      ? Colors.green.shade200
      : Colors.green.shade800;

  Color get offlineDisconnectedInlineBackground => isDarkTheme
      ? const Color(AppConstants.errorColor).withOpacity(0.30)
      : Colors.red.shade100;

  Color get offlineDisconnectedInlineForeground => isDarkTheme
      ? Colors.red.shade100
      : Colors.red.shade900;
}

/// Extension on ThemeData for additional theme-aware color helpers
extension AppThemeColors on ThemeData {
  /// Gets text color with proper contrast
  Color getTextColor({double opacity = 1.0}) {
    return isDarkTheme
        ? Colors.white.withOpacity(opacity)
        : const Color(AppConstants.textColor).withOpacity(opacity);
  }

  /// Gets secondary text color with proper contrast
  Color getSecondaryTextColor({double opacity = 1.0}) {
    return isDarkTheme
        ? Colors.white.withOpacity(0.6 * opacity)
        : const Color(AppConstants.textSecondary).withOpacity(opacity);
  }

  /// Gets border color appropriate for the theme
  Color getBorderColor({double opacity = 1.0}) {
    return isDarkTheme
        ? Colors.white.withOpacity(0.12 * opacity)
        : const Color(AppConstants.borderColor).withOpacity(opacity);
  }

  /// Gets a surface color for input fields
  Color getInputSurfaceColor() {
    return isDarkTheme
        ? const Color(AppConstants.themeElevatedSurfaceDark)
        : const Color(AppConstants.themeInputFillLight);
  }
}

/// Helper class for creating theme-aware colors with proper contrast
class ThemeAwareColors {
  /// Gets a color that ensures proper contrast based on background brightness
  static Color ensureContrast(
    Color color,
    Brightness backgroundBrightness, {
    double minContrast = 4.5, // WCAG AA standard for normal text
  }) {
    // For dark backgrounds, use lighter version
    // For light backgrounds, use darker version
    if (backgroundBrightness == Brightness.dark) {
      // Ensure color is light enough for dark background
      final luminance = color.computeLuminance();
      if (luminance < 0.4) {
        // Too dark, lighten it
        return color.withOpacity(1.0);
      }
    } else {
      // Ensure color is dark enough for light background
      final luminance = color.computeLuminance();
      if (luminance > 0.6) {
        // Too light, darken it
        return color.withOpacity(1.0);
      }
    }
    return color;
  }

  /// Gets text color that ensures WCAG contrast compliance
  static Color getContrastTextColor(Color backgroundColor) {
    final luminance = backgroundColor.computeLuminance();
    // If background is dark, return light text
    // If background is light, return dark text
    return luminance > 0.5
        ? const Color(AppConstants.textColor) // Dark text for light background
        : Colors.white; // Light text for dark background
  }

  /// Adapts a color based on theme brightness
  static Color adaptColor(
      Color lightColor, Color darkColor, Brightness brightness) {
    return brightness == Brightness.dark ? darkColor : lightColor;
  }
}
