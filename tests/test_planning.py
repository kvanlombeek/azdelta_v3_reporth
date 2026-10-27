from datetime import date

from fastapi.testclient import TestClient

from app import planning
from app.main import app
from tests.test_auth import fake_token, user

MAANDAG = date(2026, 10, 19)
ARTSEN = [
    {"naam": "dr. Alexander Ryckaert", "email": "Dr.Test@azdelta.be"},
    {"naam": "dr. Andere Arts", "email": "andere@azdelta.be"},
]


def ingreep(datum, starttijd, zaal="M OK zaal 1", gerapporteerd=False, beschrijving="Knie: Artroscopie knie"):
    return {
        "patient_id": "P1",
        "planning_hash": "abcdef123456",
        "geslacht": "man",
        "geboortedatum": date(1970, 5, 5),
        "datum": datum,
        "starttijd": starttijd,
        "zaal": zaal,
        "beschrijving": beschrijving,
        "gerapporteerd": gerapporteerd,
    }


def login(monkeypatch):
    client = TestClient(app, follow_redirects=False)
    fake_token(monkeypatch, user())
    client.get("/auth/callback?code=x&state=y")
    return client


def fake_db(monkeypatch, rows):
    calls = []

    async def artsen(ortho_group):
        return ARTSEN

    async def geplande_ingrepen(ortho_group, arts_email, maandag):
        calls.append((ortho_group, arts_email, maandag))
        return rows

    monkeypatch.setattr(planning, "artsen", artsen)
    monkeypatch.setattr(planning, "geplande_ingrepen", geplande_ingrepen)
    monkeypatch.setattr(planning, "vandaag", lambda: date(2026, 10, 23))
    return calls


def test_maandag_van():
    assert planning.maandag_van(date(2026, 10, 25)) == MAANDAG  # zondag
    assert planning.maandag_van(MAANDAG) == MAANDAG


def test_tijd():
    assert planning.tijd("7:45") == (7, 45)
    assert planning.tijd("07:45:00") == (7, 45)
    assert planning.tijd("") is None
    assert planning.tijd(None) is None
    assert planning.tijd("25:00") is None


def test_weekoverzicht_telt_en_sorteert():
    vrijdag = date(2026, 10, 23)
    rows = [
        ingreep(vrijdag, "10:37"),
        ingreep(vrijdag, "7:45"),
        ingreep(vrijdag, "8:21", zaal="M OK zaal 2"),
        ingreep(vrijdag, "9:00", gerapporteerd=True),
        ingreep(date(2026, 10, 20), None),
    ]
    o = planning.weekoverzicht(rows, MAANDAG)
    assert (o["totaal"], o["gerapporteerd"]) == (5, 1)
    assert [d["aantal_open"] for d in o["dagen"]] == [0, 1, 0, 0, 3, 0, 0]
    zalen = o["dagen"][4]["zalen"]
    assert [z["zaal"] for z in zalen] == ["M OK zaal 1", "M OK zaal 2"]
    assert [r["tijd"] for r in zalen[0]["ingrepen"]] == ["7:45", "10:37"]  # op tijd, niet als tekst
    assert o["dagen"][1]["zalen"][0]["ingrepen"][0]["tijd"] == "–"
    assert o["dagen"][4]["datum"] == "2026-10-23"


def test_standaard_dag():
    assert planning.standaard_dag(date(2026, 10, 23), MAANDAG, None) == 4  # vandaag in de week
    o = planning.weekoverzicht([ingreep(date(2026, 10, 28), "7:45")], date(2026, 10, 26))
    assert planning.standaard_dag(date(2026, 10, 23), date(2026, 10, 26), o) == 2  # eerste dag met open ingrepen


def test_api_planning_zonder_sessie_401():
    assert TestClient(app).get("/api/planning").status_code == 401


def test_api_planning_week_van_aangemelde_arts(monkeypatch):
    calls = fake_db(monkeypatch, [ingreep(date(2026, 10, 23), "7:45"), ingreep(date(2026, 10, 23), "8:00", gerapporteerd=True)])
    r = login(monkeypatch).get("/api/planning")
    assert r.status_code == 200
    assert calls == [("AZDelta", "dr.test@azdelta.be", MAANDAG)]
    d = r.json()
    assert (d["maandag"], d["weeknummer"], d["dag_index"]) == ("2026-10-19", 43, 4)  # vandaag = vrijdag
    assert d["arts_email"] == "dr.test@azdelta.be"
    assert (d["overzicht"]["gerapporteerd"], d["overzicht"]["totaal"]) == (1, 2)
    i = d["overzicht"]["dagen"][4]["zalen"][0]["ingrepen"][0]
    assert (i["tijd"], i["patient_id"], i["planning_hash"]) == ("7:45", "P1", "abcdef123456")


def test_api_planning_andere_arts_en_week(monkeypatch):
    calls = fake_db(monkeypatch, [])
    d = login(monkeypatch).get("/api/planning?arts=andere@azdelta.be&week=2026-10-29").json()
    assert calls == [("AZDelta", "andere@azdelta.be", date(2026, 10, 26))]
    assert d["arts_email"] == "andere@azdelta.be"


def test_api_planning_onbekende_arts_wordt_genegeerd(monkeypatch):
    calls = fake_db(monkeypatch, [])
    login(monkeypatch).get("/api/planning?arts=iemand@elders.be&week=onzin")
    assert calls == [("AZDelta", "dr.test@azdelta.be", MAANDAG)]


def test_api_planning_zonder_gekoppelde_arts(monkeypatch):
    calls = fake_db(monkeypatch, [])
    monkeypatch.setattr(planning, "artsen", lambda *_: _async([{"naam": "dr. Andere Arts", "email": "andere@azdelta.be"}]))
    d = login(monkeypatch).get("/api/planning").json()
    assert calls == [] and d["arts_email"] is None and d["overzicht"] is None


def test_api_planning_zonder_database(monkeypatch):
    # De pool is in de tests niet open (geen lifespan): de query faalt.
    r = login(monkeypatch).get("/api/planning")
    assert r.status_code == 503
    assert "test:test" not in r.text  # nooit de URL of het wachtwoord tonen


async def _async(value):
    return value
