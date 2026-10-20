"""PostgreSQL-verbinding (Cloud SQL).

Lokaal via de Cloud SQL Auth Proxy (127.0.0.1:5432). Op Cloud Run via de
Unix-socket die --add-cloudsql-instances aanmaakt (/cloudsql/<instance>).
Enkel DATABASE_URL verschilt; de code is dezelfde.
"""

from psycopg_pool import AsyncConnectionPool

from app.config import settings

# open=False: de pool gaat open in de lifespan van de app (app/main.py).
# Het openen wacht niet op de database, zodat de app ook start als die even onbereikbaar is.
pool = AsyncConnectionPool(settings.database_url, min_size=1, max_size=5, open=False)

