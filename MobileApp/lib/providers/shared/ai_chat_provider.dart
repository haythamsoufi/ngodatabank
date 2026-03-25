import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:uuid/uuid.dart';

import '../../models/shared/ai_chat.dart';
import '../../services/ai_chat_service.dart';
import '../../services/ai_chat_persistence_service.dart';
import '../../utils/debug_logger.dart';

class AiChatProvider with ChangeNotifier {
  final AiChatService _service = AiChatService();
  final AiChatPersistenceService _persistence = AiChatPersistenceService();
  final Uuid _uuid = const Uuid();

  bool _isLoading = false;
  bool _isStreaming = false;
  String? _error;
  String? _errorType; // 'quota_exceeded' or null
  double? _retryDelay; // seconds
  String? _conversationId;
  String? _failedMessage; // Message that failed due to quota error

  List<AiChatMessage> _messages = [];
  List<AiConversationSummary> _conversations = [];

  WebSocketChannel? _channel;
  StreamSubscription? _wsSub;

  // Prevent overlapping server syncs per conversation
  final Set<String> _syncInFlight = {};

  bool get isLoading => _isLoading;
  bool get isStreaming => _isStreaming;
  String? get error => _error;
  String? get errorType => _errorType;
  double? get retryDelay => _retryDelay;
  String? get conversationId => _conversationId;
  String? get failedMessage => _failedMessage;

  List<AiChatMessage> get messages => List.unmodifiable(_messages);
  List<AiConversationSummary> get conversations => List.unmodifiable(_conversations);

  Future<void> ensureTokenIfLoggedIn({required bool isAuthenticated}) async {
    if (!isAuthenticated) return;
    // Best effort: fetch token only if we don't already have one cached.
    // If it fails, cookie auth may still work for HTTP, but WS benefits from token headers.
    final cached = await _service.getCachedToken();
    if (cached != null && cached.isNotEmpty) return;
    await _service.fetchAndCacheToken();
  }

