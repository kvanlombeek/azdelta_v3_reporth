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
    assert [z for z, _ in zalen] == ["M OK zaal 1", "M OK zaal 2"]
    assert [r["tijd"] for r in zalen[0][1]] == ["7:45", "10:37"]  # op tijd, niet als tekst
    assert o["dagen"][1]["zalen"][0][1][0]["tijd"] == "–"


def test_landing_toont_week_van_aangemelde_arts(monkeypatch):
    calls = fake_db(monkeypatch, [ingreep(date(2026, 10, 23), "7:45"), ingreep(date(2026, 10, 23), "8:00", gerapporteerd=True)])
    r = login(monkeypatch).get("/")
    assert r.status_code == 200
    assert calls == [("AZDelta", "dr.test@azdelta.be", MAANDAG)]
    assert ">dr. Alexander Ryckaert</h1>" in r.text
    assert "Week 43 · 19 – 25 oktober 2026" in r.text
    assert ">1/2</span> ingrepen deze week reeds getarificeerd" in r.text
    assert "Knie: Artroscopie knie" in r.text
    assert 'data-tab="4" aria-selected="true"' in r.text  # vandaag = vrijdag


def test_landing_andere_arts_en_week(monkeypatch):
    calls = fake_db(monkeypatch, [])
    r = login(monkeypatch).get("/?arts=andere@azdelta.be&week=2026-10-29&dag=2")
    assert calls == [("AZDelta", "andere@azdelta.be", date(2026, 10, 26))]
    assert ">dr. Andere Arts</h1>" in r.text
    assert 'data-tab="2" aria-selected="true"' in r.text


def test_landing_onbekende_arts_wordt_genegeerd(monkeypatch):
    calls = fake_db(monkeypatch, [])
    login(monkeypatch).get("/?arts=iemand@elders.be&week=onzin")
    assert calls == [("AZDelta", "dr.test@azdelta.be", MAANDAG)]


def test_landing_zonder_gekoppelde_arts(monkeypatch):
    calls = fake_db(monkeypatch, [])
    monkeypatch.setattr(planning, "artsen", lambda *_: _async([{"naam": "dr. Andere Arts", "email": "andere@azdelta.be"}]))
    r = login(monkeypatch).get("/")
    assert calls == []
    assert "Kies een arts" in r.text


def test_landing_zonder_database(monkeypatch):
    # De pool is in de tests niet open (geen lifespan): de query faalt.
    r = login(monkeypatch).get("/")
    assert r.status_code == 503
    assert "Planning niet beschikbaar" in r.text
    assert "test:test" not in r.text  # nooit de URL of het wachtwoord tonen


async def _async(value):
    return value
