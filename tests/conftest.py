import os

# Testconfiguratie vóór app.config geïmporteerd wordt (overschrijft een lokale .env).
os.environ.update(
    {
        "ENTRA_CLIENT_ID": "test-client-id",
        "ENTRA_CLIENT_SECRET": "test-client-secret",
        "ENTRA_AUTHORITY": "organizations",
        "ENTRA_REDIRECT_URI": "http://testserver/auth/callback",
        "ENTRA_POST_LOGOUT_URI": "http://testserver/auth/logged-out",
        "ENTRA_ALLOWED_TENANTS": "de5dcc4b-b4d4-4eca-8851-2cb8bdd62c7b,0d2411fc-02b6-455e-86db-122a475d9273",
        "ENTRA_ALLOWED_EMAILS": "",
        "SESSION_SECRET": "test-session-secret",
        "SESSION_HTTPS_ONLY": "false",
        "FRONTEND_URL": "/",
        "DEV_LOGIN_EMAIL": "",
        "GEMINI_API_KEY": "",
        # Poort 1 op localhost: bestaat niet, dus de tests raken nooit een echte database.
        "DATABASE_URL": "postgresql://test:test@127.0.0.1:1/test?connect_timeout=1",
    }
)