  Future<void> loadConversations({required bool isAuthenticated}) async {
    if (!isAuthenticated) {
      // Logged-out: show locally cached/offline conversations
      _conversations = await _persistence.getAllConversations();
      _conversations.sort((a, b) {
        final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
        final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
        return bTime.compareTo(aTime);
      });
      notifyListeners();
      return;
    }
    _isLoading = true;
    _error = null;
    notifyListeners();
    try {
      // Load from local DB first (fast)
      _conversations = await _persistence.getAllConversations();
      // Sort by most recent first
      _conversations.sort((a, b) {
        final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
        final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
        return bTime.compareTo(aTime);
      });
      notifyListeners();

      // Then sync from server (if online)
      try {
        final raw = await _service.listConversations();
        final serverConvos = raw.map((e) => AiConversationSummary.fromJson(Map<String, dynamic>.from(e))).toList();

        // Save server conversations to local DB
        for (final convo in serverConvos) {
          await _persistence.saveConversation(convo);
        }

        // Merge: keep local-only conversations that don't exist on server yet
        final byId = <String, AiConversationSummary>{for (final c in serverConvos) c.id: c};
        for (final local in _conversations) {
          if (!byId.containsKey(local.id)) {
            byId[local.id] = local;
          }
        }
        _conversations = byId.values.toList();
        // Sort by most recent first
        _conversations.sort((a, b) {
          final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
          final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
          return bTime.compareTo(aTime);
        });
      } catch (e) {
        DebugLogger.logWarn('AI', 'Failed to sync conversations from server, using local: $e');
        // Keep local conversations if server sync fails
      }
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> openConversation({required bool isAuthenticated, required String conversationId}) async {
    _isLoading = true;
    _error = null;
    notifyListeners();
    try {
      // Load from local DB first (fast)
      _conversationId = conversationId;
      _messages = await _persistence.getConversationMessages(conversationId);
      notifyListeners();

      // Then sync from server (if online)
      if (isAuthenticated) {
        await _syncConversationFromServer(conversationId);
        _messages = await _persistence.getConversationMessages(conversationId);
        notifyListeners();

        // If we have offline-only messages, import them once after login to keep the server conversation consistent.
        await _maybeImportOfflineMessages(conversationId);
      }
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  void startNewConversation() {
    _conversationId = null;
    _messages = [];
    _error = null;
    _errorType = null;
    _retryDelay = null;
    _failedMessage = null;
    notifyListeners();
  }

  /// Ensure we have a stable local conversation UUID so we can persist offline and later merge on login.
  /// The server will accept a provided UUID for authenticated users, so the same ID can be reused across sync.
  Future<String> _ensureLocalConversationId({String? initialTitle}) async {
    if (_conversationId != null && _conversationId!.isNotEmpty) return _conversationId!;
    final cid = _uuid.v4();
    _conversationId = cid;
    final now = DateTime.now();
    final convo = AiConversationSummary(
      id: cid,
      title: initialTitle != null && initialTitle.isNotEmpty
          ? (initialTitle.length > 80 ? '${initialTitle.substring(0, 80)}...' : initialTitle)
          : null,
      updatedAt: now,
      lastMessageAt: now,
    );
    await _persistence.saveConversation(convo, meta: {'local_created': true});
    // Upsert into drawer list immediately
    final index = _conversations.indexWhere((c) => c.id == cid);
    if (index >= 0) {
      _conversations[index] = convo;
    } else {
      _conversations.insert(0, convo);
    }
    _conversations.sort((a, b) {
      final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
      final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
      return bTime.compareTo(aTime);
    });
    notifyListeners();
    return cid;
  }

  Future<void> deleteConversation(String conversationId, {required bool isAuthenticated}) async {
    try {
      // Delete from server first (best effort - if it fails, still delete locally)
      if (isAuthenticated) {
        try {
          await _service.deleteConversation(conversationId);
        } catch (e) {
          DebugLogger.logWarn('AI', 'Failed to delete conversation from server (continuing with local delete): $e');
          // Continue with local deletion even if server deletion fails
        }
      }

      // Delete from local DB
      await _persistence.deleteConversation(conversationId);

      // Remove from in-memory list
      _conversations.removeWhere((c) => c.id == conversationId);

      // If this was the current conversation, start a new one
      if (_conversationId == conversationId) {
        startNewConversation();
      }

      notifyListeners();
    } catch (e) {
      DebugLogger.logErrorWithTag('AI', 'Failed to delete conversation: $e');
      _error = 'Failed to delete conversation';
      notifyListeners();
    }
  }

  Future<void> clearAllConversations({required bool isAuthenticated}) async {
    try {
      // Delete all from server (best effort - if it fails, still delete locally)
      if (isAuthenticated) {
        for (final conversation in _conversations) {
          try {
            await _service.deleteConversation(conversation.id);
          } catch (e) {
            DebugLogger.logWarn('AI', 'Failed to delete conversation ${conversation.id} from server: $e');
          }
        }
      }

      // Clear from local DB
      await _persistence.clearAllConversations();

      // Clear in-memory list
      _conversations = [];

      // Start a new conversation
      startNewConversation();

      notifyListeners();
    } catch (e) {
      DebugLogger.logErrorWithTag('AI', 'Failed to clear all conversations: $e');
      _error = 'Failed to clear all conversations';
      notifyListeners();
    }
  }

  /// Retry sending the failed message (if any)
  Future<void> retryFailedMessage({required bool isAuthenticated}) async {
    // Avoid duplicating the user message; retry the last user message in-place.
    await retryLastMessage(isAuthenticated: isAuthenticated);
  }

  /// Retry the last user message without adding a duplicate
  Future<void> retryLastMessage({required bool isAuthenticated}) async {
    // Find the last user message
    final userMessages = _messages.where((m) => m.role == 'user').toList();
    if (userMessages.isEmpty) return;

    final lastUserMessage = userMessages.last;
    final message = lastUserMessage.content;

    // Clear error state
    _error = null;
    _errorType = null;
    _retryDelay = null;
    _failedMessage = null;

    // Remove any error messages or empty assistant placeholders at the end
    while (_messages.isNotEmpty &&
           (_messages.last.role == 'assistant' && _messages.last.content.isEmpty)) {
      _messages.removeLast();
    }

    // Add assistant placeholder for streaming
    _messages.add(AiChatMessage(role: 'assistant', content: ''));
    _isStreaming = true;
    notifyListeners();

    // Anonymous: just use HTTP fallback
    if (!isAuthenticated) {
      await _sendHttpIntoLastAssistant(message, isAuthenticated: false, persistUserMessage: false);
      return;
    }

    try {
      await _disconnectWs();
      _channel = await _service.connectWebSocket();

      // Send request payload
      _channel!.sink.add(jsonEncode({
        'type': 'user_message',
        'message': message,
        'conversation_id': _conversationId,
        'preferred_language': 'english',
        'page_context': {},
        'client': 'mobile',
      }));

      _wsSub = _channel!.stream.listen((event) async {
        try {
          final data = jsonDecode(event.toString());
          final type = data['type']?.toString();
          if (type == 'meta') {
            final cid = data['conversation_id']?.toString();
            if (cid != null && cid.isNotEmpty && cid != _conversationId) {
              _conversationId = cid;

              // Ensure the conversation exists locally
              final convo = AiConversationSummary(
                id: cid,
                title: message.length > 80 ? '${message.substring(0, 80)}...' : message,
                updatedAt: DateTime.now(),
                lastMessageAt: DateTime.now(),
              );
              await _persistence.saveConversation(convo);

              // Update conversation list
              final index = _conversations.indexWhere((c) => c.id == cid);
              if (index >= 0) {
                _conversations[index] = convo;
              } else {
                _conversations.insert(0, convo);
              }
              _conversations.sort((a, b) {
                final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
                final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
                return bTime.compareTo(aTime);
              });
              notifyListeners();
            }
          } else if (type == 'delta') {
            final delta = data['text']?.toString() ?? '';
            if (_messages.isNotEmpty) {
              final last = _messages.last;
              _messages[_messages.length - 1] = AiChatMessage(
                role: last.role,
                content: last.content + delta,
                createdAt: last.createdAt,
              );
              notifyListeners();
            }
          } else if (type == 'done') {
            _isStreaming = false;
            // Save conversation and messages to local DB
            if (_conversationId != null && _messages.isNotEmpty) {
              final lastMsg = _messages.last;
              if (lastMsg.role == 'assistant' && lastMsg.content.isNotEmpty) {
                await _persistence.saveMessage(
                  conversationId: _conversationId!,
                  role: 'assistant',
                  content: lastMsg.content,
                  localMessageId: _uuid.v4(),
                  syncState: AiChatPersistenceService.syncStatePendingServer,
                );
                // Update conversation summary
                final title = _messages.isNotEmpty
                    ? (_messages.first.content.length > 80 ? '${_messages.first.content.substring(0, 80)}...' : _messages.first.content)
                    : null;
                final convo = AiConversationSummary(
                  id: _conversationId!,
                  title: title,
                  updatedAt: DateTime.now(),
                  lastMessageAt: DateTime.now(),
                );
                await _persistence.saveConversation(convo);

                // Update conversation in list
                final index = _conversations.indexWhere((c) => c.id == _conversationId);
                if (index >= 0) {
                  _conversations[index] = convo;
                } else {
                  _conversations.insert(0, convo);
                }
                _conversations.sort((a, b) {
                  final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
                  final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
                  return bTime.compareTo(aTime);
                });
              }
            }
            notifyListeners();
            if (_conversationId != null) {
              unawaited(_syncConversationFromServer(_conversationId!));
            }
          } else if (type == 'error') {
            _errorType = data['error_type']?.toString();
            _error = data['message']?.toString() ?? 'Chat failed';
            if (data['retry_delay'] != null) {
              try {
                _retryDelay = double.tryParse(data['retry_delay'].toString());
              } catch (_) {
                _retryDelay = null;
              }
            } else {
              _retryDelay = null;
            }
            _isStreaming = false;

            // Remove the assistant placeholder on error
            if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
              _messages.removeLast();
            }

            // If it's an empty_response error, also handle failed message
            if (_errorType == 'empty_response' && _messages.isNotEmpty) {
              final userMessage = _messages.last;
              if (userMessage.role == 'user') {
                _failedMessage = userMessage.content;
              }
            }

            // Add an in-chat error bubble for consistency
            _messages.add(AiChatMessage(
              role: 'error',
              content: _error ?? 'Chat failed',
              errorType: _errorType,
              retryDelay: _retryDelay,
            ));
            notifyListeners();
          }
        } catch (_) {
          // Ignore malformed messages
        }
      }, onError: (e) async {
        DebugLogger.logWarn('AI', 'WS error, falling back to HTTP: $e');
        // Remove empty assistant placeholder if no content was received
        if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
          _messages.removeLast();
        }
        _isStreaming = false;
        notifyListeners();
        await _sendHttpIntoLastAssistant(message, isAuthenticated: isAuthenticated, persistUserMessage: false);
      }, onDone: () {
        // Remove empty assistant placeholder if connection closed without content
        if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
          _messages.removeLast();
        }
        _isStreaming = false;
        notifyListeners();
      });
    } catch (e) {
      DebugLogger.logWarn('AI', 'WS connect failed, falling back to HTTP: $e');
      _isStreaming = false;
      notifyListeners();
      await _sendHttpIntoLastAssistant(message, isAuthenticated: isAuthenticated, persistUserMessage: false);
    }
  }

  /// Get message content for editing (doesn't clear messages yet)
  /// Messages will be cleared when sendEditedMessage is called
  String? editMessageAt(int messageIndex) {
    if (messageIndex < 0 || messageIndex >= _messages.length) return null;
    final message = _messages[messageIndex];
    if (message.role != 'user') return null;

    // Don't clear messages yet - just return the content for editing
    // Messages will be cleared when sendEditedMessage is called

    // Clear any streaming state
    _isStreaming = false;
    _error = null;
    _errorType = null;
    _retryDelay = null;
    _failedMessage = null;

    notifyListeners();
    return message.content;
  }

  /// Send a message after editing (replaces the message at editIndex and clears all after it)
  Future<void> sendEditedMessage({
    required String message,
    required int editIndex,
    required bool isAuthenticated,
  }) async {
    // Editing cannot mutate server history; we fork a new conversation starting from the history before editIndex.
    // This yields predictable behavior and keeps merge/sync consistent.
    _error = null;
    _errorType = null;
    _retryDelay = null;
    _failedMessage = null;

    final history = <AiChatMessage>[];
    for (int i = 0; i < _messages.length && i < editIndex; i++) {
      final m = _messages[i];
      if (m.role == 'error') continue;
      // Skip empty assistant placeholders
      if (m.role == 'assistant' && m.content.isEmpty) continue;
      history.add(m);
    }

    // Start a new forked conversation (new id), persist history offline-first
    startNewConversation();
    final newCid = await _ensureLocalConversationId(
      initialTitle: history.isNotEmpty ? history.first.content : message,
    );

    _messages = List<AiChatMessage>.from(history);
    notifyListeners();

    for (final m in history) {
      await _persistence.saveMessage(
        conversationId: newCid,
        role: m.role,
        content: m.content,
        localMessageId: _uuid.v4(),
        syncState: isAuthenticated ? AiChatPersistenceService.syncStatePendingServer : AiChatPersistenceService.syncStateLocalOnly,
        createdAt: m.createdAt,
      );
    }

    // If authenticated, import the fork history to the server so the conversation is consistent across devices.
    if (isAuthenticated && history.isNotEmpty) {
      try {
        final importPayload = history.map((m) {
          return {
            'client_message_id': _uuid.v4(),
            'role': m.role,
            'content': m.content,
            'created_at': m.createdAt.toIso8601String(),
          };
        }).toList();
        await _service.importConversationMessages(conversationId: newCid, messages: importPayload);
      } catch (e) {
        DebugLogger.logWarn('AI', 'Failed to import fork history (continuing): $e');
      }
    }

    // Now send the edited message normally (it will append user+assistant and stream the reply)
    await sendMessageStreaming(message: message, isAuthenticated: isAuthenticated);
  }

  Future<void> sendMessageStreaming({
    required String message,
    required bool isAuthenticated,
  }) async {
    _error = null;
    _errorType = null;
    _retryDelay = null;
    _failedMessage = null; // Clear any previous failed message
    final cid = await _ensureLocalConversationId(initialTitle: message);
    final userLocalId = _uuid.v4();
    _messages.add(AiChatMessage(role: 'user', content: message));
    _messages.add(AiChatMessage(role: 'assistant', content: '')); // placeholder to stream into
    _isStreaming = true;
    notifyListeners();

    // Persist user message immediately (offline-first)
    await _persistence.saveMessage(
      conversationId: cid,
      role: 'user',
      content: message,
      localMessageId: userLocalId,
      syncState: isAuthenticated ? AiChatPersistenceService.syncStatePendingServer : AiChatPersistenceService.syncStateLocalOnly,
    );

    // Anonymous: just use HTTP fallback (no persistence anyway)
    if (!isAuthenticated) {
      await _sendHttpIntoLastAssistant(message, isAuthenticated: false, persistUserMessage: false);
      return;
    }

    try {
      await _disconnectWs();
      _channel = await _service.connectWebSocket();

      // Send request payload
      _channel!.sink.add(jsonEncode({
        'type': 'user_message',
        'message': message,
        'conversation_id': _conversationId,
        // End-to-end idempotency: tie this request to the locally persisted user message id.
        'client_message_id': userLocalId,
        'preferred_language': 'english',
        'page_context': {},
        'client': 'mobile',
      }));

      _wsSub = _channel!.stream.listen((event) async {
        try {
          final data = jsonDecode(event.toString());
          final type = data['type']?.toString();
          if (type == 'meta') {
            final cid = data['conversation_id']?.toString();
            if (cid != null && cid.isNotEmpty && cid != _conversationId) {
              _conversationId = cid;

              final firstUserContent = (_messages.isNotEmpty && _messages.first.role == 'user') ? _messages.first.content : null;
              final title = firstUserContent == null
                  ? null
                  : (firstUserContent.length > 80 ? '${firstUserContent.substring(0, 80)}...' : firstUserContent);

              // Ensure the conversation exists locally immediately (helps drawer + DB integrity)
              final convo = AiConversationSummary(
                id: cid,
                title: title,
                updatedAt: DateTime.now(),
                lastMessageAt: DateTime.now(),
              );
              await _persistence.saveConversation(convo);

              // Upsert into the drawer list immediately
              final index = _conversations.indexWhere((c) => c.id == cid);
              if (index >= 0) {
                _conversations[index] = convo;
              } else {
                _conversations.insert(0, convo);
              }
              _conversations.sort((a, b) {
                final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
                final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
                return bTime.compareTo(aTime);
              });
              notifyListeners();
            }
          } else if (type == 'delta') {
            final delta = data['text']?.toString() ?? '';
            if (_messages.isNotEmpty) {
              final last = _messages.last;
              _messages[_messages.length - 1] = AiChatMessage(
                role: last.role,
                content: last.content + delta,
                createdAt: last.createdAt,
              );
              notifyListeners();
            }
          } else if (type == 'done') {
            _isStreaming = false;
            // Remove empty assistant placeholder if no content was received
            if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
              _messages.removeLast();
              notifyListeners();
              return;
            }
            // Persist the final assistant message as pending-server (will be reconciled on next snapshot)
            if (_conversationId != null && _messages.isNotEmpty) {
              final lastMsg = _messages.last;
              if (lastMsg.role == 'assistant' && lastMsg.content.isNotEmpty) {
                await _persistence.saveMessage(
                  conversationId: _conversationId!,
                  role: 'assistant',
                  content: lastMsg.content,
                  localMessageId: _uuid.v4(),
                  syncState: AiChatPersistenceService.syncStatePendingServer,
                );
                final title = _messages.isNotEmpty
                    ? (_messages.first.content.length > 80 ? '${_messages.first.content.substring(0, 80)}...' : _messages.first.content)
                    : null;
                final convo = AiConversationSummary(
                  id: _conversationId!,
                  title: title,
                  updatedAt: DateTime.now(),
                  lastMessageAt: DateTime.now(),
                );
                await _persistence.saveConversation(convo);
              }
            }
            notifyListeners();
            // Refresh from server snapshot to dedupe + mark server messages
            if (_conversationId != null) {
              unawaited(_syncConversationFromServer(_conversationId!));
            }
          } else if (type == 'error') {
            _errorType = data['error_type']?.toString();
            _error = data['message']?.toString() ?? 'Chat failed';
            if (data['retry_delay'] != null) {
              try {
                _retryDelay = double.tryParse(data['retry_delay'].toString());
              } catch (_) {
                _retryDelay = null;
              }
            } else {
              _retryDelay = null;
            }
            _isStreaming = false;

            // If quota error, remove only the assistant placeholder (keep user message for context)
            // and store the message for retry
            if (_errorType == 'quota_exceeded' && _messages.isNotEmpty) {
              // Remove only the assistant placeholder, keep user message visible for context
              if (_messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
                _messages.removeLast(); // Remove assistant placeholder
              }
              // Store the last user message for retry if it exists
              final userMessages = _messages.where((m) => m.role == 'user').toList();
              if (userMessages.isNotEmpty) {
                _failedMessage = userMessages.last.content;
              }
            } else if (_errorType != 'quota_exceeded') {
              // For non-quota errors, remove the assistant placeholder if empty
              if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
                _messages.removeLast();
              }
            }

            // Add an in-chat error bubble for consistency with HTTP errors
            _messages.add(AiChatMessage(
              role: 'error',
              content: _error ?? 'Chat failed',
              errorType: _errorType,
              retryDelay: _retryDelay,
            ));
            notifyListeners();
          }
        } catch (_) {
          // Ignore malformed messages
        }
      }, onError: (e) async {
        DebugLogger.logWarn('AI', 'WS error, falling back to HTTP: $e');
        // Best effort: stop WS streaming state before HTTP fallback updates it again.
        _isStreaming = false;
        notifyListeners();
        await _sendHttpIntoLastAssistant(
          message,
          isAuthenticated: isAuthenticated,
          persistUserMessage: false,
          clientMessageId: userLocalId,
        );
      }, onDone: () {
        // Remove empty assistant placeholder if connection closed without content
        if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
          _messages.removeLast();
        }
        _isStreaming = false;
        notifyListeners();
      });
    } catch (e) {
      DebugLogger.logWarn('AI', 'WS connect failed, falling back to HTTP: $e');
      _isStreaming = false;
      notifyListeners();
      await _sendHttpIntoLastAssistant(
        message,
        isAuthenticated: isAuthenticated,
        persistUserMessage: false,
        clientMessageId: userLocalId,
      );
    }
  }

  Future<void> _sendHttpIntoLastAssistant(
    String message, {
    bool isAuthenticated = false,
    bool persistUserMessage = true,
    String? clientMessageId,
  }) async {
    _isStreaming = true;
    notifyListeners();
    try {
      // For anonymous requests, do not send a conversation_id to the server (server ignores it anyway).
      final serverConversationId = isAuthenticated ? _conversationId : null;
      final data = await _service.sendMessageHttp(
        message: message,
        conversationId: serverConversationId,
        isAuthenticated: isAuthenticated,
        clientMessageId: isAuthenticated ? clientMessageId : null,
      );
      final newCid = data['conversation_id']?.toString();
      if (isAuthenticated && newCid != null && newCid.isNotEmpty) {
        _conversationId = newCid;
      }
      final reply = data['reply']?.toString() ?? '';
      if (_messages.isNotEmpty) {
        // Find the last assistant placeholder (empty content) to update
        bool foundPlaceholder = false;
        for (int i = _messages.length - 1; i >= 0; i--) {
          if (_messages[i].role == 'assistant' && _messages[i].content.isEmpty) {
            _messages[i] = AiChatMessage(role: 'assistant', content: reply);
            foundPlaceholder = true;
            break;
          }
        }
        // If no placeholder found, add a new assistant message
        if (!foundPlaceholder) {
          _messages.add(AiChatMessage(role: 'assistant', content: reply));
        }

        if (_conversationId != null) {
          // Save user message (optional - callers may already have persisted it)
          if (persistUserMessage) {
            await _persistence.saveMessage(
              conversationId: _conversationId!,
              role: 'user',
              content: message,
              localMessageId: _uuid.v4(),
              syncState: isAuthenticated ? AiChatPersistenceService.syncStatePendingServer : AiChatPersistenceService.syncStateLocalOnly,
            );
          }
          // Save assistant reply
          await _persistence.saveMessage(
            conversationId: _conversationId!,
            role: 'assistant',
            content: reply,
            localMessageId: _uuid.v4(),
            syncState: isAuthenticated ? AiChatPersistenceService.syncStatePendingServer : AiChatPersistenceService.syncStateLocalOnly,
          );
          // Update conversation summary
          final title = message.length > 80 ? '${message.substring(0, 80)}...' : message;
          final convo = AiConversationSummary(
            id: _conversationId!,
            title: title,
            updatedAt: DateTime.now(),
            lastMessageAt: DateTime.now(),
          );
          await _persistence.saveConversation(convo);

          // Update conversation in list immediately
          final index = _conversations.indexWhere((c) => c.id == _conversationId);
          if (index >= 0) {
            _conversations[index] = convo;
          } else {
            _conversations.insert(0, convo);
          }
          // Sort by most recent first
          _conversations.sort((a, b) {
            final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
            final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
            return bTime.compareTo(aTime);
          });
        }
      }
      _isStreaming = false;
      notifyListeners();
    } catch (e) {
      _isStreaming = false; // Stop streaming immediately on error

      // Extract error message
      String errorMessage = e.toString();
      // Remove "Exception: " prefix if present
      if (errorMessage.startsWith('Exception: ')) {
        errorMessage = errorMessage.substring(11);
      }

      _error = errorMessage;

      // Check if it's a quota error from HTTP response
      final errorStr = errorMessage.toLowerCase();
      String? errorType;
      if (errorStr.contains('quota') || errorStr.contains('429') || errorStr.contains('rate limit')) {
        errorType = 'quota_exceeded';
        _errorType = 'quota_exceeded';
        // Store the last user message for retry if it exists
        final userMessages = _messages.where((m) => m.role == 'user').toList();
        if (userMessages.isNotEmpty) {
          _failedMessage = userMessages.last.content;
        }
      } else if (errorStr.contains('timeout')) {
        errorType = 'timeout_error';
        _errorType = 'timeout_error';
      } else if (errorStr.contains('connection') || errorStr.contains('network')) {
        errorType = 'network_error';
        _errorType = 'network_error';
      } else {
        errorType = 'server_error';
        _errorType = 'server_error';
      }

      // Remove the assistant placeholder if it exists
      if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
        _messages.removeLast();
      }

      // Add error message bubble to the conversation
      _messages.add(AiChatMessage(
        role: 'error',
        content: errorMessage,
        errorType: errorType,
      ));

      notifyListeners();
    }
  }

  Future<void> _syncConversationFromServer(String conversationId) async {
    if (_syncInFlight.contains(conversationId)) return;
    _syncInFlight.add(conversationId);
    try {
      final data = await _service.getConversation(conversationId);
      final msgs = (data['messages'] as List?) ?? [];
      final serverMessages = msgs.map((m) => Map<String, dynamic>.from(m)).toList();

      await _persistence.replaceServerMessages(
        conversationId: conversationId,
        serverMessages: serverMessages,
      );
      await _persistence.reconcilePendingMessages(
        conversationId: conversationId,
        serverMessages: serverMessages,
      );
    } catch (e) {
      DebugLogger.logWarn('AI', 'Failed to sync conversation from server: $e');
    } finally {
      _syncInFlight.remove(conversationId);
    }
  }

  Future<void> _maybeImportOfflineMessages(String conversationId) async {
    try {
      final localOnly = await _persistence.getLocalOnlyMessagesForImport(conversationId, limit: 200);
      if (localOnly.isEmpty) return;

      final importPayload = localOnly.map((m) {
        return {
          'client_message_id': m['local_message_id']?.toString(),
          'role': m['role']?.toString(),
          'content': m['content']?.toString(),
          'created_at': m['created_at']?.toString(),
        };
      }).toList();

      await _service.importConversationMessages(conversationId: conversationId, messages: importPayload);

      // Prevent repeated imports; mark as pending-server so they can be reconciled after the next snapshot
      await _persistence.updateConversationMessagesSyncState(
        conversationId: conversationId,
        from: AiChatPersistenceService.syncStateLocalOnly,
        to: AiChatPersistenceService.syncStatePendingServer,
      );

      await _syncConversationFromServer(conversationId);
    } catch (e) {
      DebugLogger.logWarn('AI', 'Offline message import skipped/failed: $e');
    }
  }

  Future<void> _disconnectWs() async {
    try {
      await _wsSub?.cancel();
    } catch (_) {}
    _wsSub = null;
    try {
      await _channel?.sink.close();
    } catch (_) {}
    _channel = null;
  }

  @override
  void dispose() {
    _disconnectWs();
    super.dispose();
  }
}
