# Google Play Store Publication Guide

Complete step-by-step guide to publish the IFRC Network Databank app to Google Play Store.

## Prerequisites Checklist

- ✅ Google Play Console account created ($25 paid)
- ✅ App bundle (AAB) built and ready
- ✅ App icon (512x512 PNG)
- ✅ Screenshots (at least 2, up to 8)
- ✅ Feature graphic (1024x500 PNG) - optional but recommended
- ✅ Privacy policy URL: `https://website-databank.fly.dev/privacy-policy`
- ✅ App description (short: 80 chars, full: 4000 chars)

---

## Step 1: Prepare Release Build

### 1.1 Update Version Number

Before building, update the version in `pubspec.yaml`:

```yaml
version: 1.0.0+1
```

Format: `MAJOR.MINOR.PATCH+BUILD_NUMBER`
- First part (1.0.0): Version name (shown to users)
- Second part (+1): Version code (internal, must increment each release)

**For your first release, you can keep `1.0.0+1`**

### 1.2 Build App Bundle (AAB)

**Important:** Google Play Store requires AAB format, NOT APK.

Navigate to the MobileApp directory and run:

```bash
cd MobileApp
flutter build appbundle --release --dart-define=PRODUCTION=true
```

**Output location:**
```
build/app/outputs/bundle/release/app-release.aab
```

### 1.3 Verify Build

- ✅ File size should be reasonable (typically 10-50 MB)
- ✅ File extension is `.aab` (not `.apk`)
- ✅ Build completed without errors

---

## Step 2: Prepare Store Assets

### 2.1 App Icon
- **Size:** 512x512 pixels
- **Format:** PNG (no transparency)
- **Location:** Should already be at `assets/images/app_icon.png`

### 2.2 Screenshots
**Required:** At least 2 screenshots
**Recommended:** 4-8 screenshots

**Sizes needed:**
- **Phone:** 16:9 or 9:16 aspect ratio
  - Minimum: 320px
  - Maximum: 3840px
  - Recommended: 1080x1920 (portrait) or 1920x1080 (landscape)

**Screenshot ideas:**
1. Login screen
2. Dashboard/Home screen
3. Settings screen
4. Notifications screen
5. Data visualization (if applicable)

**How to take screenshots:**
```bash
# Run app on emulator or device
flutter run --dart-define=PRODUCTION=true

# Take screenshots using:
# - Android Studio: Tools > Device Manager > Screenshot
# - Emulator: Click camera icon in toolbar
# - Physical device: Use device screenshot feature
```

### 2.3 Feature Graphic (Optional but Recommended)
- **Size:** 1024x500 pixels
- **Format:** PNG or JPG
- **Purpose:** Displayed at top of Play Store listing

### 2.4 App Description

**Short Description (80 characters max):**
```
IFRC Network Databank - Humanitarian data management for Red Cross network
```

**Full Description (4000 characters max):**
```
The IFRC Network Databank Mobile Application is a comprehensive tool for managing humanitarian data within the International Federation of Red Cross and Red Crescent Societies (IFRC) network.

KEY FEATURES:

• Native Authentication
  - Secure email/password login
  - Azure AD B2C single sign-on support
  - Session management with automatic refresh

• Dashboard & Assignments
  - View current and past assignments
  - Track entities and activities
  - Real-time data synchronization

• Push Notifications
  - Receive important updates and alerts
  - Unread notification counts
  - Customizable notification preferences

• Offline Support
  - Work without internet connection
  - Automatic request queuing
  - Smart caching for offline access
  - Automatic sync when connection restored

• WebView Integration
  - Seamless access to complex backend pages
  - Template management
  - Assignment management
  - Form builder and data entry

• User Settings
  - Edit profile (name, job title)
  - Customize profile color
  - Toggle chatbot assistance
  - Dark theme support
  - Multi-language support (English, Spanish, French, Arabic, Hindi, Russian, Chinese)

• Security Features
  - Secure session management
  - Encrypted local storage
  - URL whitelist validation
  - Content Security Policy enforcement

• Performance
  - Fast startup times
  - Optimized data loading
  - Efficient offline caching

This app is designed exclusively for authorized IFRC network users, including IFRC Secretariat staff and National Red Cross and Red Crescent Societies.

For support or questions, please contact: haythamsoufi@outlook.com
```

---

## Step 3: Create App in Play Console

