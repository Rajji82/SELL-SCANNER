package com.smartcapital.sellscanner;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.net.Uri;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.net.URL;
import java.util.Locale;

public final class MainActivity extends Activity {
    private static final int NAVY = Color.rgb(10, 17, 30);
    private static final int PANEL = Color.rgb(24, 35, 53);
    private static final int CYAN = Color.rgb(56, 189, 248);
    private String baseUrl = "";
    private ScrollView setupScreen;
    private EditText serverField;
    private TextView feedback, serverStatus;
    private WebView web;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(NAVY);
        getWindow().setNavigationBarColor(NAVY);
        createScreen();
        String last = getPreferences(MODE_PRIVATE).getString("url", "");
        serverField.setText(last);
        if (last.isEmpty()) showSetup("Enter your running scanner backend address.");
        else connect(last);
    }

    private void createScreen() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(NAVY);
        setContentView(root);
        LinearLayout top = new LinearLayout(this);
        top.setGravity(Gravity.CENTER_VERTICAL);
        top.setPadding(dp(12), dp(5), dp(12), dp(5));
        top.setBackgroundColor(PANEL);
        root.addView(top, new LinearLayout.LayoutParams(-1, dp(57)));
        TextView brand = new TextView(this);
        brand.setText("SMART CAPITAL  •  PAPER MODE");
        brand.setTextColor(Color.WHITE);
        brand.setTextSize(13);
        brand.setTypeface(null, 1);
        top.addView(brand, new LinearLayout.LayoutParams(0, -2, 1));
        Button server = button("SERVER");
        top.addView(server, new LinearLayout.LayoutParams(dp(95), dp(44)));
        server.setOnClickListener(v -> showSetup("Update the server URL and reconnect."));
        serverStatus = paragraph("Prototype / paper trading only");
        serverStatus.setTextColor(CYAN);
        serverStatus.setSingleLine(true);
        serverStatus.setPadding(dp(12), dp(6), dp(12), dp(6));
        root.addView(serverStatus, new LinearLayout.LayoutParams(-1, dp(29)));

        setupScreen = new ScrollView(this);
        setupScreen.setFillViewport(true);
        root.addView(setupScreen, new LinearLayout.LayoutParams(-1, 0, 1));
        LinearLayout setup = new LinearLayout(this);
        setup.setOrientation(LinearLayout.VERTICAL);
        setup.setPadding(dp(22), dp(25), dp(22), dp(25));
        setupScreen.addView(setup);
        TextView title = paragraph("SELL SCANNER\nANDROID");
        title.setTextSize(28);
        title.setTextColor(Color.WHITE);
        title.setTypeface(null, 1);
        setup.addView(title);
        TextView sub = paragraph("Personal test build. Connects to your existing SELL-SCANNER FastAPI dashboard.");
        sub.setPadding(0, dp(15), 0, dp(25));
        setup.addView(sub);
        TextView label = paragraph("BACKEND ADDRESS");
        label.setTextColor(CYAN);
        setup.addView(label);
        serverField = new EditText(this);
        serverField.setSingleLine(true);
        serverField.setTextSize(16);
        serverField.setTextColor(Color.WHITE);
        serverField.setHintTextColor(Color.LTGRAY);
        serverField.setHint("http://192.168.1.100:8000");
        serverField.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        serverField.setBackgroundTintList(ColorStateList.valueOf(CYAN));
        setup.addView(serverField, new LinearLayout.LayoutParams(-1, dp(55)));
        Button connect = button("OPEN DASHBOARD");
        LinearLayout.LayoutParams bParams = new LinearLayout.LayoutParams(-1, dp(51));
        bParams.topMargin = dp(18);
        setup.addView(connect, bParams);
        connect.setOnClickListener(v -> connect(serverField.getText().toString()));
        feedback = paragraph("");
        feedback.setPadding(0, dp(17), 0, dp(13));
        setup.addView(feedback);
        TextView guide = paragraph(
            "SETUP\n" +
            "1. Run the Python scanner backend on your computer.\n" +
            "2. Use the same trusted Wi-Fi on PC and Android.\n" +
            "3. Enter the PC LAN IP with port 8000.\n\n" +
            "SAFETY\n" +
            "Only paper trading is supported. Do not store broker API keys, PINs, or TOTP secrets in the Android app. " +
            "This APK does not fix backend bugs or enable real order placement.");
        guide.setPadding(0, dp(14), 0, 0);
        setup.addView(guide);

        web = new WebView(this);
        web.setVisibility(View.GONE);
        root.addView(web, new LinearLayout.LayoutParams(-1, 0, 1));
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        if (Build.VERSION.SDK_INT >= 26) settings.setSafeBrowsingEnabled(true);
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (sameOrigin(uri)) return false;
                if ("https".equalsIgnoreCase(uri.getScheme())) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); }
                    catch (ActivityNotFoundException ignored) { }
                }
                return true;
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) showSetup("Cannot reach the backend. Check scanner.py, IP, port and Wi-Fi.");
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (web.getVisibility() == View.VISIBLE) serverStatus.setText("Server: " + baseUrl);
            }
        });
    }

    private boolean sameOrigin(Uri uri) {
        try {
            URL curr = new URL(baseUrl);
            int portA = curr.getPort() < 0 ? curr.getDefaultPort() : curr.getPort();
            int portB = uri.getPort() < 0 ? ("https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80) : uri.getPort();
            return curr.getProtocol().equalsIgnoreCase(uri.getScheme())
                && curr.getHost().equalsIgnoreCase(uri.getHost()) && portA == portB;
        } catch (Exception ignored) { return false; }
    }

    private void connect(String candidate) {
        try {
            URL u = new URL(candidate.trim());
            String scheme = u.getProtocol().toLowerCase(Locale.US);
            String host = u.getHost();
            if (!scheme.equals("https") && !scheme.equals("http"))
                throw new IllegalArgumentException("Use http or https.");
            if (host.isEmpty()) throw new IllegalArgumentException("Missing hostname.");
            if (u.getUserInfo() != null || u.getQuery() != null || u.getRef() != null
                    || (!u.getPath().isEmpty() && !"/".equals(u.getPath())))
                throw new IllegalArgumentException("Use a server base URL without path, password or query.");
            if (scheme.equals("http") && !privateIp(host))
                throw new IllegalArgumentException("Use HTTP only with a private LAN IP. Remote servers must use HTTPS.");
            baseUrl = scheme + "://" + u.getAuthority();
            getPreferences(MODE_PRIVATE).edit().putString("url", baseUrl).apply();
            serverField.setText(baseUrl);
            setupScreen.setVisibility(View.GONE);
            web.setVisibility(View.VISIBLE);
            serverStatus.setText("Connecting: " + baseUrl);
            web.loadUrl(baseUrl + "/");
        } catch (Exception ex) {
            showSetup("Server address error: " + ex.getMessage());
        }
    }

    private static boolean privateIp(String host) {
        String name = host.toLowerCase(Locale.US);
        if (name.equals("localhost") || name.equals("127.0.0.1") || name.equals("10.0.2.2")) return true;
        String[] v = name.split("\\.");
        if (v.length != 4) return false;
        try {
            int[] a = new int[4];
            for (int i = 0; i < 4; ++i) {
                a[i] = Integer.parseInt(v[i]);
                if (a[i] < 0 || a[i] > 255) return false;
            }
            return a[0] == 10 || (a[0] == 192 && a[1] == 168)
                || (a[0] == 172 && a[1] >= 16 && a[1] <= 31);
        } catch (NumberFormatException err) { return false; }
    }

    private void showSetup(String message) {
        if (setupScreen == null) return;
        web.setVisibility(View.GONE);
        setupScreen.setVisibility(View.VISIBLE);
        feedback.setText(message);
        serverStatus.setText("Prototype / paper trading only");
    }

    private TextView paragraph(String value) {
        TextView t = new TextView(this);
        t.setText(value);
        t.setTextSize(14);
        t.setTextColor(Color.rgb(190, 202, 218));
        t.setLineSpacing(dp(3), 1);
        return t;
    }

    private Button button(String value) {
        Button b = new Button(this);
        b.setText(value);
        b.setTextSize(11);
        b.setAllCaps(false);
        b.setTextColor(NAVY);
        b.setBackgroundTintList(ColorStateList.valueOf(CYAN));
        return b;
    }

    private int dp(int size) {
        return Math.round(size * getResources().getDisplayMetrics().density);
    }

    @Override public void onBackPressed() {
        if (web.getVisibility() == View.VISIBLE && web.canGoBack()) web.goBack();
        else showSetup("Enter or update the backend server address.");
    }

    @Override protected void onDestroy() {
        web.destroy();
        super.onDestroy();
    }
}
