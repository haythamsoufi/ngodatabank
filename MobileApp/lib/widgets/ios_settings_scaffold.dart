import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;

import '../utils/ios_settings_style.dart';
import 'app_bar.dart';

/// Settings-style page: iOS large-title sliver nav + grouped background, or Material app bar + list.
class IOSSettingsPageScaffold extends StatelessWidget {
  const IOSSettingsPageScaffold({
    super.key,
    required this.title,
    required this.children,
    this.materialAppBarActions,
  });

  /// Shown as large title on iOS and as [AppAppBar] title on other platforms.
  final String title;

  final List<Widget> children;

  final List<Widget>? materialAppBarActions;

  @override
  Widget build(BuildContext context) {
    final bg = IOSSettingsStyle.groupedTableBackground(context);

    if (IOSSettingsStyle.useIosSettingsChrome) {
      return Scaffold(
        backgroundColor: bg,
        body: CustomScrollView(
          physics: IOSSettingsStyle.pageScrollPhysics(),
          slivers: [
            cupertino.CupertinoSliverNavigationBar(
              largeTitle: Text(title),
              backgroundColor: bg,
              border: IOSSettingsStyle.navigationBarBottomBorder(context),
            ),
            SliverSafeArea(
              top: false,
              sliver: SliverList(
                delegate: SliverChildListDelegate(children),
              ),
            ),
          ],
        ),
      );
    }

    return Scaffold(
      appBar: AppAppBar(
        title: title,
        actions: materialAppBarActions,
      ),
      body: SafeArea(
        child: ColoredBox(
          color: bg,
          child: ListView(
            padding: EdgeInsets.zero,
            physics: IOSSettingsStyle.pageScrollPhysics(),
            children: children,
          ),
        ),
      ),
    );
  }
}
