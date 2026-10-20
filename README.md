# Chess vs FruityFly, Mobile App Packaging

Everything needed to ship the chess game as native iOS and Android apps using
[Capacitor](https://capacitorjs.com). The game itself is a single self-contained
web file; the native shells wrap it.

- App name: **Chess vs FruityFly**
- App ID (both stores): **com.chessfruitfly.game**
- Web asset: `www/index.html` (currently the Oct 19 game build)

## Refreshing the game build

The friends feature (and any future game change) ships to mobile by replacing
ONE file, then re-syncing:

```bash
cp /path/to/latest-export.html www/index.html
npx cap sync
```

`npx cap sync` copies `www/` into both native projects. Never edit the copies
under `ios/App/App/public/` or `android/app/src/main/assets/` directly.

## Project layout

```
chess-mobile/
  www/index.html              the game (replace to refresh)
  capacitor.config.ts         app id, name, splash config
  android/                    native Android project (Capacitor)
  ios/                        native iOS project (Capacitor)
  assets/                     master icon artwork
  tools/generate_icons.py      regenerates all icons/splash from the master
  keystore/                   Android upload keystore (KEEP SAFE, see below)
  .github/workflows/          CI builds for Android (AAB) and iOS (IPA)
  store-listing-ios.md        App Store listing text
  store-listing-android.md    Google Play listing text
  privacy-policy.html/.md     privacy policy (also host at chessfruitfly.com/privacy-policy.html)
```

---

## PART 1: YOU MUST DO (needs your identity, Muse cannot do these)

### A. Apple Developer Program, $99/year

1. Enroll at https://developer.apple.com/programs/enroll/ (individual account,
   identity verified by Apple; only you can do this).
2. In Xcode or at https://developer.apple.com/account:
   - Create an **App ID** for `com.chessfruitfly.game` with no special
     capabilities.
   - Create an **Apple Distribution certificate**: Xcode > Settings > Accounts >
     Manage Certificates > plus button > Apple Distribution. Then in Keychain
     Access, export it as `.p12` (you set a password, save it).
   - Create an **App Store provisioning profile** for the App ID at
     Certificates, Identifiers & Profiles > Profiles > plus > App Store.
     Download the `.mobileprovision` file.
3. Note your **Team ID**: developer.apple.com/account > Membership, 10 characters.
4. In App Store Connect (https://appstoreconnect.apple.com), create the app
   record: name "Chess vs FruityFly", bundle ID `com.chessfruitfly.game`,
   paste the listing from `store-listing-ios.md`, upload the 1024px icon
   (`ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png`),
   set the privacy policy URL to https://chessfruitfly.com/privacy-policy.html,
   and fill in the App Privacy questionnaire (data collected: email address and
   gameplay data via Firebase; see privacy-policy.md).

### B. Google Play Developer, $25 one-time

1. Register at https://play.google.com/console/signup (identity verified by
   Google; only you can do this).
2. Create the app: name "Chess vs FruityFly", package `com.chessfruitfly.game`,
   category Board.
3. Upload the signed `app-release.aab` (built below or via the CI workflow).
4. Paste the listing from `store-listing-android.md`, set the privacy policy
   URL to https://chessfruitfly.com/privacy-policy.html, complete the content
   rating questionnaire and the Data Safety form (data collected: email
   address, gameplay/app activity via Firebase and Analytics; nothing sold).

### C. Add CI secrets, then run the builds

Push this folder to a GitHub repo (suggested name `chessfruitfly-mobile`, repo
root = this folder), then add these secrets under repo Settings > Secrets and
variables > Actions. Generate the base64 values with:

```bash
base64 -w0 <file>   # Linux; on macOS use: base64 -i <file>
```

| Secret | Value | Where it comes from |
|---|---|---|
| `APPLE_TEAM_ID` | 10-char Team ID | developer.apple.com > Membership |
| `IOS_CERT_P12_B64` | base64 of your `.p12` | Keychain Access export (step A2) |
| `IOS_CERT_PASSWORD` | the `.p12` password | chosen by you at export |
| `IOS_PROVISION_PROFILE_B64` | base64 of `.mobileprovision` | developer.apple.com (step A2) |
| `ANDROID_KEYSTORE_B64` | base64 of `keystore/chessfruitfly-upload.keystore` | already in this folder |
| `ANDROID_KEYSTORE_PASSWORD` | keystore password | `keystore/.store-pass` (this machine) |
| `ANDROID_KEY_ALIAS` | `chessfruitfly` | fixed at creation |
| `ANDROID_KEY_PASSWORD` | key password | `keystore/.store-pass` (this machine) |

Then run the workflows from the repo's Actions tab: **Android build** produces
`app-release.aab`, **iOS build** produces the signed `.ipa`.

### D. Upload and submit

- iOS: upload the IPA to App Store Connect (Transporter app or
  `xcrun altool`), attach it to your app version, submit for review.
- Android: upload the AAB to Play Console > Production, submit for review.

---

## PART 2: ALREADY DONE

- Capacitor project scaffolded (`@capacitor/core`, `cli`, `ios`, `android`),
  app id `com.chessfruitfly.game`, name "Chess vs FruityFly".
- Web asset bundled locally: `www/index.html` is the full game, so vs-AI and
  local 2-player work offline. Firebase features (auth, online rooms, friends)
  need network, which the apps have.
- App icons: generated from `assets/` master artwork (chess knight + fruit fly),
  full iOS AppIcon set incl. 1024px, Android legacy + adaptive icons (foreground
  + gradient background sampled from the artwork).
- Splash screens: Android `drawable/splash.xml` (dark `#1a1a2e` + centered
  logo), iOS `Splash.imageset` (2732px, same branding). Wired in
  `capacitor.config.ts`.
- Release signing wired in `android/app/build.gradle` via
  `android/keystore.properties` (gitignored; see `.example` file).
- Android upload keystore created at `keystore/chessfruitfly-upload.keystore`
  (RSA 2048, validity 10000 days). **Back this file up somewhere safe.** If it
  is lost, future app updates require a key reset through Play Console.
- CI workflows: `.github/workflows/android.yml` and `ios.yml`, fully working
  from a repo checkout.

## Local build commands (reference)

**Status:** The Android release AAB was successfully built in this environment
on Oct 20, 2026: `android/app/build/outputs/bundle/release/app-release.aab`
(3.2 MB, signed with the upload keystore). The iOS build requires a Mac and
is handled by the CI workflow.

```bash
cd chess-mobile
npm ci
npx cap sync                 # copy www/ into native projects

# Android release AAB (needs JDK 21 + Android SDK, ANDROID_HOME set):
cp android/keystore.properties.example android/keystore.properties
# fill in passwords, then:
cd android && ./gradlew bundleRelease --no-daemon
# -> android/app/build/outputs/bundle/release/app-release.aab

# iOS (needs a Mac with Xcode; use the CI workflow otherwise):
cd ios/App && pod install
# open ios/App/App.xcworkspace in Xcode, select the App scheme,
# Product > Archive with your Team selected.
```

## Security notes

- The mobile apps talk to the same Firebase project and are covered by the
  same Realtime Database security rules as the web game.
- For store review you will be asked about data collection; the answers are in
  `privacy-policy.md` (account email, gameplay data, friend codes/presence,
  aggregated analytics; nothing sold, deletion on request).
- `keystore/.store-pass` and `android/keystore.properties` are gitignored and
  must never be committed. In CI they come from GitHub Secrets.
