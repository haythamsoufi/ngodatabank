import 'dart:convert';
import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

import '../config/app_config.dart';
import '../utils/accessibility_helper.dart';
import '../utils/theme_extensions.dart';

String _cssHex(Color color) {
  final int rgb =
      (color.red << 16) | (color.green << 8) | color.blue;
  return '#${rgb.toRadixString(16).padLeft(6, '0')}';
}

/// Distinct slice/series colors derived from the active [ColorScheme].
List<Color> _chartSliceColors(ColorScheme cs) {
  return [
    cs.primary,
    cs.secondary,
    cs.tertiary,
    cs.error,
    Color.alphaBlend(cs.primary.withValues(alpha: 0.72), cs.surface),
    Color.alphaBlend(cs.secondary.withValues(alpha: 0.72), cs.surface),
  ];
}

/// Renders coerced structured payloads (Backoffice chat-immersive parity).
class AiChatStructuredPayloadsColumn extends StatelessWidget {
  final List<Map<String, dynamic>> payloads;

  const AiChatStructuredPayloadsColumn({
    super.key,
    required this.payloads,
  });

  @override
  Widget build(BuildContext context) {
    if (payloads.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final p in payloads)
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: _StructuredCard(payload: p),
          ),
      ],
    );
  }
}

class _StructuredCard extends StatelessWidget {
  final Map<String, dynamic> payload;

  const _StructuredCard({required this.payload});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final type = (payload['type'] ?? '').toString().toLowerCase();
    final border = cs.outline;
    final bg =
        theme.isDarkTheme ? cs.surfaceContainerHighest : cs.surfaceContainerLow;

    Widget child;
    switch (type) {
      case 'data_table':
        child = _DataTableView(payload: payload);
        break;
      case 'line':
      case 'linechart':
      case 'timeseries':
        child = _LineChartView(payload: payload);
        break;
      case 'bar':
      case 'barchart':
        child = _BarChartView(payload: payload);
        break;
      case 'pie':
      case 'donut':
        child = _PieChartView(payload: payload);
        break;
      case 'worldmap':
      case 'world_map':
      case 'choropleth':
        child = _WorldMapWebView(spec: payload);
        break;
      default:
        child = Text(
          payload['title']?.toString() ?? 'Visualization',
          style: TextStyle(color: cs.onSurfaceVariant),
        );
    }

    final title = payload['title']?.toString().trim() ?? '';
    return Container(
      decoration: BoxDecoration(
        color: bg,
        border: Border.all(color: border),
      ),
      padding: const EdgeInsets.all(10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (title.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                children: [
                  Icon(Icons.insert_chart_outlined, size: 18, color: cs.primary),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      title,
                      style: TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 13,
                        color: cs.onSurface,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          child,
        ],
      ),
    );
  }
}

class _DataTableView extends StatelessWidget {
  final Map<String, dynamic> payload;

  const _DataTableView({required this.payload});

  @override
  Widget build(BuildContext context) {
    final rows = payload['rows'];
    if (rows is! List || rows.isEmpty) {
      return const Text('No table rows');
    }
    final cs = Theme.of(context).colorScheme;
    final headerColor = cs.surfaceContainerHigh;
    final textStyle =
        TextStyle(fontSize: 11, color: cs.onSurfaceVariant);

    final first = rows.first;
    List<String> columns;
    if (first is Map) {
      columns = first.keys.map((k) => k.toString()).toList();
    } else {
      columns = List.generate((first as List).length, (i) => '$i');
    }

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Table(
        border: TableBorder.all(color: cs.outline, width: 0.5),
        defaultVerticalAlignment: TableCellVerticalAlignment.middle,
        children: [
          TableRow(
            decoration: BoxDecoration(color: headerColor),
            children: columns
                .map(
                  (c) => Padding(
                    padding: const EdgeInsets.all(6),
                    child: Text(c, style: textStyle.copyWith(fontWeight: FontWeight.w600)),
                  ),
                )
                .toList(),
          ),
          ...rows.take(80).map((r) {
            final cells = <Widget>[];
            if (r is Map) {
              for (final c in columns) {
                cells.add(
                  Padding(
                    padding: const EdgeInsets.all(6),
                    child: Text('${r[c] ?? ''}', style: textStyle),
                  ),
                );
              }
            } else if (r is List) {
              for (var i = 0; i < columns.length; i++) {
                cells.add(
                  Padding(
                    padding: const EdgeInsets.all(6),
                    child: Text(i < r.length ? '${r[i]}' : '', style: textStyle),
                  ),
                );
              }
            }
            return TableRow(children: cells);
          }),
        ],
      ),
    );
  }
}

