from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import db, pages, planning
from app.auth import LoginRequiredMiddleware, log, router as auth_router
from app.config import ORTHO_GROUP, settings

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.pool.open(wait=False)
    yield
    await db.pool.close()


app = FastAPI(title="Reporth v3", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(auth_router)
# Publiek (zie LoginRequiredMiddleware): de loginpagina gebruikt deze bestanden ook.
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, week: str = "", arts: str = "", dag: str = ""):
    # De login-middleware garandeert dat er hier een gebruiker in de sessie zit.
    user = request.session["user"]
    vandaag = planning.vandaag()
    try:
        maandag = planning.maandag_van(date.fromisoformat(week))
    except ValueError:
        maandag = planning.maandag_van(vandaag)

    try:
        artsen = await planning.artsen(ORTHO_GROUP)
        # Enkel artsen uit de eigen groep; standaard de aangemelde gebruiker zelf.
        emails = {a["email"].lower() for a in artsen if a["email"]}
        arts_email = next((e for e in (arts.lower(), user["email"]) if e in emails), None)
        overzicht = None
        if arts_email:
            rows = await planning.geplande_ingrepen(ORTHO_GROUP, arts_email, maandag)
            overzicht = planning.weekoverzicht(rows, maandag)
    except Exception as exc:
        log.warning("planning niet geladen fout=%s", type(exc).__name__)
        return HTMLResponse(
            pages.error_page("Planning niet beschikbaar", "De database is even niet bereikbaar.", button=("/", "Opnieuw proberen")),
            status_code=503,
        )

    # Gekozen dag; anders vandaag als die in deze week valt, anders de eerste dag met open ingrepen.
    if dag.isdigit() and int(dag) < 7:
        dag_index = int(dag)
    elif 0 <= (vandaag - maandag).days < 7:
        dag_index = (vandaag - maandag).days
    else:
        dagen = overzicht["dagen"] if overzicht else []
        dag_index = next((i for i, d in enumerate(dagen) if d["aantal_open"]), 0)

    return pages.landing_page(user["name"], artsen, arts_email, maandag, vandaag, overzicht, dag_index)


# Middleware-volgorde: in Starlette draait de LAATST toegevoegde middleware EERST
# (buitenste laag). SessionMiddleware wordt dus als laatste toegevoegd, zodat
# request.session al bestaat wanneer LoginRequiredMiddleware draait.
# Uitvoering: Session -> SecurityHeaders -> LoginRequired -> routes.
app.add_middleware(LoginRequiredMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="reporth_session",
    max_age=8 * 60 * 60,
    same_site="lax",  # lax is nodig: de terugkeer van Microsoft is een top-level navigatie
    https_only=settings.session_https_only,
)