### 3.1 Access Play Console
1. Go to [Google Play Console](https://play.google.com/console)
2. Sign in with your developer account

### 3.2 Create New App
1. Click **"Create app"** button
2. Fill in the form:
   - **App name:** `IFRC Network Databank`
   - **Default language:** English (United States)
   - **App or game:** App
   - **Free or paid:** Free (or Paid if applicable)
   - **Declarations:** Check all required boxes
3. Click **"Create app"**

---

## Step 4: Complete App Information

### 4.1 App Access
1. Go to **Policy > App access**
2. Select: **"All or some functionality is restricted"** (since it's for IFRC network only)
   - Or select **"No restrictions"** if you want it publicly available
3. Save

### 4.2 Privacy Policy
1. Go to **Policy > Privacy policy**
2. Enter URL: `https://website-databank.fly.dev/privacy-policy`
3. Save

### 4.3 Content Rating
1. Go to **Policy > Content rating**
2. Click **"Start questionnaire"**
3. Answer questions about your app:
   - **Category:** Productivity / Business
   - **Does your app contain user-generated content?** No
   - **Does your app allow users to communicate?** Yes (internal network)
   - **Does your app allow users to share location?** Possibly (if applicable)
   - Continue answering all questions
4. Submit questionnaire
5. Wait for rating (usually instant)

---

## Step 5: Set Up Store Listing

### 5.1 Main Store Listing
1. Go to **Store presence > Main store listing**

2. **App name:** `IFRC Network Databank`

3. **Short description (80 chars):**
   ```
   IFRC Network Databank - Humanitarian data management for Red Cross network
   ```

4. **Full description (4000 chars):**
   - Paste the full description from Step 2.4

5. **App icon:**
   - Upload 512x512 PNG icon

6. **Feature graphic (optional):**
   - Upload 1024x500 PNG (if you have one)

7. **Screenshots:**
   - Upload at least 2 phone screenshots
   - Drag to reorder (first screenshot is most important)

8. **Contact details:**
   - **Email:** haythamsoufi@outlook.com
   - **Phone:** (optional)
   - **Website:** https://website-databank.fly.dev

9. **Save draft**

### 5.2 Categorization
1. Go to **Store presence > Categorization**
2. **App category:** Productivity (or Business)
3. **Tags:** Add relevant tags (e.g., "humanitarian", "data management", "non-profit")

---

## Step 6: Upload App Bundle

### 6.1 Create Release
1. Go to **Production > Releases** (or **Testing > Internal testing** for testing first)
2. Click **"Create new release"**

### 6.2 Upload AAB
1. Under **"App bundles"**, click **"Upload"**
2. Select your AAB file: `build/app/outputs/bundle/release/app-release.aab`
3. Wait for upload to complete (may take a few minutes)

### 6.3 Release Notes
Enter release notes for users:
```
Initial release of IFRC Network Databank Mobile App

Features:
- User authentication and profile management
- Dashboard with assignments and entities
- Push notifications
- Offline support with automatic sync
- Multi-language support
- Dark theme
```

### 6.4 Review Release
1. Review the release information
2. Check that version code matches (should be 1 for first release)
3. Click **"Save"** (don't publish yet if you want to test first)

---

## Step 7: Testing (Recommended Before Production)

### 7.1 Internal Testing
1. Go to **Testing > Internal testing**
2. Upload the same AAB to internal testing track
3. Add testers (your email addresses)
4. Share testing link with testers
5. Test the app thoroughly

### 7.2 Fix Issues
- If you find issues, fix them, increment version code, rebuild, and upload again

---

## Step 8: Complete Required Forms

### 8.1 Data Safety
1. Go to **Policy > Data safety**
2. Click **"Start"** or **"Edit"**
3. Answer questions about data collection:
   - **Does your app collect or share personal data?** Yes
   - **Data types collected:**
     - ✅ Email address
     - ✅ Name
     - ✅ Device ID
     - ✅ App activity
     - ✅ App info and performance (crash logs)
   - **Why is this data collected?**
     - App functionality
     - Analytics
     - Developer communications
   - **Is data encrypted?** Yes
   - **Can users request deletion?** Yes
4. Save

### 8.2 Target Audience
1. Go to **Policy > Target audience**
2. Select appropriate age range
3. Answer content questions

---

## Step 9: Review and Publish

### 9.1 Pre-Launch Checklist
- ✅ App bundle uploaded
- ✅ Store listing complete
- ✅ Screenshots uploaded
- ✅ Privacy policy URL added
- ✅ Content rating completed
- ✅ Data safety form completed
- ✅ App tested (recommended)

### 9.2 Submit for Review
1. Go to **Production > Releases**
2. Find your release
3. Click **"Review release"**
4. Review all information
5. Click **"Start rollout to Production"**
6. Confirm submission

### 9.3 Review Process
- **Timeline:** Usually 1-3 days (can be up to 7 days)
- **Status:** Check Play Console for updates
- **Notifications:** You'll receive email updates

### 9.4 After Approval
- App will be live on Play Store
- Users can download and install
- Monitor reviews and ratings
- Respond to user feedback

---

## Step 10: Post-Publication

### 10.1 Monitor
- Check Play Console dashboard for:
  - Downloads
  - Ratings and reviews
  - Crashes and ANRs (Application Not Responding)
  - User feedback

### 10.2 Update App
When you need to update:
1. Increment version in `pubspec.yaml`:
   ```yaml
   version: 1.0.1+2  # Increment both parts
   ```
2. Rebuild AAB:
   ```bash
   flutter build appbundle --release --dart-define=PRODUCTION=true
   ```
3. Upload new AAB to Play Console
4. Add release notes
5. Submit for review

---

## Quick Command Reference

```bash
# Navigate to app directory
cd MobileApp

# Build production AAB
flutter build appbundle --release --dart-define=PRODUCTION=true

# Output location
# build/app/outputs/bundle/release/app-release.aab

# Clean build (if needed)
flutter clean
flutter pub get
flutter build appbundle --release --dart-define=PRODUCTION=true
```

---

## Troubleshooting

### Build Errors
- Run `flutter clean` and rebuild
- Check Flutter version: `flutter --version`
- Verify all dependencies: `flutter pub get`

### Upload Errors
- Ensure AAB file is not corrupted
- Check file size (should be reasonable)
- Verify version code is unique and incremented

### Review Rejection
- Read rejection reason carefully
- Fix issues mentioned
- Resubmit with updated version

---

## Important Notes

1. **Version Code:** Must always increment (1, 2, 3, ...)
2. **Privacy Policy:** Must be publicly accessible
3. **Testing:** Highly recommended to test in internal track first
4. **Review Time:** Can take 1-7 days
5. **Updates:** Can take same review time

---

## Support

If you encounter issues:
- Check [Google Play Console Help](https://support.google.com/googleplay/android-developer)
- Review [Flutter Deployment Guide](https://docs.flutter.dev/deployment/android)

Good luck with your publication! 🚀
