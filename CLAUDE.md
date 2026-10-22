# Reporth v3

Reporth is een Belgisch platform voor orthopedisch chirurgen: chirurgisch logboek (registratie van ingrepen), AI-ondersteunde operatieverslagen en brieven, opvolging van uitkomsten (PROM's) en RIZIV-facturatie. Productie draait vandaag op **Retool + PostgreSQL (Cloud SQL, België)** bij AZ Delta Roeselare. AZ Maria Middelares is in onboarding.

**v3** is de herschrijving in eigen code, onafhankelijk van Retool, met SSO via Microsoft Entra ID. Doel: binnen ±6 maanden (vanaf okt 2026) de Retool-versie kunnen vervangen, met Maria Middelares als eerste nieuw ziekenhuis op v3.

**Huidige stand:** artsen melden aan met hun eigen ziekenhuisaccount (Entra ID, multi-tenant, OIDC authorization code flow). De startpagina toont het weekoverzicht (geplande ingrepen, nog te tarificeren) van de aangemelde arts, uit PostgreSQL. De groep is nog vast `ORTHO_GROUP = "AZDelta"` (`app/config.py`).

Taal: code-commentaar, UI-teksten, logs en docs zijn in het **Nederlands**. Domein-identifiers ook (`geplande_ingrepen`, `weekoverzicht`, `gerapporteerd`). Behoud dat, en gebruik Belgisch-Nederlandse vaktermen (ingreep, tarificatie, lateraliteit, nomenclatuur, arts).

## Architectuurprincipes (niet wijzigen zonder overleg)

1. **Cloud multi-tenant, geen on-premises.** Eén deployment voor alle ziekenhuizen. Bouw niets dat een aparte installatie per ziekenhuis veronderstelt.
2. **Isolatie per ziekenhuis/groep.** Vandaag is dat de vaste `ORTHO_GROUP`. Vóór een tweede ziekenhuis live gaat, moet de groep afgeleid worden van de aangemelde gebruiker (`tid`) in plaats van een constante, en moet elke query erop filteren. Geen endpoint mag data van een ander ziekenhuis teruggeven; test dit expliciet.
3. **Frontendkeuze en deploymentmodel zijn twee aparte assen.** Hou ze gescheiden in code en documentatie.
4. **Data blijft in België/EU**: Cloud SQL en Cloud Run in `europe-west1`.
5. **Incrementeel, geen big bang.** v3 draait een tijd naast Retool op dezelfde database. Breek het bestaande schema niet zonder migratieplan, en hou rekening met **Metabase**: die dashboards lezen dezelfde tabellen, dus kolommen hernoemen of verwijderen breekt ze.

## Stack

- Python 3.12, FastAPI + Starlette, uvicorn
- Auth: Authlib + joserfc, sessie via Starlette `SessionMiddleware` (gesigneerde cookie)
- DB: PostgreSQL (Cloud SQL, met pgvector) via `psycopg` 3 (async) met `psycopg_pool`. Geen ORM, ruwe SQL. Bestaand schema: `procedures_production`.
- Front-end: **server-side gerenderde HTML als f-strings** in `app/pages.py`. Geen templates, geen JS-framework, geen buildstap. Tailwind 3.4.17 via de Play CDN; huisstijl als CSS-variabelen in `_head()`. Eén klein inline vanilla-JS-script voor de dagtabs.
- Hosting: Cloud Run (`europe-west1`), image via Cloud Build, secrets in Secret Manager
- Elders in het Reporth-ecosysteem (nog niet in v3): Gemini API (verslagen, brieven, PROM-formulieren via Vision), embeddings voor procedure-matching (`procedures_production.procedure_embeddings`), Postmark Inbound voor binnenkomende mail, Metabase-dashboards. DNS voor reporth.be/.com bij Vercel.

## Structuur

| Pad | Inhoud |
|---|---|
| `app/main.py` | App, `/`, `/health`, security headers, middleware-volgorde |
| `app/auth.py` | Login, callback, logout, issuer-validatie, `LoginRequiredMiddleware` |
| `app/config.py` | Env vars (`load_settings`), `TENANT_NAMES`, `ORTHO_GROUP` |
| `app/db.py` | Async connection pool (opent in de lifespan, wacht niet op de DB) |
| `app/planning.py` | SQL-queries en groepering per dag en zaal |
| `app/pages.py` | Alle HTML |
| `app/static/` | Logo's en favicon (publiek bereikbaar) |
| `tests/` | pytest; `conftest.py` zet test-env vóór import van `app.config` |
| `deploy.sh`, `cloudbuild.yaml`, `Dockerfile` | Build en deploy |

Endpoints: `/` (aangemeld), `/health` (publiek), `/auth/signin`, `/auth/login`, `/auth/callback`, `/auth/me` (JSON of 401), `/auth/logout`, `/auth/logged-out`.

## Front-end

Frontend is voorlopig. De f-string-HTML in pages.py is een tussenstap. De definitieve frontend (bv. React of server-side templates met HTMX) is nog niet gekozen. Bouw geen grote nieuwe schermen in f-strings zonder overleg, en hou businesslogica uit pages.py zodat de frontend later vervangbaar is.

## Commando's

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                       # invullen: ENTRA_CLIENT_SECRET, SESSION_SECRET, DATABASE_URL
cloud-sql-proxy orthopediereportingproject:europe-west1:orthopedie-reporting-db   # DB lokaal op 127.0.0.1:5432
uvicorn app.main:app --reload --port 8000
python -m pytest
./deploy.sh                                # idempotent; bouwt en deployt naar Cloud Run
```

## Conventies en valkuilen

- **SQL haalt op, Python verwerkt.** Queries zijn eenvoudige retrieval; verrijking, groepering en business logic gebeuren in Python. Altijd geparametriseerde queries. Dynamische waarden die de *structuur* van een query bepalen (kolomnamen, sortering) gaan via een whitelist.
- **Kleine stappen.** Eén logische stap per functie, liever meerdere kleine testbare functies dan één grote.
- **HTML-escaping**: alle dynamische tekst in `pages.py` gaat door `html.escape`. Nieuwe velden idem, zonder uitzondering.
- **Middleware-volgorde** in `main.py` is bewust: in Starlette draait de laatst toegevoegde middleware eerst. `SessionMiddleware` moet als laatste worden toegevoegd, anders bestaat `request.session` nog niet in `LoginRequiredMiddleware`. Uitvoering: Session → SecurityHeaders → LoginRequired → routes.
- **Nieuwe publieke route of statisch bestand**: `LoginRequiredMiddleware` blokkeert standaard alles; publieke paden staan daar expliciet (de loginpagina gebruikt `/static`).
- **Issuer-validatie** is eigen code (`is_valid_issuer`), omdat de metadata van `/organizations` een issuer-template bevat. `iss` moet exact `https://login.microsoftonline.com/{tid}/v2.0` zijn én `tid` moet in `ENTRA_ALLOWED_TENANTS` staan. Niet vervangen door de standaardcontrole van Authlib.
- **Identiteit** koppelen op `tid` + `oid`, niet op e-mailadres.
- **`SameSite=lax`** op de sessiecookie is nodig: de terugkeer van Microsoft is een top-level navigatie.
- **Arts-autorisatie**: `/` accepteert enkel artsen uit de eigen `ORTHO_GROUP`; de `arts`-parameter wordt tegen die lijst gevalideerd. Behoud die controle bij wijzigingen.
- **Datumfilter in SQL** vergelijkt de ISO-tekst (`geplande_procedure->>'date_procedure'`) zodat index `idx_patient_date_procedure` bruikbaar blijft. Niet casten in de `WHERE`.
- **Gerapporteerd** = er bestaat een ingreep voor die patiënt tot 1 dag voor of na de geplande datum.
- Tijdzone is `Europe/Brussels` (`planning.TZ`).
- Foutpagina bij DB-problemen is een 503 met "Opnieuw proberen"; de app moet ook starten als de DB even onbereikbaar is.

## Tests

- pytest + FastAPI `TestClient`. Tests raken nooit de echte database (`DATABASE_URL` wijst naar een dode poort) en doen geen netwerkcalls naar Microsoft of Gemini: mocken.
- Verplicht te testen: issuer-validatie, toegangsweigering zonder sessie (redirect voor HTML, 401 voor JSON), arts-autorisatie, en zodra van toepassing: isolatie tussen ziekenhuizen, anonimisering vóór AI-calls, Transfile golden files.
- Draai de tests tot ze slagen voordat je een taak afgerond noemt.

## Privacy, GDPR en logging

- De data is **gepseudonimiseerde persoonsgegevens** (GDPR art. 4(5)), niet anoniem. GDPR blijft volledig van toepassing. Het ziekenhuis beheert de sleutel tot heridentificatie.
- Het ziekenhuis beheert zelf wie toegang heeft ("Assignment required" in hun Enterprise app); MFA en Conditional Access gelden automatisch. Dit is een eis van de DPO's.
- **Vóór elke call naar een externe AI-API** (Gemini) worden gegevens verder geanonimiseerd (o.a. geboortedatum gerandomiseerd). Stuur nooit veldcombinaties of documentbeelden door zonder die stap. Bouw dit als één centrale functie.
- Sessie bevat enkel `name`, `email`, `oid`, `tid` (geen tokens), cookie `reporth_session`, 8 uur geldig.
- Log (stdout → Cloud Logging) enkel technische gegevens: `login ok` / `login geweigerd reden=…` met `tid` en `oid`. **Nooit** namen, e-mailadressen, tokens, verslagtekst of patiëntgegevens loggen.
- Links zonder login (bv. een verslag openen vanuit een mail) enkel met tijdsgebonden tokens, audit-logging en lichte verificatie.
- Geen analytics. Het enige externe script is de Tailwind-CDN.

## Domein

- **Ingreep**: wat de chirurg uitvoerde, gekoppeld aan één of meer procedures.  Classificatie gebeurt deels op keywords en codebereiken.
- **Tarificatie / nomenclatuur**: officiële RIZIV-codes en honoraria.
- **Lateraliteit**: links/rechts/bilateraal; beïnvloedt facturatieregels.
- **Arts / chirurg / assistent**: rollen. Assistenten registreren vaak voor een supervisor.
- **Procedurelijst**: door Paul onderhouden. Ingrepen bestaat uit 1 of meerdere van deze procedures. Aan de procedures zijn RIZIV-nomenclatuurcodes gekoppeld. Lijsten van andere ziekenhuizen worden daarop gemapt via embeddings.
- **PROM's**: patient-reported outcome measures, soms als gescande formulieren.

## Secrets en config

- `.env` staat in `.gitignore`: nooit committen, nooit tonen of uitlezen in output. `.env.example` bevat enkel placeholders.
- Productie-secrets (`reporth-v3-entra-client-secret`, `reporth-v3-session-secret`, `reporth-v3-database-url`) leven in Secret Manager; `deploy.sh` bevat er geen.
- Op Cloud Run wijst `DATABASE_URL` naar de Unix-socket `/cloudsql/<instance>` in plaats van `127.0.0.1`. Enkel de URL verschilt, de code niet.
- Nieuw ziekenhuis: admin consent door hun beheerder, tenant-ID toevoegen aan `ENTRA_ALLOWED_TENANTS` in `deploy.sh`, leesbare naam aan `TENANT_NAMES` in `app/config.py`.
- Redirect-URI's in Entra: `callback` en `logged-out` voor zowel `https://v3.reporth.be` als `http://localhost:8000`.

Zie `README.md` voor het volledige deploy-, secrets- en domeinverhaal.

## Werkwijze

1. **Toon eerst een kort plan** voor elke niet-triviale wijziging en wacht op akkoord.
2. **Geen `gcloud`-commando's die resources aanmaken, wijzigen of verwijderen** (en geen `./deploy.sh`) zonder expliciete toestemming. Lezen (`describe`, `list`) mag.
3. **Geen schrijfoperaties op de productiedatabase** zonder expliciete toestemming. Via de proxy zit je op productie; behandel die verbinding als read-only.
4. Nooit de waarde van een secret printen, loggen of committen.
5. Bij twijfel over facturatieregels, RIZIV-codes of medische betekenis: vraag het, verzin niets.
6. Sluit een taak af met een korte checklist van wat Kasper zelf nog moet doen (Entra-instellingen, secrets, DNS bij Vercel, enz.).

## Git

Repo: `kvanlombeek/azdelta_v3_reporth` (privé), branch `main`.