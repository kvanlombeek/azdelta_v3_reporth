"""Instellingen uit omgevingsvariabelen (lokaal aangevuld vanuit .env)."""

import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # overschrijft geen variabelen die al gezet zijn

# Leesbare namen voor gekende tenants. Onbekend = tenant-ID tonen.
TENANT_NAMES = {
    "de5dcc4b-b4d4-4eca-8851-2cb8bdd62c7b": "Reporth",
    "0d2411fc-02b6-455e-86db-122a475d9273": "AZ Delta",
}

# Voorlopig vast. Later per gebruiker (in Retool: current_user.metadata.ortho_group).
ORTHO_GROUP = "AZDelta"

REQUIRED = [
    "ENTRA_CLIENT_ID",
    "ENTRA_CLIENT_SECRET",
    "ENTRA_REDIRECT_URI",
    "ENTRA_POST_LOGOUT_URI",
    "ENTRA_ALLOWED_TENANTS",
    "SESSION_SECRET",
    "DATABASE_URL",
]


def _csv(name: str) -> frozenset[str]:
    raw = os.getenv(name, "")
    return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())


@dataclass
class Settings:
    client_id: str
    client_secret: str
    authority: str
    redirect_uri: str
    post_logout_uri: str
    allowed_tenants: frozenset[str]
    allowed_emails: frozenset[str]
    session_secret: str
    session_https_only: bool
    database_url: str

    @property
    def metadata_url(self) -> str:
        return f"https://login.microsoftonline.com/{self.authority}/v2.0/.well-known/openid-configuration"


def load_settings() -> Settings:
    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if missing:
        # Enkel namen tonen, nooit waarden.
        sys.exit(f"Configuratiefout: ontbrekende omgevingsvariabele(n): {', '.join(missing)}")

    allowed_tenants = _csv("ENTRA_ALLOWED_TENANTS")
    if not allowed_tenants:
        sys.exit("Configuratiefout: ENTRA_ALLOWED_TENANTS bevat geen tenant-ID's")

    return Settings(
        client_id=os.environ["ENTRA_CLIENT_ID"].strip(),
        client_secret=os.environ["ENTRA_CLIENT_SECRET"].strip(),
        authority=os.getenv("ENTRA_AUTHORITY", "organizations").strip() or "organizations",
        redirect_uri=os.environ["ENTRA_REDIRECT_URI"].strip(),
        post_logout_uri=os.environ["ENTRA_POST_LOGOUT_URI"].strip(),
        allowed_tenants=allowed_tenants,
        allowed_emails=_csv("ENTRA_ALLOWED_EMAILS"),
        session_secret=os.environ["SESSION_SECRET"].strip(),
        session_https_only=os.getenv("SESSION_HTTPS_ONLY", "true").strip().lower() != "false",
        database_url=os.environ["DATABASE_URL"].strip(),
    )


settings = load_settings()