class _LineChartView extends StatelessWidget {
  final Map<String, dynamic> payload;

  const _LineChartView({required this.payload});

  @override
  Widget build(BuildContext context) {
    final series = payload['series'];
    if (series is! List || series.isEmpty) return const SizedBox.shrink();

    final spots = <FlSpot>[];
    for (final p in series) {
      if (p is! Map) continue;
      final x = (p['x'] as num?)?.toDouble();
      final y = (p['y'] as num?)?.toDouble();
      if (x == null || y == null) continue;
      spots.add(FlSpot(x, y));
    }
    if (spots.isEmpty) return const SizedBox.shrink();

    final minX = spots.map((s) => s.x).reduce(math.min);
    final maxX = spots.map((s) => s.x).reduce(math.max);
    final minY = spots.map((s) => s.y).reduce(math.min);
    final maxY = spots.map((s) => s.y).reduce(math.max);
    final padY = (maxY - minY).abs() < 1e-6 ? 1.0 : (maxY - minY) * 0.1;

    final lineColor = context.linkOnSurfaceColor;

    return SizedBox(
      height: 200,
      child: LineChart(
        LineChartData(
          minX: minX,
          maxX: maxX,
          minY: minY - padY,
          maxY: maxY + padY,
          gridData: FlGridData(show: true, drawVerticalLine: false, horizontalInterval: null),
          titlesData: FlTitlesData(
            leftTitles: AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 36)),
            bottomTitles: AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 28)),
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          ),
          borderData: FlBorderData(show: true),
          lineBarsData: [
            LineChartBarData(
              spots: spots,
              isCurved: false,
              color: lineColor,
              barWidth: 2,
              dotData: const FlDotData(show: true),
            ),
          ],
        ),
      ),
    );
  }
}

class _BarChartView extends StatelessWidget {
  final Map<String, dynamic> payload;

  const _BarChartView({required this.payload});

  @override
  Widget build(BuildContext context) {
    final cats = payload['categories'];
    if (cats is! List || cats.isEmpty) return const SizedBox.shrink();

    final labels = <String>[];
    final vals = <double>[];
    for (final c in cats) {
      if (c is! Map) continue;
      labels.add((c['label'] ?? '').toString());
      vals.add((c['value'] as num?)?.toDouble() ?? 0);
    }
    if (vals.isEmpty) return const SizedBox.shrink();

    final maxY = vals.reduce(math.max);
    final cs = Theme.of(context).colorScheme;
    final barColor = cs.primary;

    return SizedBox(
      height: math.min(280.0, 40.0 + cats.length * 28.0),
      child: BarChart(
        BarChartData(
          alignment: BarChartAlignment.spaceAround,
          maxY: maxY <= 0 ? 1 : maxY * 1.15,
          titlesData: FlTitlesData(
            leftTitles: AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 36)),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 52,
                getTitlesWidget: (v, m) {
                  final i = v.toInt();
                  if (i < 0 || i >= labels.length) return const SizedBox.shrink();
                  return Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(
                      labels[i].length > 10 ? '${labels[i].substring(0, 8)}…' : labels[i],
                      style: TextStyle(fontSize: 9, color: cs.onSurfaceVariant),
                    ),
                  );
                },
              ),
            ),
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          ),
          borderData: FlBorderData(show: false),
          barGroups: List.generate(vals.length, (i) {
            return BarChartGroupData(
              x: i,
              barRods: [
                BarChartRodData(toY: vals[i], width: 14, color: barColor),
              ],
            );
          }),
        ),
      ),
    );
  }
}

class _PieChartView extends StatelessWidget {
  final Map<String, dynamic> payload;

  const _PieChartView({required this.payload});

