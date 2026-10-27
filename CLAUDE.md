# Reporth v3

Reporth is een Belgisch platform voor orthopedisch chirurgen: chirurgisch logboek (registratie van ingrepen), AI-ondersteunde operatieverslagen en brieven, opvolging van uitkomsten (PROM's) en RIZIV-facturatie. Productie draait vandaag op **Retool + PostgreSQL (Cloud SQL, België)** bij AZ Delta Roeselare. AZ Maria Middelares is in onboarding.

De arts start normaal op een landingspagina, met daarop de geplande ingrepen per operatie zaal van die week. Een arts kan dan een geplande ingreep aanklikken, en dan start de registratie. Deze bestaat uit drie stappen:
- De eerste stap is de tarificatie. Hier worden alle parameters zoals tijd, ziekenhuis, arts, assistent, geregistreerd. Al deze zaken zijn normaal al gekend vanuit de planning. De arts kiest hier ook uit een lijst van onderhouden procedures 1 of meerdere procedures (bijvoorbeeld THP of Carpal tunnel release) die de arts heeft uitgevoerd. Aan elke procedure zijn de bijbehorede Riziv Nomenclatuur nummers gekoppeld.
- De tweede stap is een detailformulier afhankelijk van de gekozen procedure. Bij een THP installatie moeten bijvoorbeeld zaken zoals toegansweg, implantaat, anesthesie etc worden ingevuld om dan te koppelen naar Sciensano.
- De laatste stap is dat al deze informatie wordt doorgestuurd naar een LLM API zoals Gemini, en dat er door deze LLM een brief wordt geschreven. De arts moet deze brief dan nog nalezen en opslagen.

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
- Front-end: **React 18 + TypeScript + Vite** in `frontend/`, Tailwind 3.4.17 (via npm); huisstijl als CSS-variabelen in `frontend/src/index.css`. Gewone `fetch`, geen router- of data-bibliotheek. Python is **enkel API** (`/api`, `/auth`, `/health`) en kent de inhoud van de frontend niet.
- Hosting: Cloud Run (`europe-west1`), image via Cloud Build, secrets in Secret Manager
- Elders in het Reporth-ecosysteem (nog niet in v3): Gemini API (verslagen, brieven, PROM-formulieren via Vision), embeddings voor procedure-matching (`procedures_production.procedure_embeddings`), Postmark Inbound voor binnenkomende mail, Metabase-dashboards. DNS voor reporth.be/.com bij Vercel.

## Structuur

| Pad | Inhoud |
|---|---|
| `app/main.py` | App, `/health`, security headers, middleware-volgorde, serveert de gebouwde frontend (`app/web`) |
| `app/auth.py` | Login, callback, logout, dev-login, issuer-validatie, `LoginRequiredMiddleware` |
| `app/api.py` | JSON-API: `/api/planning`, `/api/tarificatie/nieuw/{patient_id}/{hash}`, `/api/tarificatie/berekenen`, `/api/tarificatie/ingreep/{ingreep_id}` (opgeslagen ingreep, niet herberekend), `/api/ingrepen` |
| `app/tarificatie.py` | Queries en voorinvulling van de tarificatie (stap 1) |
| `app/ingrepen.py` | Historiek: geregistreerde ingrepen met filters (arts, regio, datum, zoekterm), via `GET /api/ingrepen`. Arts ziet enkel zichzelf; `ADMIN_EMAILS` en actieve assistenten zien alle artsen van de groep |
| `app/tarificatie_codes.py` | Rekent het voorstel van RIZIV-codes uit (hoofdcode per zijde/straal, extra, gips, A/H-partner), via `POST /api/tarificatie/berekenen`. Bewaart niets |
| `app/procedures.py` | Procedures zoeken (Gemini-embedding + trigram + RIZIV-code) op `curated_form_fields.procedure_embeddings`, via `/api/procedures` |
| `app/config.py` | Env vars (`load_settings`), `TENANT_NAMES`, `ORTHO_GROUP` |
| `app/db.py` | Async connection pool (opent in de lifespan, wacht niet op de DB) |
| `app/planning.py` | SQL-queries en groepering per dag en zaal |
| `frontend/` | React-app (Vite). `npm run dev` lokaal; `npm run build` bouwt naar `app/web` (gitignored) |
| `tests/` | pytest; `conftest.py` zet test-env vóór import van `app.config` |
| `deploy.sh`, `cloudbuild.yaml`, `Dockerfile` | Build en deploy |

Endpoints: `/api/*` (aangemeld, anders 401), `/health` (publiek), `/auth/login`, `/auth/callback`, `/auth/me` (JSON of 401), `/auth/logout`, `/auth/logged-out` (redirect naar de frontend), `/auth/dev` (enkel lokaal). Alle andere paden zijn de React-app (`/`, `/aanmelden`, `/afgemeld`, `/fout`, `/ingrepen`, `/tarificatie/nieuw/...`, `/tarificatie/ingreep/{id}`).

## Front-end

React + Vite (`frontend/`), apart van de Python-code. Eén deployment: de Dockerfile bouwt de frontend en Python serveert `app/web`; frontendkeuze en deploymentmodel blijven twee aparte assen. Businesslogica (groeperen, valideren, autorisatie) blijft in Python; de frontend toont en verzamelt invoer. De bestanden van de frontend zijn publiek, de data (`/api`) niet.

## Commando's

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                       # invullen: ENTRA_CLIENT_SECRET, SESSION_SECRET, DATABASE_URL
cloud-sql-proxy orthopediereportingproject:europe-west1:orthopedie-reporting-db   # DB lokaal op 127.0.0.1:5432
uvicorn app.main:app --reload --port 8000   # API
(cd frontend && npm install && npm run dev)  # frontend op http://localhost:5173 (proxy naar 8000)
# Zonder Microsoft-login (bv. geen MFA): zet DEV_LOGIN_EMAIL in .env en open http://localhost:8000/auth/dev
python -m pytest
./deploy.sh                                # idempotent; bouwt en deployt naar Cloud Run
```

## Conventies en valkuilen

- **SQL haalt op, Python verwerkt.** Queries zijn eenvoudige retrieval; verrijking, groepering en business logic gebeuren in Python. Altijd geparametriseerde queries. Dynamische waarden die de *structuur* van een query bepalen (kolomnamen, sortering) gaan via een whitelist.
- **Kleine stappen.** Eén logische stap per functie, liever meerdere kleine testbare functies dan één grote.
- **Geen HTML in Python**: foutmeldingen bij het inloggen zijn redirects naar `/fout?reden=<code>`; enkel codes, nooit details van Microsoft of de gebruiker. React escaped tekst zelf; gebruik nooit `dangerouslySetInnerHTML`.
- **Middleware-volgorde** in `main.py` is bewust: in Starlette draait de laatst toegevoegde middleware eerst. `SessionMiddleware` moet als laatste worden toegevoegd, anders bestaat `request.session` nog niet in `LoginRequiredMiddleware`. Uitvoering: Session → SecurityHeaders → LoginRequired → routes (de frontend-mount staat als laatste).
- **Toegang**: `LoginRequiredMiddleware` geeft 401 op elk `/api/*`-pad zonder sessie. De frontendbestanden zijn publiek; de frontend stuurt bij een 401 door naar `/aanmelden`. Nieuwe data hoort dus altijd onder `/api`.
- **Issuer-validatie** is eigen code (`is_valid_issuer`), omdat de metadata van `/organizations` een issuer-template bevat. `iss` moet exact `https://login.microsoftonline.com/{tid}/v2.0` zijn én `tid` moet in `ENTRA_ALLOWED_TENANTS` staan. Niet vervangen door de standaardcontrole van Authlib.
- **Identiteit** koppelen op `tid` + `oid`, niet op e-mailadres.
- **`SameSite=lax`** op de sessiecookie is nodig: de terugkeer van Microsoft is een top-level navigatie.
- **Arts-autorisatie**: `/api/planning` accepteert enkel artsen uit de eigen `ORTHO_GROUP`; de `arts`-parameter wordt tegen die lijst gevalideerd. Behoud die controle bij wijzigingen.
- **Datumfilter in SQL** vergelijkt de ISO-tekst (`geplande_procedure->>'date_procedure'`) zodat index `idx_patient_date_procedure` bruikbaar blijft. Niet casten in de `WHERE`.
- **Gerapporteerd** = er bestaat een ingreep voor die patiënt tot 1 dag voor of na de geplande datum.
- Tijdzone is `Europe/Brussels` (`planning.TZ`).
- Bij DB-problemen geeft de API een 503 (JSON) en toont de frontend "Opnieuw proberen"; de app moet ook starten als de DB even onbereikbaar is.
- **Dev-login** (`DEV_LOGIN_EMAIL`) bestaat enkel lokaal: `config.py` weigert te starten als die gezet is op Cloud Run (`K_SERVICE`). Zet hem nooit in `deploy.sh`.
- **Planning-links** dragen `patient_id` en een `planning_hash` (12 tekens, md5 van `geplande_procedure`) als versiecontrole; de server leest de planning altijd opnieuw en vertrouwt de browser niet.

## Tests

- pytest + FastAPI `TestClient`. Tests raken nooit de echte database (`DATABASE_URL` wijst naar een dode poort) en doen geen netwerkcalls naar Microsoft of Gemini: mocken.
- Verplicht te testen: issuer-validatie, toegangsweigering zonder sessie (401 op `/api/*`), arts-autorisatie, en zodra van toepassing: isolatie tussen ziekenhuizen, anonimisering vóór AI-calls, Transfile golden files.
- Draai de tests tot ze slagen voordat je een taak afgerond noemt.

## Privacy, GDPR en logging

- De data is **gepseudonimiseerde persoonsgegevens** (GDPR art. 4(5)), niet anoniem. GDPR blijft volledig van toepassing. Het ziekenhuis beheert de sleutel tot heridentificatie.
- Het ziekenhuis beheert zelf wie toegang heeft ("Assignment required" in hun Enterprise app); MFA en Conditional Access gelden automatisch. Dit is een eis van de DPO's.
- **Vóór elke call naar een externe AI-API** (Gemini) worden gegevens verder geanonimiseerd (o.a. geboortedatum gerandomiseerd). Stuur nooit veldcombinaties of documentbeelden door zonder die stap. Bouw dit als één centrale functie.
- **Uitzondering op de anonimiseringsregel**: het zoeken naar procedures (`app/procedures.py`) stuurt enkel de zoektekst (procedurewoorden; vooringevuld met de planningsomschrijving, bv. "Cts release open") naar Gemini, nooit patiëntgegevens; de zoektekst wordt niet gelogd en het zoekveld waarschuwt de arts. `GEMINI_API_KEY` is optioneel: zonder sleutel blijft zoeken op tekst en code werken.
- Sessie bevat enkel `name`, `email`, `oid`, `tid` (geen tokens), cookie `reporth_session`, 8 uur geldig.
- Log (stdout → Cloud Logging) enkel technische gegevens: `login ok` / `login geweigerd reden=…` met `tid` en `oid`. **Nooit** namen, e-mailadressen, tokens, verslagtekst of patiëntgegevens loggen.
- Links zonder login (bv. een verslag openen vanuit een mail) enkel met tijdsgebonden tokens, audit-logging en lichte verificatie.
- Geen analytics en geen externe scripts of CDN's.

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