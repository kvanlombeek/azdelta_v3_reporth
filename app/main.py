from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import api, db
from app.auth import LoginRequiredMiddleware, router as auth_router
from app.config import settings

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
app.include_router(api.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if settings.frontend_url != "/":
    # Lokaal draait de frontend op een eigen poort (Vite); hier enkel een gemakkelijke doorverwijzing.
    @app.get("/", include_in_schema=False)
    async def naar_frontend():
        return RedirectResponse(settings.frontend_url, status_code=307)


class FrontendFiles(StaticFiles):
    """De gebouwde React-app. Onbekende paden (bv. /tarificatie/...) krijgen index.html; de router doet de rest."""

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith(("api/", "auth/")):
                raise
            response = await super().get_response("index.html", scope)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"  # assets zijn gehasht, index.html niet
        return response


# Productie: de Dockerfile bouwt de frontend naar app/web. Lokaal draait Vite apart en bestaat die map niet.
# Als laatste, zodat /api, /auth en /health voorrang hebben.
WEB_DIR = Path(__file__).parent / "web"
if WEB_DIR.is_dir():
    app.mount("/", FrontendFiles(directory=WEB_DIR, html=True), name="frontend")


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
