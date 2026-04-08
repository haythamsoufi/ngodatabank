import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../models/shared/ai_chat_launch_args.dart';
import '../../providers/shared/auth_provider.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';

/// Glass-style AI ask card.
///
/// Tapping it opens [_ChatSearchOverlay] via a transparent [PageRoute].
/// While the overlay is open the card fades out, creating a smooth visual
/// handoff. When the overlay closes the card fades back in.
class LandingAiEntryCard extends StatefulWidget {
  final AppLocalizations l10n;

  /// No longer used — kept so call-sites need no change.
  final ScrollController? scrollController;

  const LandingAiEntryCard({
    super.key,
    required this.l10n,
    this.scrollController,
  });

  @override
  State<LandingAiEntryCard> createState() => _LandingAiEntryCardState();
}

class _LandingAiEntryCardState extends State<LandingAiEntryCard> {
  bool _overlayOpen = false;

  Future<void> _openOverlay() async {
    HapticFeedback.lightImpact();
    setState(() => _overlayOpen = true);

    // Capture the result via a closure because PageRouteBuilder's pop value
    // isn't surfaced by Navigator.push<void> when opaque: false.
    String? result;

    await Navigator.of(context, rootNavigator: true).push<void>(
      PageRouteBuilder<void>(
        opaque: false,
        barrierColor: Colors.transparent,
        // Zero route-level duration — we run our own AnimationController.
        transitionDuration: Duration.zero,
        reverseTransitionDuration: Duration.zero,
        pageBuilder: (ctx, _, _) => _ChatSearchOverlay(
          l10n: widget.l10n,
          onDismiss: () => Navigator.of(ctx, rootNavigator: true).pop(),
          onSubmit: (t) {
            result = t;
            Navigator.of(ctx, rootNavigator: true).pop();
          },
        ),
        transitionsBuilder: (_, _, _, child) => child,
      ),
    );

    if (mounted) setState(() => _overlayOpen = false);
    if (result == null || !mounted) return;

    final trimmed = result!.trim();
    final chatbot =
        Provider.of<AuthProvider>(context, listen: false).user?.chatbotEnabled ??
            false;
    Navigator.of(context).pushNamed(
      AppRoutes.aiChat,
      arguments: AiChatLaunchArgs(
        bottomNavTabIndex: chatbot ? 3 : 2,
        startNewConversation: true,
        initialText: trimmed.isEmpty ? null : trimmed,
        sendImmediately: trimmed.isNotEmpty,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final glass = isDark
        ? Colors.white.withValues(alpha: 0.08)
        : Colors.white.withValues(alpha: 0.14);
    final border = Colors.white.withValues(alpha: 0.22);

    return AnimatedOpacity(
      opacity: _overlayOpen ? 0.0 : 1.0,
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOut,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: GestureDetector(
          onTap: _overlayOpen ? null : _openOverlay,
          behavior: HitTestBehavior.opaque,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: glass,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: border),
                ),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        widget.l10n.homeLandingChatTitle,
                        style: theme.textTheme.titleSmall?.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        widget.l10n.homeLandingChatDescription,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: Colors.white.withValues(alpha: 0.85),
                          height: 1.25,
                        ),
                      ),
                      const SizedBox(height: 8),
                      // Visual-only pill — tap is handled by the card GestureDetector.
                      IgnorePointer(
                        child: _PillHint(l10n: widget.l10n, theme: theme),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _PillHint extends StatelessWidget {
  final AppLocalizations l10n;
  final ThemeData theme;

  const _PillHint({required this.l10n, required this.theme});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(4, 4, 4, 4),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.95),
        borderRadius: BorderRadius.circular(26),
        border: Border.all(color: theme.colorScheme.outline),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(10, 9, 4, 9),
              child: Text(
                l10n.homeLandingAskPlaceholder,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: Colors.grey.shade500, fontSize: 14),
              ),
            ),
          ),
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: Color(AppConstants.ifrcRed),
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.arrow_forward_rounded,
              color: Colors.white,
              size: 20,
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Overlay
// ---------------------------------------------------------------------------

/// Full-screen transparent overlay with its own [AnimationController].
///
/// The route itself has zero transition duration so it appears instantly.
/// The [AnimationController] drives the slide-in and backdrop fade, giving
/// us full control without depending on the route's animation object.
///
/// [PopScope] intercepts the back button to run the dismiss animation before
/// actually popping the route.
class _ChatSearchOverlay extends StatefulWidget {
  final AppLocalizations l10n;
  final VoidCallback onDismiss;
  final ValueChanged<String> onSubmit;

  const _ChatSearchOverlay({
    required this.l10n,
    required this.onDismiss,
    required this.onSubmit,
  });

  @override
  State<_ChatSearchOverlay> createState() => _ChatSearchOverlayState();
}

