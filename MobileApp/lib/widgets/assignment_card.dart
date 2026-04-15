import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:intl/intl.dart';

import '../l10n/app_localizations.dart';
import '../models/shared/assignment.dart';
import '../utils/constants.dart';
import '../utils/ios_constants.dart';
import '../utils/theme_extensions.dart';
import 'shared/elevated_list_card.dart';

class AssignmentCard extends StatelessWidget {
  final Assignment assignment;
  final VoidCallback onTap;
  final VoidCallback? onEnterData;
  final bool showEnterDataButton;
  final String? enterDataButtonText;

  const AssignmentCard({
    super.key,
    required this.assignment,
    required this.onTap,
    this.onEnterData,
    this.showEnterDataButton = false,
    this.enterDataButtonText,
  });

  @override
  Widget build(BuildContext context) {
    return ElevatedListCard(
      child: FlipListCard(
        frontBuilder: (ctx) => _buildFrontFace(ctx),
        backBuilder: (ctx) => _buildBackFace(ctx),
        footerBuilder: (ctx, flip) {
          if (flip.value < 0.5) return const SizedBox.shrink();
          // Front already has Enter data; back footer only for open-from-back (e.g. past rows).
          if (showEnterDataButton && onEnterData != null) {
            return const SizedBox.shrink();
          }
          return _buildBackFooterActions(ctx);
        },
      ),
    );
  }

  /// Enter data below the flip ([ListCardFooterActions] matches session logs).
  Widget _buildBackFooterActions(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;

    return ListCardFooterActions(
      child: _enterDataActionButton(
        context,
        onPressed: onTap,
        label: enterDataButtonText ?? localizations.enterData,
      ),
    );
  }

  /// Blue compact [TextButton.icon] used on front (when applicable) and back footer.
  Widget _enterDataActionButton(
    BuildContext context, {
    required VoidCallback onPressed,
    required String label,
  }) {
    final blue = IOSColors.getSystemBlue(context);
    final buttonStyle = TextButton.styleFrom(
      foregroundColor: blue,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      minimumSize: Size.zero,
      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      visualDensity: VisualDensity.compact,
      alignment: AlignmentDirectional.centerStart,
    );
    return TextButton.icon(
      onPressed: onPressed,
      icon: Icon(Icons.edit_note_rounded, size: 18, color: blue),
      label: Text(label),
      style: buttonStyle,
    );
  }

  Color _getCompletionColor(BuildContext context, double completionRate) {
    if (completionRate >= 100) {
      return const Color(AppConstants.successColor);
    } else if (completionRate >= 80) {
      return const Color(AppConstants.successColor);
    } else if (completionRate >= 50) {
      return const Color(AppConstants.warningColor);
    } else if (completionRate >= 25) {
      return const Color(AppConstants.warningColor);
    } else {
      return const Color(AppConstants.errorColor);
    }
  }

  String _formatDate(BuildContext context, DateTime date) {
    final locale = Localizations.localeOf(context);
    if (locale.languageCode == 'ar') {
      DateFormat.useNativeDigitsByDefaultFor('ar', false);
    }
    final dateFormat = DateFormat('MMM d, y', locale.languageCode);
    String formatted = dateFormat.format(date);
    formatted = formatted
        .replaceAll('٠', '0')
        .replaceAll('١', '1')
        .replaceAll('٢', '2')
        .replaceAll('٣', '3')
        .replaceAll('٤', '4')
        .replaceAll('٥', '5')
        .replaceAll('٦', '6')
        .replaceAll('٧', '7')
        .replaceAll('٨', '8')
        .replaceAll('٩', '9');
    return formatted;
  }

  String _formatDateTime(BuildContext context, DateTime date) {
    final locale = Localizations.localeOf(context);
    if (locale.languageCode == 'ar') {
      DateFormat.useNativeDigitsByDefaultFor('ar', false);
    }
    final dateFormat = DateFormat('MMM d, y · HH:mm', locale.languageCode);
    String formatted = dateFormat.format(date.toLocal());
    formatted = formatted
        .replaceAll('٠', '0')
        .replaceAll('١', '1')
        .replaceAll('٢', '2')
        .replaceAll('٣', '3')
        .replaceAll('٤', '4')
        .replaceAll('٥', '5')
        .replaceAll('٦', '6')
        .replaceAll('٧', '7')
        .replaceAll('٨', '8')
        .replaceAll('٩', '9');
    return formatted;
  }

