import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

import '../../models/admin/admin_user_detail.dart';
import '../../models/admin/admin_user_list_item.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';

/// Loads the admin user directory via [GET /admin/api/users] (session auth, `admin.users.view`).
/// Read-only: no mutations from the mobile app.
class ManageUsersProvider with ChangeNotifier {
  final ApiService _api = ApiService();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<AdminUserListItem> _users = [];
  bool _isLoading = false;
  String? _error;

  List<AdminUserListItem> get users => List.unmodifiable(_users);
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadUsers() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get(
            '/admin/api/users',
            useCache: false,
          ),
      context: 'Manage Users',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null) {
      _error = 'Unable to load users. Please try again.';
      _users = [];
      _isLoading = false;
      notifyListeners();
      return;
    }

    if (response.statusCode == 403) {
      _error =
          'You do not have permission to view users. This requires admin user access on the server.';
      _users = [];
      _isLoading = false;
      notifyListeners();
      return;
    }

    if (response.statusCode == 200) {
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic> &&
            decoded['success'] == true &&
            decoded['data'] is List) {
          final list = decoded['data'] as List<dynamic>;
          _users = list
              .whereType<Map<String, dynamic>>()
              .map(AdminUserListItem.fromJson)
              .toList();
          _error = null;
        } else {
          _error = 'Unexpected response from server.';
          _users = [];
        }
      } catch (e, stackTrace) {
        final err = _errorHandler.parseError(
          error: e,
          stackTrace: stackTrace,
          context: 'Parse users list',
        );
        _error = err.getUserMessage();
        _users = [];
      }
    } else {
      final err = _errorHandler.parseError(
        error: Exception('HTTP ${response.statusCode}'),
        response: response,
        context: 'Manage Users',
      );
      _error = err.getUserMessage();
      _users = [];
    }

    _isLoading = false;
    notifyListeners();
  }

  /// Single-user profile (roles, RBAC permissions, entity grants). Does not mutate the list cache.
  Future<AdminUserDetail?> fetchUserDetail(int userId) async {
    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get(
            '/admin/api/users/$userId',
            useCache: false,
          ),
      context: 'User detail',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null || response.statusCode != 200) {
      return null;
    }

    try {
      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String, dynamic>) return null;
      if (decoded['success'] != true) return null;
      final data = decoded['data'];
      if (data is! Map<String, dynamic>) return null;
      return AdminUserDetail.fromJson(data);
    } catch (e, stackTrace) {
      _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Parse user detail',
      );
      return null;
    }
  }
}