class _ChatSearchOverlayState extends State<_ChatSearchOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _anim;
  late final Animation<Offset> _slide;
  late final Animation<double> _fade;

  final _textController = TextEditingController();
  final _focusNode = FocusNode();

  bool _dismissing = false;

  void _onFocusChange() {
    if (mounted) setState(() {});
  }

  @override
  void initState() {
    super.initState();
    _focusNode.addListener(_onFocusChange);
    _anim = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 300),
    );
    _slide = Tween<Offset>(
      begin: const Offset(0, -1),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _anim, curve: Curves.easeOutCubic));
    _fade = Tween<double>(begin: 0, end: 0.52)
        .animate(CurvedAnimation(parent: _anim, curve: Curves.easeOut));

    // Kick the animation immediately.
    _anim.forward();

    // Request focus after the first frame so the keyboard animates in.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _focusNode.requestFocus();
    });
  }

  @override
  void dispose() {
    _focusNode.removeListener(_onFocusChange);
    _anim.dispose();
    _textController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  Future<void> _dismiss() async {
    if (_dismissing) return;
    _dismissing = true;
    _focusNode.unfocus();
    await _anim.reverse();
    if (mounted) widget.onDismiss();
  }

  void _submit() {
    FocusManager.instance.primaryFocus?.unfocus();
    widget.onSubmit(_textController.text);
  }

  @override
  Widget build(BuildContext context) {
    final mq = MediaQuery.of(context);
    final appBarBottom = mq.padding.top + kToolbarHeight;
    final theme = Theme.of(context);

    return PopScope(
      // Intercept back button so we can animate out before popping.
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _dismiss();
      },
      child: Stack(
        fit: StackFit.expand,
        children: [
          // Dimmed backdrop — tap to dismiss.
          AnimatedBuilder(
            animation: _fade,
            builder: (_, _) => GestureDetector(
              onTap: _dismiss,
              behavior: HitTestBehavior.opaque,
              child: ColoredBox(
                color: Colors.black.withValues(alpha: _fade.value),
              ),
            ),
          ),

          // Search bar slides in from above the AppBar.
          Positioned(
            top: appBarBottom,
            left: 0,
            right: 0,
            child: SlideTransition(
              position: _slide,
              child: _buildBar(theme),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBar(ThemeData theme) {
    final focused = _focusNode.hasFocus;
    final accent = Color(AppConstants.ifrcRed);
    final headerOnSurface = theme.colorScheme.onSurface;
    final headerMuted = theme.colorScheme.onSurface.withValues(alpha: 0.72);

    return Material(
      color: theme.scaffoldBackgroundColor,
      elevation: 4,
      shadowColor: Colors.black.withValues(alpha: 0.18),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(8, 8, 16, 8),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOutCubic,
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
          decoration: BoxDecoration(
            color: theme.colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: focused ? accent : theme.colorScheme.outline,
              width: focused ? 2 : 1,
            ),
            boxShadow: focused
                ? [
                    BoxShadow(
                      color: accent.withValues(alpha: 0.22),
                      blurRadius: 12,
                      offset: const Offset(0, 4),
                    ),
                  ]
                : null,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                widget.l10n.homeLandingChatTitle,
                style: theme.textTheme.titleSmall?.copyWith(
                  color: headerOnSurface,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                widget.l10n.homeLandingChatDescription,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: headerMuted,
                  height: 1.25,
                ),
              ),
              const SizedBox(height: 10),
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.fromLTRB(4, 4, 4, 4),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.surface,
                        borderRadius: BorderRadius.circular(26),
                        border: Border.all(
                          color: focused
                              ? accent.withValues(alpha: 0.45)
                              : theme.colorScheme.outline,
                        ),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _textController,
                              focusNode: _focusNode,
                              onSubmitted: focused ? null : (_) => _submit(),
                              minLines: 1,
                              maxLines: focused ? 6 : 1,
                              keyboardType: focused
                                  ? TextInputType.multiline
                                  : TextInputType.text,
                              textInputAction: focused
                                  ? TextInputAction.newline
                                  : TextInputAction.done,
                              textAlignVertical: TextAlignVertical.center,
                              style: theme.textTheme.bodyMedium
                                  ?.copyWith(fontSize: 14, height: 1.35),
                              cursorColor: accent,
                              decoration: InputDecoration(
                                hintText: widget.l10n.homeLandingAskPlaceholder,
                                hintStyle: TextStyle(
                                  color: Colors.grey.shade500,
                                  fontSize: 14,
                                ),
                                filled: true,
                                fillColor: Colors.transparent,
                                isDense: true,
                                border: InputBorder.none,
                                enabledBorder: InputBorder.none,
                                focusedBorder: InputBorder.none,
                                disabledBorder: InputBorder.none,
                                errorBorder: InputBorder.none,
                                focusedErrorBorder: InputBorder.none,
                                contentPadding: const EdgeInsets.fromLTRB(
                                  12,
                                  9,
                                  4,
                                  9,
                                ),
                              ),
                            ),
                          ),
                          Material(
                            color: accent,
                            shape: const CircleBorder(),
                            clipBehavior: Clip.antiAlias,
                            child: InkWell(
                              onTap: _submit,
                              customBorder: const CircleBorder(),
                              child: const SizedBox(
                                width: 36,
                                height: 36,
                                child: Icon(
                                  Icons.arrow_forward_rounded,
                                  color: Colors.white,
                                  size: 18,
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
