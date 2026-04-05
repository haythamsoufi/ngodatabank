import 'package:flutter/foundation.dart';
import 'dart:convert';
import 'dart:async';
import 'package:http/http.dart' as http;
import '../../services/api_service.dart';
import '../../services/error_handler.dart';

class AdminDashboardProvider with ChangeNotifier {
  final ApiService _api = ApiService();
  final ErrorHandler _errorHandler = ErrorHandler();

  Map<String, dynamic>? _stats;
  bool _isLoading = false;
  String? _error;

  Map<String, dynamic>? get stats => _stats;
  bool get isLoading => _isLoading;
  String? get error => _error;

  // Convenience getters - mapped to API response fields
  int get userCount => _stats?['user_count'] ?? 0;
  int get adminCount =>
      _stats?['admin_count'] ?? 0; // Not provided by API, default to 0
  int get focalPointCount =>
      _stats?['focal_point_count'] ?? 0; // Not provided by API, default to 0
  int get templateCount => _stats?['template_count'] ?? 0;
  int get assignmentCount => _stats?['assignment_count'] ?? 0;
  int get todayLogins => _stats?['today_logins'] ?? 0;
  int get recentLogins => _stats?['recent_logins'] ?? 0;
  int get recentActivities =>
      _stats?['recent_submissions'] ?? 0; // API returns 'recent_submissions'
  int get activeSessions =>
      _stats?['active_users'] ??
      0; // API returns 'active_users', not 'active_sessions'
  int get pendingSubmissions =>
      _stats?['pending_public_submissions_count'] ??
      0; // Not provided by API, default to 0
  int get overdueAssignments =>
      _stats?['overdue_assignments'] ?? 0; // Not provided by API, default to 0
  int get securityAlerts =>
      _stats?['unresolved_security_events'] ??
      0; // Not provided by API, default to 0

  Future<void> loadDashboardStats() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get(
        '/admin/api/dashboard/stats',
        timeout: const Duration(seconds: 30),
      ),
      context: 'Admin Dashboard Stats',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null) {
      _error = 'Unable to load dashboard stats. Please try again.';
      _stats = null;
      _isLoading = false;
      notifyListeners();
      return;
    }

    if (response.statusCode == 200) {
      try {
        final decoded = jsonDecode(response.body);
        // Backoffice returns stats flat at the top level (no nested 'data' key).
        // Accept: {"status":"success","user_count":27,...}
        //   or:  {"status":"success","data":{"user_count":27,...}}
        final bool isSuccess =
            decoded['status'] == 'success' || decoded['success'] == true;
        if (isSuccess) {
          final nested = decoded['data'];
          _stats = Map<String, dynamic>.from(
              nested is Map ? nested : decoded);
          _error = null;
        } else {
          final error = _errorHandler.parseError(
            error: Exception(
                decoded['message'] ?? 'Failed to load dashboard stats'),
            response: response,
            context: 'Admin Dashboard Stats',
          );
          _error = error.getUserMessage();
          _stats = null;
        }
      } catch (e, stackTrace) {
        final error = _errorHandler.parseError(
          error: e,
          stackTrace: stackTrace,
          context: 'Admin Dashboard Stats parsing',
        );
        _error = error.getUserMessage();
        _stats = null;
      }
    } else {
      final error = _errorHandler.parseError(
        error: Exception('HTTP ${response.statusCode}'),
        response: response,
        context: 'Admin Dashboard Stats',
      );
      _error = error.getUserMessage();
      _stats = null;
    }

    _isLoading = false;
    notifyListeners();
  }
}
