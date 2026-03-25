# Android Release Signing Setup

This guide will help you set up release signing for your Android app bundle so it can be uploaded to Google Play Console.

## Problem

If you get the error: "You uploaded an APK or Android App Bundle that was signed in debug mode", it means your app bundle is using the debug signing key instead of a release signing key.

## Solution

You need to:
1. Generate a keystore file (or use an existing one)
2. Create a `key.properties` file with your keystore information
3. Rebuild your app bundle

---

## Step 1: Generate a Keystore

If you don't already have a keystore, generate one using Java's `keytool` command:

```bash
keytool -genkey -v -keystore ~/upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload
```

**Important:** Replace `~/upload-keystore.jks` with your desired keystore path and `upload` with your desired alias name.

**You'll be prompted for:**
- Keystore password (remember this!)
- Key password (can be same as keystore password)
- Your name, organizational unit, organization, city, state, and country code

**Example on Windows:**

If `keytool` is not in your PATH, use the full path:
```powershell
# Option 1: Use full path to keytool
& "C:\Program Files\Java\jre-1.8\bin\keytool.exe" -genkey -v -keystore android\keystore\upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload

# Option 2: Add Java bin to PATH for this session
$env:Path += ";C:\Program Files\Java\jre-1.8\bin"
keytool -genkey -v -keystore android\keystore\upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload
```

**Note:** The exact path may vary depending on your Java installation. Common locations:
- `C:\Program Files\Java\jre-1.8\bin\keytool.exe` (JRE)
- `C:\Program Files\Java\jdk-*\bin\keytool.exe` (JDK)

**Example on macOS/Linux:**
```bash
keytool -genkey -v -keystore ~/upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload
```

**⚠️ CRITICAL:** 
- Keep your keystore file safe and backed up!
- If you lose the keystore or forget the password, you won't be able to update your app on Google Play Store
- Store it in a secure location
- Consider using a password manager to store the passwords

---

## Step 2: Create key.properties File

1. Navigate to `MobileApp/android/` directory
2. Create a file named `key.properties` (copy from `key.properties.example` as a template)
3. Add the following content (replace with your actual values):

```properties
storePassword=YOUR_KEYSTORE_PASSWORD
keyPassword=YOUR_KEY_PASSWORD
keyAlias=upload
storeFile=../keystore/upload-keystore.jks
```

**Important notes:**
- `storePassword`: The password you set for the keystore file
- `keyPassword`: The password for the key alias (can be same as storePassword)
- `keyAlias`: The alias you used when generating the keystore (e.g., "upload")
- `storeFile`: Path to your keystore file, relative to the `android` directory

**Example if keystore is in `android/keystore/upload-keystore.jks`:**
```properties
storePassword=mySecurePassword123
keyPassword=mySecurePassword123
keyAlias=upload
storeFile=keystore/upload-keystore.jks
```

**Example if keystore is in your home directory on Linux/Mac:**
```properties
storePassword=mySecurePassword123
keyPassword=mySecurePassword123
keyAlias=upload
storeFile=/Users/yourusername/upload-keystore.jks
```

**Example if keystore is in a specific location on Windows:**
```properties
storePassword=mySecurePassword123
keyPassword=mySecurePassword123
keyAlias=upload
storeFile=C:/IFRC Network Databank/MobileApp/android/keystore/upload-keystore.jks
```

---

## Step 3: Verify Setup

Your directory structure should look like this:

```
MobileApp/
  android/
    key.properties          ← Your keystore configuration (NOT in git)
    key.properties.example  ← Template (in git)
    keystore/               ← Your keystore directory (create if needed)
      upload-keystore.jks   ← Your keystore file (NOT in git)
    app/
      build.gradle          ← Updated with signing config
```

---

## Step 4: Build Release App Bundle

Now rebuild your app bundle with release signing:

```bash
cd MobileApp
flutter build appbundle --release --dart-define=PRODUCTION=true
```

The build will use your release keystore automatically.

---

## Step 5: Verify the Bundle

After building, verify that the bundle is properly signed:

```bash
# On Windows (PowerShell)
jarsigner -verify -verbose -certs build\app\outputs\bundle\release\app-release.aab

# On macOS/Linux
jarsigner -verify -verbose -certs build/app/outputs/bundle/release/app-release.aab
```

You should see output indicating the bundle is signed (not debug).

---

## Troubleshooting

### Build fails with "signingConfig signingConfigs.release is not configured"

- Make sure `key.properties` file exists in `MobileApp/android/` directory
- Check that all paths in `key.properties` are correct
- Verify the keystore file exists at the specified path

### Build fails with "Keystore was tampered with, or password was incorrect"

- Double-check your passwords in `key.properties`
- Verify the keystore file path is correct
- Make sure you're using the correct keystore file

### "jarsigner: unable to open jar file"

- Make sure you've built the bundle first (`flutter build appbundle`)
- Check the path to your `.aab` file

---

## Security Best Practices

1. **Never commit `key.properties` or keystore files to git**
   - They are already in `.gitignore`
   - Keep them secure and backed up separately

2. **Store keystore passwords securely**
   - Use a password manager
   - Consider using environment variables for CI/CD (see below)

3. **Back up your keystore**
   - Store it in multiple secure locations
   - If you lose it, you'll need to create a new app on Play Store

4. **Use different keystores for different environments**
   - Development/testing can use debug signing
   - Production must use release signing

---

## For CI/CD (GitHub Actions, etc.)

If you need to sign builds in CI/CD, store the keystore and passwords as secrets and create `key.properties` during the build:

```yaml
- name: Create key.properties
  run: |
    echo "storePassword=${{ secrets.KEYSTORE_PASSWORD }}" > android/key.properties
    echo "keyPassword=${{ secrets.KEY_PASSWORD }}" >> android/key.properties
    echo "keyAlias=${{ secrets.KEY_ALIAS }}" >> android/key.properties
    echo "storeFile=${{ secrets.KEYSTORE_PATH }}" >> android/key.properties
```

---

## Additional Resources

- [Flutter Android Deployment Guide](https://docs.flutter.dev/deployment/android)
- [Google Play App Signing](https://support.google.com/googleplay/android-developer/answer/9842756)
