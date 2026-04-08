import 'dart:ui';

import 'package:flutter/material.dart';
import '../../utils/constants.dart';
import 'landing_hero_slideshow_background.dart';

/// Collapsing hero with gradient mesh, title and subtitle.
///
/// Optional [footer] (e.g. AI entry card) and [quickPrompts] are laid out inside
/// [FlexibleSpaceBar] so they sit on the same gradient with prompts **below** the
/// footer. Using [SliverAppBar.bottom] for the footer would paint it over
/// [flexibleSpace] and clip the mesh to a solid [backgroundColor] band.
class LandingHeroSliver extends StatefulWidget {
  final String title;
  final String description;
  final double expandedHeight;
  /// Placed on the hero gradient above [quickPrompts] (e.g. AI entry card).
  final Widget? footer;
  /// Placed on the hero gradient below [footer] (e.g. quick prompt chips).
  final Widget? quickPrompts;

  const LandingHeroSliver({
    super.key,
    required this.title,
    required this.description,
    this.expandedHeight = 188,
    this.footer,
    this.quickPrompts,
  });

  /// Reserved height for [footer] (card + overlap into the hero).
  static const double footerPreferredHeight = 212;

  /// Extra flex height when [quickPrompts] is non-null (list + padding).
  static const double quickPromptsSlotHeight = 58;

  @override
  State<LandingHeroSliver> createState() => _LandingHeroSliverState();
}

class _LandingHeroSliverState extends State<LandingHeroSliver>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeIn;
  late Animation<Offset> _slide;

  static const List<Color> _meshColors = [
    Color(0xFF0F172A),
    Color(0xFF1E3A5F),
    Color(0xFF7F1D1D),
    Color(0xFF0F172A),
  ];

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );
    _fadeIn = CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic);
    _slide = Tween<Offset>(
      begin: const Offset(0, 0.06),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final top = MediaQuery.paddingOf(context).top;
    final footerExtra =
        widget.footer != null ? LandingHeroSliver.footerPreferredHeight : 0.0;
    final promptsExtra = widget.quickPrompts != null
        ? LandingHeroSliver.quickPromptsSlotHeight
        : 0.0;
    final h = widget.expandedHeight + top + footerExtra + promptsExtra;

    return SliverAppBar(
      pinned: false,
      floating: false,
      stretch: true,
      clipBehavior: Clip.none,
      toolbarHeight: 0,
      expandedHeight: h,
      automaticallyImplyLeading: false,
      backgroundColor: _meshColors.first,
      flexibleSpace: FlexibleSpaceBar(
        stretchModes: const [
          StretchMode.zoomBackground,
        ],
        background: Stack(
          fit: StackFit.expand,
          children: [
            const LandingHeroSlideshowBackground(
              fallback: _MeshGradient(colors: _meshColors),
            ),
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.black.withValues(alpha: 0.45),
                    Colors.black.withValues(alpha: 0.78),
                  ],
                ),
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SizedBox(height: top + 12),
                Expanded(
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 20),
                      child: FadeTransition(
                        opacity: _fadeIn,
                        child: SlideTransition(
                          position: _slide,
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Text(
                                widget.title,
                                textAlign: TextAlign.center,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: Theme.of(context)
                                    .textTheme
                                    .headlineSmall
                                    ?.copyWith(
                                      color: Colors.white,
                                      fontWeight: FontWeight.w800,
                                      height: 1.2,
                                      letterSpacing: -0.4,
                                    ),
                              ),
                              const SizedBox(height: 8),
                              Text(
                                widget.description,
                                textAlign: TextAlign.center,
                                maxLines: 4,
                                overflow: TextOverflow.ellipsis,
                                style: Theme.of(context)
                                    .textTheme
                                    .bodyMedium
                                    ?.copyWith(
                                      color: Colors.white.withValues(alpha: 0.9),
                                      height: 1.35,
                                    ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
                if (widget.footer != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 20),
                    child: widget.footer!,
                  ),
                if (widget.quickPrompts != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(0, 0, 0, 12),
                    child: widget.quickPrompts!,
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _MeshGradient extends StatelessWidget {
  final List<Color> colors;

  const _MeshGradient({required this.colors});

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: colors,
            ),
          ),
        ),
        Positioned(
          right: -80,
          top: -40,
          child: _Blob(color: Color(AppConstants.ifrcRed).withValues(alpha: 0.35)),
        ),
        Positioned(
          left: -60,
          bottom: 20,
          child: _Blob(color: Colors.blue.shade900.withValues(alpha: 0.4)),
        ),
      ],
    );
  }
}

class _Blob extends StatelessWidget {
  final Color color;

  const _Blob({required this.color});

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: ImageFiltered(
        imageFilter: ImageFilter.blur(sigmaX: 60, sigmaY: 60),
        child: Container(
          width: 200,
          height: 200,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color,
          ),
        ),
      ),
    );
  }
}