  @override
  Widget build(BuildContext context) {
    final slices = payload['slices'];
    if (slices is! List || slices.length < 2) return const SizedBox.shrink();

    double total = 0;
    final items = <({String label, double value, Color color})>[];
    final palette = _chartSliceColors(Theme.of(context).colorScheme);

    var i = 0;
    for (final s in slices) {
      if (s is! Map) continue;
      final label = (s['label'] ?? '').toString();
      final v = (s['value'] as num?)?.toDouble() ?? 0;
      if (v <= 0) continue;
      total += v;
      items.add((label: label, value: v, color: palette[i % palette.length]));
      i++;
    }
    if (total <= 0 || items.isEmpty) return const SizedBox.shrink();

    return SizedBox(
      height: 220,
      child: Row(
        children: [
          Expanded(
            flex: 2,
            child: PieChart(
              PieChartData(
                sectionsSpace: 2,
                centerSpaceRadius: 36,
                sections: [
                  for (final it in items)
                    PieChartSectionData(
                      color: it.color,
                      value: it.value,
                      title: '${(it.value / total * 100).toStringAsFixed(0)}%',
                      radius: 52,
                      titleStyle: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: AccessibilityHelper.getAccessibleTextColor(it.color),
                      ),
                    ),
                ],
              ),
            ),
          ),
          Expanded(
            flex: 2,
            child: ListView(
              children: [
                for (final it in items)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Row(
                      children: [
                        Container(width: 10, height: 10, color: it.color),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            '${it.label} (${it.value.toStringAsFixed(1)})',
                            style: TextStyle(
                              fontSize: 11,
                              color: Theme.of(context).colorScheme.onSurface,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _WorldMapWebView extends StatefulWidget {
  final Map<String, dynamic> spec;

  const _WorldMapWebView({required this.spec});

  @override
  State<_WorldMapWebView> createState() => _WorldMapWebViewState();
}

class _WorldMapWebViewState extends State<_WorldMapWebView> {
  String _html(ColorScheme cs) {
    final specJson = jsonEncode(widget.spec);
    final bg = _cssHex(cs.surface);
    final fg = _cssHex(cs.onSurfaceVariant);
    final stroke = _cssHex(cs.outline);
    return '''
<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
html,body{margin:0;padding:0;height:100%;background:$bg;}
#map{height:220px;width:100%;}
.info{font:12px/1.35 system-ui;padding:6px 8px;color:$fg;}
</style>
</head><body>
<div class="info" id="t"></div>
<div id="map"></div>
<script>
const spec = $specJson;
document.getElementById('t').textContent = (spec.metric || 'value') + ' — ' + (spec.countries||[]).length + ' countries';
const valueByIso = {};
(spec.countries||[]).forEach(function(c){
  if (c && c.iso3) valueByIso[String(c.iso3).toUpperCase()] = Number(c.value);
});
const vals = Object.values(valueByIso).filter(function(v){return isFinite(v);});
const vmin = vals.length ? Math.min.apply(null, vals) : 0;
const vmax = vals.length ? Math.max.apply(null, vals) : 1;
function colorFor(v){
  if (!isFinite(v)) return '#94a3b8';
  const t = vmax > vmin ? (v - vmin) / (vmax - vmin) : 0.5;
  const r = Math.round(30 + 180 * t);
  const g = Math.round(100 + 80 * (1-t));
  const b = Math.round(180 - 100 * t);
  return 'rgb('+r+','+g+','+b+')';
}
const map = L.map('map', { scrollWheelZoom: false, zoomControl: true }).setView([20, 0], 2);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 8,
  attribution: '&copy; OpenStreetMap'
}).addTo(map);
fetch('https://cdn.jsdelivr.net/gh/datasets/geo-countries@master/data/countries.geojson')
  .then(function(r){return r.json();})
  .then(function(geo){
    L.geoJSON(geo, {
      style: function(feature){
        var p = feature.properties || {};
        var iso = (p.ISO_A3 || p.iso_a3 || p.ISO_A3_EH || '').toString().toUpperCase();
        var v = valueByIso[iso];
        return {
          fillColor: colorFor(v),
          weight: 0.5,
          color: '$stroke',
          fillOpacity: 0.75
        };
      }
    }).addTo(map);
    setTimeout(function(){ map.invalidateSize(); }, 200);
  })
  .catch(function(){
    document.getElementById('t').textContent = 'Map data unavailable offline';
  });
</script>
</body></html>
''';
  }

  @override
  Widget build(BuildContext context) {
    final baseUri = WebUri(AppConfig.baseApiUrl);
    final cs = Theme.of(context).colorScheme;
    return SizedBox(
      height: 248,
      child: InAppWebView(
        initialData: InAppWebViewInitialData(
          data: _html(cs),
          baseUrl: baseUri,
        ),
      ),
    );
  }
}
