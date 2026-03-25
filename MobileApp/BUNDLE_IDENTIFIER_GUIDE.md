# Bundle Identifier Configuration Guide

This guide explains how to configure bundle identifiers for different organizations.

## Current Default Configuration

**Default (NGO Databank):**
- Android: `com.ngo.databank`
- iOS: `com.ngo.databank`

**IFRC Configuration:**
- Android: `com.ifrc.databank`
- iOS: `com.ifrc.databank`

## Where identifiers live in the project

| Area | Files | What to update |
| --- | --- | --- |
| Android package / namespace | `android/app/build.gradle` | `namespace`, `applicationId` |
| Android label & deep links | `android/app/src/main/AndroidManifest.xml` | `android:label`, intent filter `android:scheme` |
| iOS bundle ID | `ios/Runner.xcodeproj/project.pbxproj` | `PRODUCT_BUNDLE_IDENTIFIER` (app and `RunnerTests`) |
| iOS display name & URL scheme | `ios/Runner/Info.plist` | `CFBundleDisplayName`, `CFBundleURLSchemes` |

The `name` field in `pubspec.yaml` is the Dart package name (e.g. `ngo_databank_app`), not the Play/App Store bundle identifier.

**IFRC vs default deep links / labels:** For IFRC builds, align display name, app label, and URL scheme with your org (e.g. `ifrcdatabank`) in the manifest and `Info.plist` as needed.

## Changing Bundle Identifier for IFRC Builds

### Method 1: Manual Update (Before Building)

#### Android
Edit `android/app/build.gradle`:
```gradle
namespace "com.ifrc.databank"
// ...
defaultConfig {
    applicationId "com.ifrc.databank"
}
```

#### iOS
Edit `ios/Runner.xcodeproj/project.pbxproj`:
Replace all instances of:
```
PRODUCT_BUNDLE_IDENTIFIER = com.ngo.databank;
```
with:
```
PRODUCT_BUNDLE_IDENTIFIER = com.ifrc.databank;
```

Also update `ios/Runner/Info.plist`:
```xml
<key>CFBundleDisplayName</key>
<string>IFRC Network Databank</string>
```

### Method 2: Using Script (Recommended)

Create a script to automate the change:

**`scripts/set-bundle-id.sh`** (for macOS/Linux):
```bash
#!/bin/bash

ORG=${1:-"ngo"}  # Default to "ngo"

if [ "$ORG" == "ifrc" ]; then
    # Android
    sed -i '' 's/namespace "com\.ngo\.databank"/namespace "com.ifrc.databank"/g' android/app/build.gradle
    sed -i '' 's/applicationId "com\.ngo\.databank"/applicationId "com.ifrc.databank"/g' android/app/build.gradle
    
    # iOS
    sed -i '' 's/PRODUCT_BUNDLE_IDENTIFIER = com\.ngo\.databank/PRODUCT_BUNDLE_IDENTIFIER = com.ifrc.databank/g' ios/Runner.xcodeproj/project.pbxproj
    sed -i '' 's/PRODUCT_BUNDLE_IDENTIFIER = com\.ngo\.databank\.RunnerTests/PRODUCT_BUNDLE_IDENTIFIER = com.ifrc.databank.RunnerTests/g' ios/Runner.xcodeproj/project.pbxproj
    
    echo "Bundle identifier set to IFRC"
else
    # Android
    sed -i '' 's/namespace "com\.ifrc\.databank"/namespace "com.ngo.databank"/g' android/app/build.gradle
    sed -i '' 's/applicationId "com\.ifrc\.databank"/applicationId "com.ngo.databank"/g' android/app/build.gradle
    
    # iOS
    sed -i '' 's/PRODUCT_BUNDLE_IDENTIFIER = com\.ifrc\.databank/PRODUCT_BUNDLE_IDENTIFIER = com.ngo.databank/g' ios/Runner.xcodeproj/project.pbxproj
    sed -i '' 's/PRODUCT_BUNDLE_IDENTIFIER = com\.ifrc\.databank\.RunnerTests/PRODUCT_BUNDLE_IDENTIFIER = com.ngo.databank.RunnerTests/g' ios/Runner.xcodeproj/project.pbxproj
    
    echo "Bundle identifier set to NGO Databank (default)"
fi
```

