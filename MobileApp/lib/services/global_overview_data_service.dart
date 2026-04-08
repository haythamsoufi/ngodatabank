import 'dart:convert';

import 'package:latlong2/latlong.dart';

import '../config/fdrs_constants.dart';
import 'api_service.dart';

/// Aggregated FDRS indicator values per country for the native home map/chart.
class GlobalOverviewDataset {
  GlobalOverviewDataset({
    required this.periodName,
    required this.byCountryId,
    required this.countryNames,
    required this.countryIso2,
  });

  final String? periodName;
  final Map<int, double> byCountryId;
  final Map<int, String> countryNames;
  final Map<int, String> countryIso2;

  double get globalTotal =>
      byCountryId.values.fold<double>(0, (a, b) => a + b);

  List<MapEntry<int, double>> topByValue(int n) {
    final list = byCountryId.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    return list.take(n).toList();
  }

  /// Points for markers where we have both a value and a centroid.
  List<({LatLng point, double value, int countryId, String iso2})> geoPoints(
    LatLng? Function(String? iso2) centroid,
  ) {
    final out = <({LatLng point, double value, int countryId, String iso2})>[];
    for (final e in byCountryId.entries) {
      final iso = countryIso2[e.key];
      if (iso == null || iso.isEmpty) continue;
      final ll = centroid(iso);
      if (ll == null || e.value <= 0) continue;
      out.add((
        point: ll,
        value: e.value,
        countryId: e.key,
        iso2: iso.toUpperCase(),
      ));
    }
    return out;
  }
}

class GlobalOverviewDataService {
  GlobalOverviewDataService({ApiService? api}) : _api = api ?? ApiService();

  final ApiService _api;

  static double? _parseNumeric(dynamic v) {
    if (v == null) return null;
    if (v is num) return v.toDouble();
    if (v is String) {
      final s = v.trim().replaceAll(',', '').replaceAll(' ', '');
      if (s.isEmpty || s.toLowerCase() == 'null') return null;
      return double.tryParse(s) ?? int.tryParse(s)?.toDouble();
    }
    if (v is Map<String, dynamic>) {
      for (final k in ['value', 'total', 'amount', 'count', 'number']) {
        if (v.containsKey(k)) return _parseNumeric(v[k]);
      }
    }
    if (v is List && v.isNotEmpty) return _parseNumeric(v.first);
    return null;
  }

  /// Distinct FDRS period names, newest first (same order as Backoffice `/periods`).
  Future<List<String>> listFdrsPeriods() async {
    final resp = await _api.get(
      '/api/v1/periods',
      queryParams: {'template_id': '${FdrsConstants.templateId}'},
      includeAuth: false,
      useCache: false,
    );
    if (resp.statusCode != 200) return [];
    final decoded = jsonDecode(resp.body);
    if (decoded is! List<dynamic>) return [];
    return decoded
        .map((e) => e?.toString() ?? '')
        .where((s) => s.isNotEmpty)
        .toList();
  }

  Future<({Map<int, String> names, Map<int, String> iso2})> _loadCountryMaps(
    String locale,
  ) async {
    final resp = await _api.get(
      '/api/v1/countrymap',
      queryParams: {'locale': locale},
      includeAuth: false,
      useCache: false,
    );
    if (resp.statusCode != 200) {
      return (names: <int, String>{}, iso2: <int, String>{});
    }
    final decoded = jsonDecode(resp.body);
    if (decoded is! List<dynamic>) {
      return (names: <int, String>{}, iso2: <int, String>{});
    }
    final names = <int, String>{};
    final iso2 = <int, String>{};
    for (final e in decoded) {
      if (e is! Map<String, dynamic>) continue;
      final id = e['id'];
      final idInt = id is int ? id : int.tryParse(id?.toString() ?? '');
      if (idInt == null) continue;
      final label = (e['localized_name'] ?? e['name'])?.toString();
      if (label != null && label.isNotEmpty) {
        names[idInt] = label;
      }
      final iso = e['iso2']?.toString();
      if (iso != null && iso.isNotEmpty) {
        iso2[idInt] = iso.toUpperCase();
      }
    }
    return (names: names, iso2: iso2);
  }

  Future<List<Map<String, dynamic>>> _fetchAllTableRows({
    required int indicatorBankId,
    String? periodName,
  }) async {
    final merged = <Map<String, dynamic>>[];
    var page = 1;
    const perPage = 20000;
    while (true) {
      final qp = <String, String>{
        'template_id': '${FdrsConstants.templateId}',
        'indicator_bank_id': '$indicatorBankId',
        'disagg': 'true',
        'related': 'all',
        'per_page': '$perPage',
        'page': '$page',
      };
      if (periodName != null && periodName.isNotEmpty) {
        qp['period_name'] = periodName;
      }
      final resp = await _api.get(
        '/api/v1/data/tables',
        queryParams: qp,
        includeAuth: false,
        useCache: false,
      );
      if (resp.statusCode != 200) {
        throw OverviewLoadException(
          'HTTP ${resp.statusCode} loading /data/tables',
        );
      }
      final body = jsonDecode(resp.body);
      if (body is! Map<String, dynamic>) break;
      final data = body['data'];
      if (data is List<dynamic>) {
        for (final row in data) {
          if (row is Map<String, dynamic>) merged.add(row);
        }
      }
      final totalPages = (body['total_pages'] as num?)?.toInt() ?? 1;
      if (page >= totalPages) break;
      page++;
      if (page > 80) break;
    }
    return merged;
  }

  /// Loads totals per country for one indicator and [periodName].
  ///
  /// When [periodName] is null or empty, uses the first period from [listFdrsPeriods]
  /// (latest reporting period).
  Future<GlobalOverviewDataset> loadOverview({
    required int indicatorBankId,
    required String locale,
    String? periodName,
  }) async {
    var period = periodName;
    if (period == null || period.isEmpty) {
      final list = await listFdrsPeriods();
      period = list.isNotEmpty ? list.first : null;
    }
    final maps = await _loadCountryMaps(locale);
    final rows = await _fetchAllTableRows(
      indicatorBankId: indicatorBankId,
      periodName: period,
    );

    final byCountry = <int, double>{};
    for (final row in rows) {
      final cidRaw = row['country_id'];
      final cid = cidRaw is int ? cidRaw : int.tryParse(cidRaw?.toString() ?? '');
      if (cid == null) continue;
      final n = _parseNumeric(row['num_value']) ?? _parseNumeric(row['value']);
      if (n == null || n <= 0) continue;
      byCountry.update(cid, (v) => v + n, ifAbsent: () => n);
    }

    return GlobalOverviewDataset(
      periodName: period,
      byCountryId: byCountry,
      countryNames: maps.names,
      countryIso2: maps.iso2,
    );
  }
}

class OverviewLoadException implements Exception {
  OverviewLoadException(this.message);
  final String message;

  @override
  String toString() => message;
}
