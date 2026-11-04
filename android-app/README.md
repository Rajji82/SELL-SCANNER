# Smart Capital SELL-SCANNER Android v0.1

An installable personal test Android app for the existing SELL-SCANNER
FastAPI dashboard. This app loads your server over HTTPS or a trusted
local LAN. It is NOT a standalone scanner or a live-trading application.

## Get an APK
GitHub Actions -> Android Debug APK -> newest successful run -> Artifacts ->
SmartCapital-SellScanner-debug-apk -> download ZIP -> extract app-debug.apk.
This debug-signed APK is suitable for personal testing, not Play Store release.

## Run backend on Windows
Install the Python requirements and start the server from the project folder:

    python -m uvicorn scanner:app --host 0.0.0.0 --port 8000

Run ipconfig to find your computer's LAN IPv4 address. Connect the Android
device and PC to the same trusted Wi-Fi. Enter this address into the app:
    http://192.168.1.100:8000
Replace the example IP with your actual computer IP. Android's 127.0.0.1
is the phone, not your PC. Permit firewall port 8000 on private networks
only. Do NOT expose this unaudited backend to the public internet.

## Build locally
Open android-app in Android Studio and select Build -> Build APK(s).
Or run gradle -p android-app assembleDebug using JDK 17 and Android SDK 35.
Output: android-app/app/build/outputs/apk/debug/app-debug.apk.

## Limitations and safety
- Requires backend running separately. No offline market data.
- Does not place real orders, add auto-trading, or run Python on Android.
- Existing deadlock, missing endpoints and risk defects are not fixed.
- No broker API keys, TOTP secrets, PINs or app tokens are bundled.
- WebView only loads the configured origin; JavaScript is enabled.
- SSL errors are not bypassed. Plain HTTP limited to local IPv4 networks.
- Use paper trading; rotate previously exposed .env credentials immediately.
