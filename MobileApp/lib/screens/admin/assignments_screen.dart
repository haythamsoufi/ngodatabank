import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:provider/provider.dart';
import '../../providers/admin/assignments_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../models/admin/admin_assignment.dart';
import '../../utils/theme_extensions.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/error_state.dart';
import '../../widgets/ios_dialog.dart';
import '../../l10n/app_localizations.dart';

class AssignmentsScreen extends StatefulWidget {
  const AssignmentsScreen({super.key});

  @override
  State<AssignmentsScreen> createState() => _AssignmentsScreenState();
}

class _AssignmentsScreenState extends State<AssignmentsScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadAssignments();
    });
  }

  Future<void> _loadAssignments() async {
    await Provider.of<AssignmentsProvider>(context, listen: false)
        .loadAssignments();
  }

  Future<void> _handleDelete(AdminAssignment assignment) async {
    final localizations = AppLocalizations.of(context)!;
    final confirmed = await IOSAlertDialog.show<bool>(
      context: context,
      title: localizations.deleteAssignment,
      message: localizations.deleteAssignmentConfirmMessage,
      actions: [
        cupertino.CupertinoDialogAction(
          onPressed: () => Navigator.of(context).pop(false),
          child: Text(localizations.cancel),
        ),
        cupertino.CupertinoDialogAction(
          isDestructiveAction: true,
          onPressed: () => Navigator.of(context).pop(true),
          child: Text(localizations.delete),
        ),
      ],
    );

    if (confirmed == true) {
      if (!mounted) return;
      final provider = Provider.of<AssignmentsProvider>(context, listen: false);
      final success = await provider.deleteAssignment(assignment.id);

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(success
                ? localizations.assignmentDeletedSuccessfully
                : localizations.failedToDeleteAssignment),
            backgroundColor: success ? Colors.green : Colors.red,
          ),
        );

        if (success) {
          _loadAssignments();
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final chatbot = context.watch<AuthProvider>().user?.chatbotEnabled ?? false;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.manageAssignments,
        actions: const [
        ],
      ),
      body: Consumer<AssignmentsProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading) {
            return AppLoadingIndicator(message: localizations.loadingAssignments);
          }

          if (provider.error != null) {
            return AppErrorState(
              message: provider.error,
              onRetry: () => provider.loadAssignments(),
            );
          }

          if (provider.assignments.isEmpty) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.assignment_outlined,
                    size: 56,
                    color: context.textSecondaryColor,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    localizations.noAssignmentsFound,
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: theme.colorScheme.onSurface,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    localizations.getStartedByCreating,
                    style: TextStyle(
                      fontSize: 14,
                      color: context.textSecondaryColor,
                    ),
                  ),
                ],
              ),
            );
          }

          return RefreshIndicator(
            onRefresh: () async => _loadAssignments(),
            color: Color(AppConstants.ifrcRed),
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: provider.assignments.length,
              itemBuilder: (context, index) {
                final assignment = provider.assignments[index];
                return Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                    side: BorderSide(
                      color: context.borderColor,
                      width: 1,
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    assignment.periodName,
                                    style: theme.textTheme.titleMedium?.copyWith(
                                      fontWeight: FontWeight.w600,
                                      color: theme.colorScheme.onSurface,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    assignment.templateName ??
                                        localizations.templateMissing,
                                    style: theme.textTheme.bodyMedium?.copyWith(
                                      color: theme.colorScheme.onSurfaceVariant,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  icon: const Icon(Icons.delete, size: 20),
                                  color: Colors.red,
                                  onPressed: () => _handleDelete(assignment),
                                  tooltip: localizations.delete,
                                ),
                              ],
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                      ],
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
      bottomNavigationBar: AppBottomNavigationBar(
        currentIndex: AppBottomNavigationBar.adminTabNavIndex(
          chatbotEnabled: chatbot,
        ),
        chatbotEnabled: chatbot,
        onTap: (index) {
          Navigator.of(context).popUntil((route) {
            return route.isFirst || route.settings.name == AppRoutes.dashboard;
          });
        },
      ),
    );
  }
}
