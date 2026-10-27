# Reporth v3 – hello world met Entra ID-login

Minimale webapp die bewijst dat artsen kunnen aanmelden met hun eigen ziekenhuisaccount
(Microsoft Entra ID, multi-tenant, OpenID Connect authorization code flow).
Na het aanmelden toont de startpagina het weekoverzicht (planning) van de aangemelde arts, uit de PostgreSQL-database (Cloud SQL).

| Onderdeel | Bestand |
|---|---|
| Configuratie (env vars, tenantnamen) | `app/config.py` |
| Login, callback, logout, issuer-validatie, login-middleware | `app/auth.py` |
| App, `/`, `/health`, security-headers, middleware-volgorde | `app/main.py` |
| Databaseverbinding (async pool) | `app/db.py` |
| Weekplanning (queries, groepering per dag en zaal) | `app/planning.py` |
| JSON-API | `app/api.py`, `app/tarificatie.py` |
| Frontend (React + Vite) | `frontend/` (build naar `app/web`) |

Endpoints: `/api/*` (aangemeld), `/health` (publiek), `/auth/login`, `/auth/callback`,
`/auth/me` (JSON of 401), `/auth/logout`, `/auth/logged-out`.

## Lokaal draaien

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # invullen: ENTRA_CLIENT_SECRET, SESSION_SECRET en DATABASE_URL
uvicorn app.main:app --reload --port 8000
python -m pytest
```

De database is lokaal enkel bereikbaar via de Cloud SQL Auth Proxy, die op `127.0.0.1:5432` moet
draaien (zoals bij procedure-finder):

```bash
cloud-sql-proxy orthopediereportingproject:europe-west1:orthopedie-reporting-db
```

`DATABASE_URL` heeft de vorm `postgresql://USER:PASSWORD@127.0.0.1:5432/ortho_db_omop`
(speciale tekens in het wachtwoord URL-encoden). De tests gebruiken nooit de echte database.

Open daarna http://localhost:8000. In `.env` staan voor lokaal al
`ENTRA_REDIRECT_URI=http://localhost:8000/auth/callback` en `SESSION_HTTPS_ONLY=false`.

## Entra ID (app-registratie in de Reporth-tenant)

Controleer bij *Authentication → Web → Redirect URIs* dat de volgende vier URL's
geregistreerd zijn:

- `https://v3.reporth.be/auth/callback`
- `https://v3.reporth.be/auth/logged-out`
- `http://localhost:8000/auth/callback`
- `http://localhost:8000/auth/logged-out`

Microsoft stuurt na het afmelden alleen door naar een `post_logout_redirect_uri` die
ook als redirect-URI geregistreerd is. Zonder de `logged-out`-URI's blijft de gebruiker
na het afmelden op de Microsoft-pagina staan.

Voor een nieuw ziekenhuis:

1. Een beheerder van dat ziekenhuis geeft admin consent voor de app.
2. Voeg de tenant-ID toe aan `ENTRA_ALLOWED_TENANTS` (in `deploy.sh`).
3. Voeg de leesbare naam toe aan `TENANT_NAMES` in `app/config.py`.

## Secrets aanmaken (eenmalig)

Doe dit zelf. Dankzij `read -s` komen de waarden niet in je shell-history of op je scherm.

```bash
gcloud config set project orthopediereportingproject

# Client secret uit Entra (Certificates & secrets) plakken, Enter
read -s SECRET && printf '%s' "$SECRET" | gcloud secrets create reporth-v3-entra-client-secret --data-file=- && unset SECRET

# Willekeurige sessiesleutel (end="" zodat er geen newline in het secret komt)
python3 -c "import secrets; print(secrets.token_urlsafe(48), end='')" | gcloud secrets create reporth-v3-session-secret --data-file=-
```

Databaseverbinding: op Cloud Run is er geen Auth Proxy. `--add-cloudsql-instances` maakt
de Unix-socket `/cloudsql/<instance>` aan, dus de URL wijst daarnaar in plaats van naar
`127.0.0.1`. Dit commando leest de lokale URL uit `.env`, zet die om naar de socketvorm en
bewaart ze als secret, zonder ze te tonen:

```bash
python3 - <<'PY' | gcloud secrets create reporth-v3-database-url --data-file=-
from urllib.parse import urlparse
url = next(l.split("=", 1)[1].strip().strip('"') for l in open(".env") if l.startswith("DATABASE_URL="))
u = urlparse(url)
userinfo = u.netloc.rsplit("@", 1)[0]
print(f"postgresql://{userinfo}@{u.path}?host=/cloudsql/orthopediereportingproject:europe-west1:orthopedie-reporting-db", end="")
PY
```

Een nieuwe versie van de client secret zet je met
`gcloud secrets versions add reporth-v3-entra-client-secret --data-file=-` (met dezelfde `read -s`).
Herdeploy daarna, of maak een nieuwe revisie, zodat Cloud Run `latest` opnieuw leest.

## Deployen

```bash
./deploy.sh
```

Het script doet het volgende:

1. Het controleert dat de drie secrets bestaan.
2. Het maakt de Artifact Registry-repo `reporth` en de serviceaccounts aan als ze nog
   ontbreken:
   - `reporth-v3@` voor runtime, met `secretAccessor` op de drie secrets en `roles/cloudsql.client`;
   - `reporth-v3-build@` voor Cloud Build, met `roles/run.builder`.
3. Het bouwt de image met Cloud Build.
4. Het deployt naar Cloud Run in `europe-west1` en toont de service-URL.

Omdat het script idempotent is, kun je het gerust opnieuw draaien.

De IAM-binding voor de secrets kun je ook los zetten:

```bash
for s in reporth-v3-entra-client-secret reporth-v3-session-secret reporth-v3-database-url; do
  gcloud secrets add-iam-policy-binding "$s" \
    --member serviceAccount:reporth-v3@orthopediereportingproject.iam.gserviceaccount.com \
    --role roles/secretmanager.secretAccessor
done
```

## Custom domein v3.reporth.be

1. **Domain mapping aanmaken.** `reporth.be` is al geverifieerd, want
   `procedures.reporth.be` draait in hetzelfde project.
   ```bash
   gcloud beta run domain-mappings create --service reporth-v3 --domain v3.reporth.be --region europe-west1
   ```
   Wordt er toch om verificatie gevraagd, gebruik dan `gcloud domains verify reporth.be`.
2. **DNS bij Vercel** (project/domein `reporth.be` → DNS Records). Voeg dit record toe:

   | Type | Name | Value |
   |---|---|---|
   | CNAME | `v3` | `ghs.googlehosted.com.` |
3. **Wachten op het certificaat.** Dat duurt meestal 15 tot 30 minuten, soms langer.
   Controleer de status zo:
   ```bash
   gcloud beta run domain-mappings describe --domain v3.reporth.be --region europe-west1 \
     --format "yaml(status.conditions)"
   ```
   Het certificaat is actief zodra `Ready`, `CertificateProvisioned` en `DomainRoutable`
   op `True` staan. Testen kan met `curl -I https://v3.reporth.be/health`.

## Privacy en logging

- De sessie bevat enkel `name`, `email`, `oid` en `tid`, en geen tokens. Het is een
  gesigneerde cookie `reporth_session`, 8 uur geldig.
- De logs (stdout, dus Cloud Logging) bevatten enkel `login ok` of
  `login geweigerd reden=…` met `tid` en `oid`. Namen, e-mailadressen en tokens worden
  nooit gelogd.
- Er is geen analytics. Er zijn geen externe scripts.