  Widget _assignmentBackDetail(
    BuildContext context, {
    required String label,
    required String value,
    IconData? icon,
    Color? valueColor,
    FontWeight? valueWeight,
  }) {
    if (value.isEmpty) {
      return const SizedBox.shrink();
    }
    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.55);
    final valueStyle = IOSTextStyle.footnote(context).copyWith(
      color: valueColor ?? theme.colorScheme.onSurface.withValues(alpha: 0.9),
      fontWeight: valueWeight ?? FontWeight.w500,
      height: 1.3,
    );
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (icon != null) ...[
            Icon(
              icon,
              size: 15,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
            ),
            const SizedBox(width: 8),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: IOSTextStyle.caption2(context).copyWith(
                    color: muted,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.2,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  value,
                  style: valueStyle,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFrontFace(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final textTheme = theme.textTheme;
    final titleText = assignment.periodName != null &&
            assignment.periodName!.isNotEmpty
        ? '${assignment.templateName ?? assignment.name} - ${assignment.periodName}'
        : assignment.templateName ?? assignment.name;

    final dueStr = assignment.dueDate != null
        ? _formatDate(context, assignment.dueDate!)
        : localizations.noDueDate;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              Icons.assignment_rounded,
              size: 18,
              color: scheme.onSurfaceVariant,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                titleText,
                style: textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                  height: 1.25,
                ),
              ),
            ),
            const SizedBox(width: 4),
            _StatusBadge(status: assignment.status),
          ],
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 6,
          children: [
            ListMetricChip(
              label: localizations.completion,
              value: '${assignment.completionRate.toStringAsFixed(0)}%',
            ),
            ListMetricChip(
              label: localizations.dueDate,
              value: dueStr,
            ),
            if (assignment.isOverdue)
              ListMetricChip(
                label: '',
                value: localizations.overdue,
              ),
          ],
        ),
        ListCardFooterActions(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              if (showEnterDataButton && onEnterData != null)
                Expanded(
                  child: Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: _enterDataActionButton(
                      context,
                      onPressed: onEnterData!,
                      label: enterDataButtonText ?? localizations.enterData,
                    ),
                  ),
                )
              else
                const Spacer(),
              IconButton(
                onPressed: FlipListCardScope.of(context).toggleFlip,
                icon: Icon(
                  Icons.flip_outlined,
                  size: 20,
                  color: scheme.onSurfaceVariant,
                ),
                style: IconButton.styleFrom(
                  padding: const EdgeInsets.all(4),
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  visualDensity: VisualDensity.compact,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildBackFace(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final isOverdue = assignment.isOverdue;
    final completionColor =
        _getCompletionColor(context, assignment.completionRate);

    String submittedLine = '';
    final submitter = assignment.submittedByUserName?.trim();
    if (submitter != null && submitter.isNotEmpty) {
      if (assignment.submittedAt != null) {
        submittedLine =
            '$submitter\n${localizations.atDatetime(_formatDateTime(context, assignment.submittedAt!))}';
      } else {
        submittedLine = submitter;
      }
    } else if (assignment.submittedAt != null) {
      submittedLine = _formatDateTime(context, assignment.submittedAt!);
    }

    String contributorsValue = '';
    if (assignment.contributorNames.isNotEmpty) {
      contributorsValue = assignment.contributorNames.join(', ');
    }

    final publicLines = <String>[];
    if (assignment.isPublic) {
      publicLines.add(localizations.publicLinkEnabled);
    }
    if (assignment.publicSubmissionCount != null &&
        assignment.publicSubmissionCount! > 0) {
      publicLines.add(
        localizations.receivedCountSubmissionsUsingPublicLink(
          assignment.publicSubmissionCount!,
        ),
      );
      if (assignment.latestPublicSubmissionAt != null) {
        publicLines.add(
          localizations.latestDatetime(
            _formatDateTime(context, assignment.latestPublicSubmissionAt!),
          ),
        );
      }
    }
    final publicBlock = publicLines.join('\n');

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  '${assignment.completionRate.toStringAsFixed(0)}%',
                  style: IOSTextStyle.title3(context).copyWith(
                    color: completionColor,
                  ),
                ),
                const SizedBox(width: 6),
                Text(
                  localizations.completion,
                  style: IOSTextStyle.footnote(context),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Container(
              height: 3,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(1.5),
                color: theme.dividerColor.withValues(alpha: 0.2),
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(1.5),
                child: LinearProgressIndicator(
                  value: assignment.completionRate / 100,
                  minHeight: 3,
                  backgroundColor: Colors.transparent,
                  valueColor: AlwaysStoppedAnimation<Color>(
                    completionColor,
                  ),
                ),
              ),
            ),
          ],
        ),
        if (assignment.assignedAt != null)
          _assignmentBackDetail(
            context,
            label: localizations.assignmentAssignedDate,
            value: _formatDateTime(context, assignment.assignedAt!),
            icon: cupertino.CupertinoIcons.calendar,
          ),
        if (assignment.statusTimestamp != null)
          _assignmentBackDetail(
            context,
            label: localizations.assignmentStatusUpdated,
            value: _formatDateTime(context, assignment.statusTimestamp!),
            icon: cupertino.CupertinoIcons.time,
          ),
        if (assignment.dueDate != null)
          _assignmentBackDetail(
            context,
            label: localizations.dueDate,
            value: _formatDate(context, assignment.dueDate!),
            icon: cupertino.CupertinoIcons.flag,
            valueColor: isOverdue
                ? const Color(AppConstants.errorColor)
                : null,
            valueWeight: isOverdue ? FontWeight.w700 : FontWeight.w500,
          ),
        if (submittedLine.isNotEmpty)
          _assignmentBackDetail(
            context,
            label: localizations.assignmentSubmittedBy,
            value: submittedLine,
            icon: cupertino.CupertinoIcons.paperplane,
          ),
        if (assignment.approvedByUserName != null &&
            assignment.approvedByUserName!.trim().isNotEmpty)
          _assignmentBackDetail(
            context,
            label: localizations.assignmentApprovedBy,
            value: assignment.approvedByUserName!.trim(),
            icon: cupertino.CupertinoIcons.check_mark_circled,
          ),
        if (contributorsValue.isNotEmpty)
          _assignmentBackDetail(
            context,
            label: localizations.contributors,
            value: contributorsValue,
            icon: cupertino.CupertinoIcons.person_2,
          )
        else if (assignment.lastModifiedUserName != null &&
            assignment.lastModifiedUserName!.trim().isNotEmpty)
          _assignmentBackDetail(
            context,
            label: localizations.lastModifiedBy,
            value: assignment.lastModifiedUserName!.trim(),
            icon: cupertino.CupertinoIcons.person,
          ),
        if (publicBlock.isNotEmpty)
          _assignmentBackDetail(
            context,
            label: localizations.submittedThroughPublicLink,
            value: publicBlock,
            icon: cupertino.CupertinoIcons.globe,
            valueColor: IOSColors.getSystemBlue(context),
            valueWeight: FontWeight.w600,
          ),
      ],
    );
  }
}

class _StatusBadge extends StatelessWidget {
  final String status;

  const _StatusBadge({required this.status});

  Color _getStatusColor(BuildContext context) {
    switch (status.toLowerCase().trim()) {
      case 'approved':
        return const Color(AppConstants.successColor);
      case 'submitted':
        return const Color(0xFF0D9488);
      case 'in progress':
        return context.navyTextColor;
      case 'requires revision':
        return const Color(AppConstants.errorColor);
      case 'pending':
        return const Color(AppConstants.warningColor);
      default:
        return const Color(AppConstants.textSecondary);
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final scheme = Theme.of(context).colorScheme;
    final statusColor = _getStatusColor(context);
    final localizedStatus = localizations.localizeStatus(status);

    final fill = Color.alphaBlend(
      statusColor.withValues(alpha: 0.26),
      scheme.surface,
    );

    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: 8,
        vertical: 3,
      ),
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: statusColor.withValues(alpha: 0.55),
          width: 1,
        ),
      ),
      child: Text(
        localizedStatus,
        style: TextStyle(
          color: statusColor,
          fontSize: 11,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.2,
        ),
      ),
    );
  }
}
