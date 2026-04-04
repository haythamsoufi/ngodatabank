import 'package:flutter/material.dart';
import 'constants.dart';

class AppTheme {
  static ThemeData lightTheme({Locale? locale}) =>
      _buildTheme(Brightness.light, locale);

  static ThemeData darkTheme({Locale? locale}) =>
      _buildTheme(Brightness.dark, locale);

  static ThemeData _buildTheme(Brightness brightness, Locale? locale) {
    final isDark = brightness == Brightness.dark;
    final fontFamily = locale?.languageCode == 'ar' ? 'Tajawal' : 'Montserrat';

    TextStyle getTextStyle({
      required double fontSize,
      required FontWeight fontWeight,
      required Color color,
      double? letterSpacing,
      double? height,
    }) {
      return TextStyle(
        fontFamily: fontFamily,
        fontSize: fontSize,
        fontWeight: fontWeight,
        color: color,
        letterSpacing: letterSpacing,
        height: height,
      );
    }

    final primary = Color(AppConstants.ifrcNavy);
    final secondary = Color(AppConstants.ifrcRed);
    final colorScheme = ColorScheme.fromSeed(
      seedColor: primary,
      primary: primary,
      secondary: secondary,
      error: const Color(AppConstants.errorColor),
      surface: isDark
          ? const Color(AppConstants.themeSurfaceDark)
          : const Color(AppConstants.backgroundColor),
      onPrimary: Colors.white,
      onSecondary: Colors.white,
      onSurface: isDark
          ? Colors.white
          : const Color(AppConstants.textColor),
      brightness: brightness,
    );

    final textPrimary =
        isDark ? Colors.white : const Color(AppConstants.textColor);
    final bodySmallColor = isDark
        ? Colors.white.withOpacity(0.7)
        : const Color(AppConstants.textSecondary);
    final bodyMediumColor =
        isDark ? Colors.white.withOpacity(0.9) : textPrimary;

    final inputRadius = BorderRadius.circular(AppConstants.radiusMedium);

    return ThemeData(
      useMaterial3: true,
      visualDensity: VisualDensity.adaptivePlatformDensity,
      materialTapTargetSize: MaterialTapTargetSize.padded,
      // Subtle page motion (keeps iOS cupertino-style push; others get a soft fade-up).
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: <TargetPlatform, PageTransitionsBuilder>{
          TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.android: FadeUpwardsPageTransitionsBuilder(),
          TargetPlatform.fuchsia: FadeUpwardsPageTransitionsBuilder(),
          TargetPlatform.linux: FadeUpwardsPageTransitionsBuilder(),
          TargetPlatform.windows: FadeUpwardsPageTransitionsBuilder(),
        },
      ),
      splashFactory: InkSparkle.splashFactory,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: isDark
          ? const Color(AppConstants.themeScaffoldDark)
          : const Color(AppConstants.themeScaffoldLight),
      appBarTheme: AppBarTheme(
        backgroundColor: isDark
            ? const Color(AppConstants.themeSurfaceDark)
            : Colors.white,
        foregroundColor: isDark ? Colors.white : Colors.black,
        elevation: 0,
        centerTitle: false,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: getTextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: isDark ? Colors.white : Colors.black,
          letterSpacing: -0.5,
        ),
        iconTheme: IconThemeData(color: isDark ? Colors.white : Colors.black),
        shadowColor: Colors.black.withOpacity(isDark ? 0.3 : 0.1),
        scrolledUnderElevation: 1,
      ),
      textTheme: TextTheme(
        displayLarge: getTextStyle(
          fontSize: 32,
          fontWeight: FontWeight.bold,
          color: textPrimary,
          letterSpacing: -1,
        ),
        displayMedium: getTextStyle(
          fontSize: 28,
          fontWeight: FontWeight.bold,
          color: textPrimary,
          letterSpacing: -0.5,
        ),
        displaySmall: getTextStyle(
          fontSize: 24,
          fontWeight: FontWeight.w600,
          color: textPrimary,
          letterSpacing: -0.5,
        ),
        headlineMedium: getTextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: textPrimary,
          letterSpacing: -0.3,
        ),
        titleLarge: getTextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: textPrimary,
        ),
        titleMedium: getTextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: textPrimary,
        ),
        bodyLarge: getTextStyle(
          fontSize: 16,
          fontWeight: FontWeight.normal,
          color: textPrimary,
          height: 1.5,
        ),
        bodyMedium: getTextStyle(
          fontSize: 14,
          fontWeight: FontWeight.normal,
          color: bodyMediumColor,
          height: 1.5,
        ),
        bodySmall: getTextStyle(
          fontSize: 12,
          fontWeight: FontWeight.normal,
          color: bodySmallColor,
          height: 1.4,
        ),
        labelLarge: getTextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: textPrimary,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primary,
          foregroundColor: Colors.white,
          elevation: 0,
          padding: const EdgeInsets.symmetric(
            horizontal: AppConstants.paddingLarge,
            vertical: AppConstants.paddingMedium + 2,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
          ),
          textStyle: getTextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: Colors.white,
            letterSpacing: 0.2,
          ),
        ).copyWith(
          elevation: WidgetStateProperty.resolveWith<double>(
            (Set<WidgetState> states) {
              if (states.contains(WidgetState.disabled)) return 0;
              if (states.contains(WidgetState.pressed)) return 2;
              return 1;
            },
          ),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: const Color(AppConstants.themeFilledButtonBlue),
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(
            horizontal: AppConstants.paddingLarge,
            vertical: AppConstants.paddingMedium + 2,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
          ),
          elevation: 0,
          textStyle: getTextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: Colors.white,
            letterSpacing: 0.2,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: isDark
              ? Colors.white.withOpacity(0.9)
              : primary,
          padding: const EdgeInsets.symmetric(
            horizontal: AppConstants.paddingLarge,
            vertical: AppConstants.paddingMedium + 2,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
          ),
          side: BorderSide(
            color: isDark ? Colors.white.withOpacity(0.5) : primary,
            width: 1.5,
          ),
          textStyle: getTextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: isDark ? Colors.white.withOpacity(0.9) : primary,
            letterSpacing: 0.2,
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: isDark
            ? const Color(AppConstants.themeElevatedSurfaceDark)
            : const Color(AppConstants.themeInputFillLight),
        border: OutlineInputBorder(
          borderRadius: inputRadius,
          borderSide: BorderSide(
            color: isDark
                ? Colors.white.withOpacity(0.12)
                : const Color(AppConstants.themeInputBorderLight),
            width: 1,
          ),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: inputRadius,
          borderSide: BorderSide(
            color: isDark
                ? Colors.white.withOpacity(0.12)
                : const Color(AppConstants.themeInputBorderLight),
            width: 1,
          ),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: inputRadius,
          borderSide: BorderSide(
            color: isDark
                ? Colors.white.withOpacity(0.7)
                : const Color(AppConstants.themeInputBorderFocusedLight),
            width: isDark ? 1.5 : 2,
          ),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: inputRadius,
          borderSide: const BorderSide(
            color: Color(AppConstants.errorColor),
            width: 1,
          ),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: inputRadius,
          borderSide: const BorderSide(
            color: Color(AppConstants.errorColor),
            width: 1.5,
          ),
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 12,
          vertical: 12,
        ),
        labelStyle: getTextStyle(
          fontSize: 12,
          fontWeight: FontWeight.normal,
          color: isDark
              ? Colors.white.withOpacity(0.7)
              : const Color(AppConstants.themeInputLabelLight),
        ),
      ),
      cardTheme: CardThemeData(
        elevation: isDark ? 0 : 1,
        shadowColor: isDark
            ? Colors.black.withOpacity(0.35)
            : Colors.black.withOpacity(0.06),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        ),
        margin: EdgeInsets.zero,
        color: isDark
            ? const Color(AppConstants.themeSurfaceDark)
            : Colors.white,
        surfaceTintColor: Colors.transparent,
      ),
      dividerTheme: DividerThemeData(
        color: isDark
            ? Colors.white.withOpacity(0.15)
            : const Color(AppConstants.borderColor),
        thickness: 1,
        space: 1,
      ),
      chipTheme: ChipThemeData(
        backgroundColor: isDark
            ? const Color(AppConstants.themeElevatedSurfaceDark)
            : colorScheme.surfaceContainerLow,
        selectedColor: primary.withOpacity(isDark ? 0.3 : 0.1),
        labelStyle: getTextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          color: textPrimary,
        ),
        padding: const EdgeInsets.symmetric(
          horizontal: 12,
          vertical: 8,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        ),
      ),
      listTileTheme: ListTileThemeData(
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppConstants.paddingMedium,
          vertical: AppConstants.paddingSmall,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
        ),
      ),
      floatingActionButtonTheme: FloatingActionButtonThemeData(
        backgroundColor: secondary,
        foregroundColor: colorScheme.onSecondary,
        elevation: 4,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        elevation: 2,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        ),
        backgroundColor: isDark
            ? const Color(AppConstants.themeElevatedSurfaceDark)
            : const Color(0xFF1F2937),
        contentTextStyle: getTextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w500,
          color: Colors.white,
        ),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        showDragHandle: true,
        dragHandleColor: isDark
            ? Colors.white.withOpacity(0.35)
            : Colors.black.withOpacity(0.25),
        backgroundColor: isDark
            ? const Color(AppConstants.themeSurfaceDark)
            : Colors.white,
        surfaceTintColor: Colors.transparent,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(AppConstants.radiusXLarge),
          ),
        ),
      ),
      dialogTheme: DialogThemeData(
        elevation: 3,
        backgroundColor: isDark
            ? const Color(AppConstants.themeSurfaceDark)
            : Colors.white,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusXLarge),
        ),
      ),
      popupMenuTheme: PopupMenuThemeData(
        elevation: 3,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
        ),
      ),
    );
  }
}