**Usage:**
```bash
# Set to IFRC
./scripts/set-bundle-id.sh ifrc

# Set to NGO (default)
./scripts/set-bundle-id.sh ngo
```

**`scripts/set-bundle-id.ps1`** (for Windows):
```powershell
param(
    [string]$Org = "ngo"
)

if ($Org -eq "ifrc") {
    # Android
    (Get-Content android/app/build.gradle) -replace 'namespace "com\.ngo\.databank"', 'namespace "com.ifrc.databank"' | Set-Content android/app/build.gradle
    (Get-Content android/app/build.gradle) -replace 'applicationId "com\.ngo\.databank"', 'applicationId "com.ifrc.databank"' | Set-Content android/app/build.gradle
    
    # iOS
    (Get-Content ios/Runner.xcodeproj/project.pbxproj) -replace 'PRODUCT_BUNDLE_IDENTIFIER = com\.ngo\.databank', 'PRODUCT_BUNDLE_IDENTIFIER = com.ifrc.databank' | Set-Content ios/Runner.xcodeproj/project.pbxproj
    (Get-Content ios/Runner.xcodeproj/project.pbxproj) -replace 'PRODUCT_BUNDLE_IDENTIFIER = com\.ngo\.databank\.RunnerTests', 'PRODUCT_BUNDLE_IDENTIFIER = com.ifrc.databank.RunnerTests' | Set-Content ios/Runner.xcodeproj/project.pbxproj
    
    Write-Host "Bundle identifier set to IFRC"
} else {
    # Android
    (Get-Content android/app/build.gradle) -replace 'namespace "com\.ifrc\.databank"', 'namespace "com.ngo.databank"' | Set-Content android/app/build.gradle
    (Get-Content android/app/build.gradle) -replace 'applicationId "com\.ifrc\.databank"', 'applicationId "com.ngo.databank"' | Set-Content android/app/build.gradle
    
    # iOS
    (Get-Content ios/Runner.xcodeproj/project.pbxproj) -replace 'PRODUCT_BUNDLE_IDENTIFIER = com\.ifrc\.databank', 'PRODUCT_BUNDLE_IDENTIFIER = com.ngo.databank' | Set-Content ios/Runner.xcodeproj/project.pbxproj
    (Get-Content ios/Runner.xcodeproj/project.pbxproj) -replace 'PRODUCT_BUNDLE_IDENTIFIER = com\.ifrc\.databank\.RunnerTests', 'PRODUCT_BUNDLE_IDENTIFIER = com.ngo.databank.RunnerTests' | Set-Content ios/Runner.xcodeproj/project.pbxproj
    
    Write-Host "Bundle identifier set to NGO Databank (default)"
}
```

**Usage:**
```powershell
# Set to IFRC
.\scripts\set-bundle-id.ps1 -Org ifrc

# Set to NGO (default)
.\scripts\set-bundle-id.ps1 -Org ngo
```

## For Play Store / App Store

### Play Store (Android)
- **Default (NGO Databank):** Use `com.ngo.databank`
- **IFRC:** Use `com.ifrc.databank` (requires separate Play Store listing)

### App Store (iOS)
- **Default (NGO Databank):** Use `com.ngo.databank`
- **IFRC:** Use `com.ifrc.databank` (requires separate App Store listing)

## Important Notes

1. **Bundle identifier must be unique** - You cannot publish two apps with the same bundle identifier
2. **Changing bundle identifier** creates a new app in the stores - it's treated as a different app
3. **For testing** - You can install both versions side-by-side if they have different bundle identifiers
4. **Organization config** - The `packageName` in `organization_config.json` should match the bundle identifier you're using

## Verification

After changing bundle identifiers, verify:

### Android
```bash
# Check build.gradle
grep -n "applicationId" android/app/build.gradle
grep -n "namespace" android/app/build.gradle
```

### iOS
```bash
# Check project.pbxproj
grep -n "PRODUCT_BUNDLE_IDENTIFIER" ios/Runner.xcodeproj/project.pbxproj
```

## Current Status

✅ **Default:** `com.ngo.databank` (for Play Store publication)
✅ **IFRC:** `com.ifrc.databank` (for IFRC-specific builds)
