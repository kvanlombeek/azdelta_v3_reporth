import pytest
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


def test_static_is_public(client):
    r = client.get("/static/logo.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert client.get("/static/bestaat-niet.png").status_code == 404


def test_root_without_session_redirects_to_login(client):
    r = client.get("/")
    assert r.status_code == 307
    assert r.headers["location"] == "/auth/signin"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_signin_page(client, monkeypatch):
    r = client.get("/auth/signin")
    assert r.status_code == 200
    assert 'href="/auth/login"' in r.text
    assert 'href="/auth/login?via=reporth"' in r.text

    fake_token(monkeypatch, user())
    client.get("/auth/callback?code=x&state=y")
    assert client.get("/auth/signin").headers["location"] == "/"


def test_me_without_session_is_401(client):
    assert client.get("/auth/me").status_code == 401


def test_json_request_without_session_is_401(client):
    r = client.get("/", headers={"Accept": "application/json"})
    assert r.status_code == 401
    assert client.get("/api/iets").status_code == 401


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

    home = client.get("/")
    assert not home.is_redirect  # aangemeld; zonder testdatabase geeft de planning 503


def test_email_not_on_allowlist_is_403(client, monkeypatch):
    monkeypatch.setattr(settings, "allowed_emails", frozenset({"iemand.anders@azdelta.be"}))
    fake_token(monkeypatch, user())
    r = client.get("/auth/callback?code=x&state=y")
    assert r.status_code == 403
    assert client.get("/auth/me").status_code == 401


def test_email_falls_back_to_preferred_username(client, monkeypatch):
    monkeypatch.setattr(settings, "allowed_emails", frozenset({"dr.test@azdelta.be"}))
    info = user(email=None)
    info["preferred_username"] = "DR.TEST@azdelta.be"
    fake_token(monkeypatch, info)
    assert client.get("/auth/callback?code=x&state=y").status_code == 303


def test_tenant_rejected_by_issuer_validation_is_403(client, monkeypatch):
    fake_token(monkeypatch, exc=InvalidClaimError("iss"))
    assert client.get("/auth/callback?code=x&state=y").status_code == 403


def test_tenant_recheck_after_login_is_403(client, monkeypatch):
    fake_token(monkeypatch, user(tid=OTHER))
    assert client.get("/auth/callback?code=x&state=y").status_code == 403


def test_entra_error_is_shown_escaped(client):
    r = client.get("/auth/callback", params={"error": "access_denied", "error_description": "AADSTS50105 <script>"})
    assert r.status_code == 400
    assert "AADSTS50105 &lt;script&gt;" in r.text
    assert "<script>" not in r.text.rsplit("</script>", 1)[1]  # enkel de Tailwind-scripts in <head>


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
    assert client.get("/").status_code == 307
