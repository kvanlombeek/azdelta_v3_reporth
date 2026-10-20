"""Entra ID-login via OpenID Connect (authorization code flow)."""

import logging
import sys
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from joserfc.errors import InvalidClaimError, JoseError
from starlette.middleware.base import BaseHTTPMiddleware

from app import pages
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


def _forbidden(message: str) -> HTMLResponse:
    return HTMLResponse(pages.error_page("Geen toegang", message), status_code=403)


@router.get("/signin")
async def signin(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/", status_code=303)
    return HTMLResponse(pages.login_page())


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
        description = request.query_params.get("error_description", "")
        log.warning("login geweigerd reden=entra_error error=%s", error)
        return HTMLResponse(
            pages.error_page("Aanmelden mislukt", "Microsoft meldt een fout.", f"{error}\n{description}"),
            status_code=400,
        )

    try:
        token = await _client(request).authorize_access_token(request, claims_options=CLAIMS_OPTIONS)
    except InvalidClaimError as exc:
        if exc.claim == "iss":
            log.warning("login geweigerd reden=tenant_of_issuer_niet_toegelaten")
            return _forbidden("Je organisatie heeft (nog) geen toegang tot Reporth.")
        log.warning("login geweigerd reden=ongeldig_token claim=%s", exc.claim)
        return HTMLResponse(pages.error_page("Aanmelden mislukt", "Ongeldig token.", str(exc)), status_code=400)
    # Authlib 1.9 valideert het id_token met joserfc; die fouten zijn joserfc.errors.JoseError.
    except (OAuthError, JoseError) as exc:
        log.warning("login geweigerd reden=%s", type(exc).__name__)
        return HTMLResponse(pages.error_page("Aanmelden mislukt", "De login kon niet worden voltooid.", str(exc)), status_code=400)

    userinfo = token.get("userinfo") or {}
    tid = (userinfo.get("tid") or "").lower()
    oid = userinfo.get("oid", "")

    # Defense in depth: de tenant nog eens expliciet controleren.
    if tid not in settings.allowed_tenants:
        log.warning("login geweigerd reden=tenant_niet_toegelaten tid=%s oid=%s", tid, oid)
        return _forbidden("Je organisatie heeft (nog) geen toegang tot Reporth.")

    email = (userinfo.get("email") or userinfo.get("preferred_username") or "").lower()
    if settings.allowed_emails and email not in settings.allowed_emails:
        log.warning("login geweigerd reden=email_niet_op_lijst tid=%s oid=%s", tid, oid)
        return _forbidden("Je account staat niet op de lijst van toegelaten gebruikers.")

    # Nieuwe sessie (voorkomt session fixation); enkel deze vier velden, geen tokens.
    request.session.clear()
    request.session["user"] = {"name": userinfo.get("name") or email, "email": email, "oid": oid, "tid": tid}
    log.info("login ok tid=%s oid=%s", tid, oid)
    return RedirectResponse("/", status_code=303)


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
    return HTMLResponse(pages.logged_out_page())


class LoginRequiredMiddleware(BaseHTTPMiddleware):
    """Schermt alles af behalve /auth/*, /static/* en /health."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/health" or path.startswith(("/auth/", "/static/")) or request.session.get("user"):
            return await call_next(request)
        if path.startswith("/api/") or "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"detail": "Niet aangemeld"}, status_code=401)
        return RedirectResponse("/auth/signin", status_code=307)
