"""Entra ID-login via OpenID Connect (authorization code flow)."""

import logging
import sys
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from joserfc.errors import InvalidClaimError, JoseError
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

# Naar stdout, zodat het in Cloud Logging terechtkomt.
# Enkel technische gegevens (tid, oid, reden): geen namen, e-mails of tokens.
log = logging.getLogger("reporth.auth")
log.setLevel(logging.INFO)
if not log.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    log.addHandler(_handler)
    log.propagate = False


def is_valid_issuer(claims, iss) -> bool:
    """Issuer-validatie voor een multi-tenant app.

    De metadata van /organizations bevat als issuer een template
    (https://login.microsoftonline.com/{tenantid}/v2.0), dus de standaardcontrole
    van Authlib kan niet werken. We controleren daarom zelf dat de tenant uit het
    token toegelaten is én dat de issuer precies bij die tenant hoort.
    """
    tid = claims.get("tid")
    if not tid or tid.lower() not in settings.allowed_tenants:
        return False
    return iss == f"https://login.microsoftonline.com/{tid}/v2.0"


CLAIMS_OPTIONS = {"iss": {"essential": True, "validate": is_valid_issuer}}

oauth = OAuth()
oauth.register(
    name="entra",
    client_id=settings.client_id,
    client_secret=settings.client_secret,
    server_metadata_url=settings.metadata_url,
    client_kwargs={"scope": "openid profile email"},
)

# Gast-login (/auth/login?via=reporth): via de Reporth-tenant in plaats van
# "organizations". Een gast (B2B) meldt zich aan met het eigen ziekenhuisaccount,
# maar toestemming en token komen van de Reporth-tenant. Bedoeld om te testen
# zolang het ziekenhuis nog geen admin consent gaf.
REPORTH_TENANT = "de5dcc4b-b4d4-4eca-8851-2cb8bdd62c7b"
oauth.register(
    name="entra_reporth",
    client_id=settings.client_id,
    client_secret=settings.client_secret,
    server_metadata_url=f"https://login.microsoftonline.com/{REPORTH_TENANT}/v2.0/.well-known/openid-configuration",
    client_kwargs={"scope": "openid profile email"},
)


def _client(request: Request):
    return oauth.entra_reporth if request.session.get("login_via") == "reporth" else oauth.entra

router = APIRouter(prefix="/auth")


def _naar_frontend(pad: str = "/") -> RedirectResponse:
    """Doorsturen naar een pagina van de React-app (FRONTEND_URL is lokaal een andere poort)."""
    return RedirectResponse(settings.frontend_url.rstrip("/") + pad, status_code=303)


def _fout(reden: str, **extra: str) -> RedirectResponse:
    """De foutpagina zelf is React: /fout?reden=... Enkel codes, geen details van Microsoft of de gebruiker."""
    return _naar_frontend("/fout?" + urlencode({"reden": reden, **extra}))


@router.get("/login")
async def login(request: Request):
    # Vaste redirect-URI uit config: achter de Cloud Run-proxy zou de app
    # zichzelf anders als http:// zien.
    request.session["login_via"] = "reporth" if request.query_params.get("via") == "reporth" else "organizations"
    return await _client(request).authorize_redirect(request, settings.redirect_uri)


@router.get("/callback")
async def callback(request: Request):
    # Fout die Microsoft zelf terugstuurt (bv. AADSTS-codes).
    if "error" in request.query_params:
        error = request.query_params.get("error", "")
        log.warning("login geweigerd reden=entra_error error=%s", error)
        return _fout("microsoft", code=error)

    try:
        token = await _client(request).authorize_access_token(request, claims_options=CLAIMS_OPTIONS)
    except InvalidClaimError as exc:
        if exc.claim == "iss":
            log.warning("login geweigerd reden=tenant_of_issuer_niet_toegelaten")
            return _fout("organisatie")
        log.warning("login geweigerd reden=ongeldig_token claim=%s", exc.claim)
        return _fout("token")
    # Authlib 1.9 valideert het id_token met joserfc; die fouten zijn joserfc.errors.JoseError.
    except (OAuthError, JoseError) as exc:
        log.warning("login geweigerd reden=%s", type(exc).__name__)
        return _fout("login")

    userinfo = token.get("userinfo") or {}
    tid = (userinfo.get("tid") or "").lower()
    oid = userinfo.get("oid", "")

    # Defense in depth: de tenant nog eens expliciet controleren.
    if tid not in settings.allowed_tenants:
        log.warning("login geweigerd reden=tenant_niet_toegelaten tid=%s oid=%s", tid, oid)
        return _fout("organisatie")

    email = (userinfo.get("email") or userinfo.get("preferred_username") or "").lower()
    if settings.allowed_emails and email not in settings.allowed_emails:
        log.warning("login geweigerd reden=email_niet_op_lijst tid=%s oid=%s", tid, oid)
        return _fout("lijst")

    # Nieuwe sessie (voorkomt session fixation); enkel deze vier velden, geen tokens.
    request.session.clear()
    request.session["user"] = {"name": userinfo.get("name") or email, "email": email, "oid": oid, "tid": tid}
    log.info("login ok tid=%s oid=%s", tid, oid)
    return _naar_frontend()


@router.get("/dev")
async def dev_login(request: Request):
    """Lokale ontwikkel-login zonder Microsoft (bv. als MFA niet beschikbaar is).

    Bestaat enkel als DEV_LOGIN_EMAIL gezet is; config.py weigert die instelling op Cloud Run.
    """
    if not settings.dev_login_email:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    request.session.clear()
    request.session["user"] = {"name": "Developer", "email": settings.dev_login_email, "oid": "dev-oid", "tid": "dev-tenant"}
    log.warning("dev-login actief")
    return _naar_frontend()


@router.get("/me")
async def me(request: Request):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"detail": "Niet aangemeld"}, status_code=401)
    return user


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    query = urlencode({"post_logout_redirect_uri": settings.post_logout_uri})
    return RedirectResponse(
        f"https://login.microsoftonline.com/{settings.authority}/oauth2/v2.0/logout?{query}", status_code=303
    )


@router.get("/logged-out")
async def logged_out():
    return _naar_frontend("/afgemeld")


class LoginRequiredMiddleware(BaseHTTPMiddleware):
    """Schermt de data af: /api/* geeft 401 zonder sessie.

    De bestanden van de React-app zijn publiek (er zit geen data in); die stuurt zelf
    door naar /aanmelden als een API-call 401 geeft.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/") and not request.session.get("user"):
            return JSONResponse({"detail": "Niet aangemeld"}, status_code=401)
        return await call_next(request)
