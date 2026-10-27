import pytest
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from joserfc.errors import InvalidClaimError

from app.auth import is_valid_issuer, oauth
from app.config import settings
from app.main import app

AZ_DELTA = "0d2411fc-02b6-455e-86db-122a475d9273"
OTHER = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def client():
    return TestClient(app, follow_redirects=False)


def fake_token(monkeypatch, userinfo=None, exc=None):
    """Vervangt de token-uitwisseling met Microsoft (geen netwerk)."""

    async def authorize_access_token(request, **kwargs):
        assert kwargs["claims_options"]["iss"]["validate"] is is_valid_issuer
        if exc:
            raise exc
        return {"userinfo": userinfo}

    monkeypatch.setattr(oauth.entra, "authorize_access_token", authorize_access_token)


def user(tid=AZ_DELTA, email="Dr.Test@azdelta.be"):
    return {"name": "Dr. Test", "email": email, "oid": "oid-123", "tid": tid}


def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r.headers["X-Frame-Options"] == "DENY"


def test_me_without_session_is_401(client):
    assert client.get("/auth/me").status_code == 401


def test_api_without_session_is_401(client):
    r = client.get("/api/iets")
    assert r.status_code == 401
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/api/planning").status_code == 401


def test_frontend_fallback(tmp_path):
    from app.main import FrontendFiles

    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "app.js").write_text("x")
    spa = FastAPI()
    spa.mount("/", FrontendFiles(directory=tmp_path, html=True))
    c = TestClient(spa)
    assert c.get("/tarificatie/nieuw/P1/abc").text == "<div id=root></div>"  # onbekend pad -> index.html
    assert c.get("/").headers["cache-control"] == "no-cache"
    assert c.get("/app.js").text == "x"
    assert c.get("/api/bestaat-niet").status_code == 404  # nooit index.html voor API-paden


def test_issuer_validation():
    ok_iss = f"https://login.microsoftonline.com/{AZ_DELTA}/v2.0"
    assert is_valid_issuer({"tid": AZ_DELTA}, ok_iss) is True
    assert is_valid_issuer({"tid": OTHER}, f"https://login.microsoftonline.com/{OTHER}/v2.0") is False
    assert is_valid_issuer({"tid": AZ_DELTA}, f"https://login.microsoftonline.com/{OTHER}/v2.0") is False
    assert is_valid_issuer({}, ok_iss) is False


def test_successful_login_sets_session(client, monkeypatch):
    fake_token(monkeypatch, user())
    r = client.get("/auth/callback?code=x&state=y")
    assert r.status_code == 303
    assert "reporth_session" in r.cookies

    me = client.get("/auth/me").json()
    assert me == {"name": "Dr. Test", "email": "dr.test@azdelta.be", "oid": "oid-123", "tid": AZ_DELTA}

    assert client.get("/api/planning").status_code == 503  # aangemeld; zonder testdatabase geeft de planning 503


def test_email_not_on_allowlist_is_refused(client, monkeypatch):
    monkeypatch.setattr(settings, "allowed_emails", frozenset({"iemand.anders@azdelta.be"}))
    fake_token(monkeypatch, user())
    r = client.get("/auth/callback?code=x&state=y")
    assert r.headers["location"] == "/fout?reden=lijst"
    assert client.get("/auth/me").status_code == 401


def test_email_falls_back_to_preferred_username(client, monkeypatch):
    monkeypatch.setattr(settings, "allowed_emails", frozenset({"dr.test@azdelta.be"}))
    info = user(email=None)
    info["preferred_username"] = "DR.TEST@azdelta.be"
    fake_token(monkeypatch, info)
    assert client.get("/auth/callback?code=x&state=y").status_code == 303


def test_tenant_rejected_by_issuer_validation_is_refused(client, monkeypatch):
    fake_token(monkeypatch, exc=InvalidClaimError("iss"))
    assert client.get("/auth/callback?code=x&state=y").headers["location"] == "/fout?reden=organisatie"
    assert client.get("/auth/me").status_code == 401


def test_tenant_recheck_after_login_is_refused(client, monkeypatch):
    fake_token(monkeypatch, user(tid=OTHER))
    assert client.get("/auth/callback?code=x&state=y").headers["location"] == "/fout?reden=organisatie"
    assert client.get("/auth/me").status_code == 401


def test_entra_error_redirects_with_code_only(client):
    r = client.get("/auth/callback", params={"error": "access_denied", "error_description": "AADSTS50105 geheim"})
    assert r.status_code == 303
    assert r.headers["location"] == "/fout?reden=microsoft&code=access_denied"  # geen beschrijving doorgeven


def test_logged_out_redirects_to_frontend(client):
    assert client.get("/auth/logged-out").headers["location"] == "/afgemeld"


def test_guest_login_uses_reporth_tenant(client, monkeypatch):
    async def fake_redirect(request, redirect_uri):
        return RedirectResponse("https://login.example/reporth", status_code=302)

    async def fake_token(request, **kwargs):
        return {"userinfo": user(tid="de5dcc4b-b4d4-4eca-8851-2cb8bdd62c7b")}

    monkeypatch.setattr(oauth.entra_reporth, "authorize_redirect", fake_redirect)
    monkeypatch.setattr(oauth.entra_reporth, "authorize_access_token", fake_token)

    assert client.get("/auth/login?via=reporth").headers["location"] == "https://login.example/reporth"
    # De callback gebruikt dezelfde (Reporth-)client als de login.
    assert client.get("/auth/callback?code=x&state=y").status_code == 303
    assert client.get("/auth/me").json()["tid"] == "de5dcc4b-b4d4-4eca-8851-2cb8bdd62c7b"


def test_logout_clears_session_and_redirects_to_microsoft(client, monkeypatch):
    fake_token(monkeypatch, user())
    client.get("/auth/callback?code=x&state=y")
    r = client.get("/auth/logout")
    assert r.status_code == 303
    assert r.headers["location"].startswith(
        "https://login.microsoftonline.com/organizations/oauth2/v2.0/logout?post_logout_redirect_uri=http%3A%2F%2Ftestserver%2Fauth%2Flogged-out"
    )
    assert client.get("/api/planning").status_code == 401


def test_dev_login_uit_standaard(client):
    assert client.get("/auth/dev").status_code == 404


def test_dev_login_aan(client, monkeypatch):
    monkeypatch.setattr(settings, "dev_login_email", "dev@example.com")
    r = client.get("/auth/dev")
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert client.get("/auth/me").json()["email"] == "dev@example.com"


def test_dev_login_geweigerd_op_cloud_run(monkeypatch):
    from app.config import load_settings

    monkeypatch.setenv("DEV_LOGIN_EMAIL", "dev@example.com")
    monkeypatch.setenv("K_SERVICE", "reporth-v3")
    with pytest.raises(SystemExit):
        load_settings()
