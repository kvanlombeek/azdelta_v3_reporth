from datetime import date

from app import ingrepen, planning
from app.config import settings
from tests.test_planning import login

ARTSEN = [
    {"naam": "dr. Test", "email": "Dr.Test@azdelta.be", "actief": True},
    {"naam": "dr. Andere", "email": "andere@azdelta.be", "actief": False},  # inactieve arts: historiek blijft zichtbaar
]
RIJ = {
    "ingreep_id": 7, "date_procedure": date(2026, 10, 1), "patient_id": "P1", "arts_email": "andere@azdelta.be",
    "domein": "Knie", "lateraliteit": "Links", "campus_naam": "Roeselare", "ambulant_gehospitaliseerd": "Ambulant",
    "detailformulier": "", "hoofd_key": "H1", "hoofd_naam": "Hoofdnaam", "geslacht": "man", "geboortedatum": date(1970, 10, 2),
    "totaal": 120,
}


def fake(monkeypatch, assistent=False, rijen=(RIJ,), procs=None):
    gezien = {}

    async def artsen(ortho_group):
        gezien["groep"] = ortho_group
        return ARTSEN

    async def is_assistent(ortho_group, email, vandaag):
        return assistent

    async def zoek(emails, regio, van, tot, q, patient, pagina):
        gezien["zoek"] = (emails, regio, van, tot, q, patient, pagina)
        return {"totaal": 120, "rijen": list(rijen), "procedures": procs or {}}

    monkeypatch.setattr(ingrepen, "artsen", artsen)
    monkeypatch.setattr(ingrepen, "is_assistent", is_assistent)
    monkeypatch.setattr(ingrepen, "zoek", zoek)
    monkeypatch.setattr(planning, "vandaag", lambda: date(2026, 10, 24))
    return gezien


def test_zonder_sessie_401():
    from fastapi.testclient import TestClient

    from app.main import app

    assert TestClient(app).get("/api/ingrepen").status_code == 401


def test_arts_ziet_enkel_zichzelf_ook_met_arts_parameter(monkeypatch):
    gezien = fake(monkeypatch)
    r = login(monkeypatch).get("/api/ingrepen?arts=andere@azdelta.be")  # genegeerd
    assert r.status_code == 200
    assert gezien["zoek"][0] == ["dr.test@azdelta.be"] and gezien["groep"] == "AZDelta"
    assert r.json()["mag_alle_artsen"] is False
    assert r.json()["artsen"] == [{"email": "dr.test@azdelta.be", "naam": "dr. Test"}]  # enkel zichzelf


def test_gebruiker_buiten_de_groep_403(monkeypatch):
    fake(monkeypatch)

    async def andere_groep(ortho_group):
        return [{"naam": "x", "email": "x@azdelta.be", "actief": True}]

    monkeypatch.setattr(ingrepen, "artsen", andere_groep)  # de aangemelde gebruiker staat er niet in, is geen admin of assistent
    assert login(monkeypatch).get("/api/ingrepen").status_code == 403


def test_assistent_kiest_arts_of_ziet_alle_artsen_van_de_groep(monkeypatch):
    gezien = fake(monkeypatch, assistent=True)
    c = login(monkeypatch)
    r = c.get("/api/ingrepen")
    assert gezien["zoek"][0] == ["dr.test@azdelta.be", "andere@azdelta.be"]
    assert r.json()["mag_alle_artsen"] is True and len(r.json()["artsen"]) == 2
    c.get("/api/ingrepen?arts=Andere@azdelta.be&regio=Knie&q=kruisband&patient=2014126260&van=2026-01-01&tot=2026-02-01&pagina=2")
    assert gezien["zoek"] == (["andere@azdelta.be"], "Knie", date(2026, 1, 1), date(2026, 2, 1), "kruisband", "2014126260", 2)
    assert c.get("/api/ingrepen?arts=vreemd@ander.be").status_code == 422  # enkel artsen uit de eigen groep


def test_admin_ziet_alle_artsen(monkeypatch):
    gezien = fake(monkeypatch)
    monkeypatch.setattr(settings, "admin_emails", frozenset({"dr.test@azdelta.be"}))
    login(monkeypatch).get("/api/ingrepen")
    assert len(gezien["zoek"][0]) == 2


def test_filters_worden_gevalideerd(monkeypatch):
    fake(monkeypatch)
    c = login(monkeypatch)
    assert c.get("/api/ingrepen?regio=Onzin").status_code == 422
    assert c.get("/api/ingrepen?van=gisteren").status_code == 422
    assert c.get("/api/ingrepen?pagina=0").status_code == 422


def test_antwoord_vorm_en_terugval_op_hoofdprocedure(monkeypatch):
    fake(monkeypatch, assistent=True)
    d = login(monkeypatch).get("/api/ingrepen").json()
    assert (d["totaal"], d["pagina"], d["per_pagina"]) == (120, 1, 50)
    i = d["ingrepen"][0]
    assert i["leeftijd"] == 55 and i["arts"] == "dr. Andere" and "geboortedatum" not in i
    assert i["procedures"] == [{"procedure_key": "H1", "naam": "Hoofdnaam", "zijden": [], "stralen": []}]  # geen kindrijen
    assert i["detailformulier"] is None


def test_zonder_database_503(monkeypatch):
    assert login(monkeypatch).get("/api/ingrepen").status_code == 503


def test_procedures_groeperen_per_ingreep():
    rijen = [
        {"ingreep_id": 1, "procedure_key": "a", "procedure_name": "A", "lateraliteit": "7771000", "stralen": "straal3"},
        {"ingreep_id": 1, "procedure_key": "a", "procedure_name": "A", "lateraliteit": "7771000", "stralen": "straal4"},
        {"ingreep_id": 1, "procedure_key": "a", "procedure_name": "A", "lateraliteit": "24028007", "stralen": "straal3"},
        {"ingreep_id": 1, "procedure_key": "b", "procedure_name": "B", "lateraliteit": "24847006", "stralen": None},
    ]
    g = ingrepen.procedures_per_ingreep(rijen)[1]
    assert g == [
        {"procedure_key": "a", "naam": "A", "zijden": ["Links", "Rechts"], "stralen": [3, 4]},
        {"procedure_key": "b", "naam": "B", "zijden": [], "stralen": []},
    ]


def test_like_escape():
    assert ingrepen.like_escape("100%_a\\") == "100\\%\\_a\\\\"


# --- Een opgeslagen ingreep openen in het tarificatieformulier ---

from app import procedures, tarificatie, tarificatie_codes  # noqa: E402

INGREEP = {
    "ingreep_id": 7, "date_procedure": date(2026, 10, 1), "campus_code": "1100", "opname_id": "204798102",
    "ambulant_gehospitaliseerd": "Ambulant", "arts_email": "dr.test@azdelta.be", "assistent_interne_nummer": "42",
    "domein": "Knie", "cd_ltrlty": "51440002", "patient_id": "P1", "procedure_key": "p1",
    "geslacht": "man", "geboortedatum": date(1970, 10, 2),
}
PROC_RIJEN = [
    {"procedure_key": "p1", "procedure_name": "Eerste", "lateraliteit": "7771000", "stralen": None},
    {"procedure_key": "p1", "procedure_name": "Eerste", "lateraliteit": "24028007", "stralen": None},
    {"procedure_key": "oud", "procedure_name": "Oude procedure", "lateraliteit": "24028007", "stralen": "straal3"},
    {"procedure_key": "oud", "procedure_name": "Oude procedure", "lateraliteit": "24028007", "stralen": "straal4"},
]
TARIEF = [
    {"nomenclatuur": "RA", "n_waarde": "N 55", "lateraliteit": None, "straal": None, "label_short_nl": "Radioscopie"},
    {"nomenclatuur": "A1", "n_waarde": "N 100", "lateraliteit": "Rechts", "straal": None, "label_short_nl": "Hoofd"},
    {"nomenclatuur": "A1", "n_waarde": "N 100", "lateraliteit": "Links", "straal": None, "label_short_nl": "Hoofd"},
    {"nomenclatuur": "ZZ", "n_waarde": None, "lateraliteit": None, "straal": None, "label_short_nl": None},
]
P1 = {"procedure_key": "p1", "procedure_name": "Eerste", "nc_main_A": "A1", "nc_main_H": "H1", "nc_extra": ["RA"], "nc_gips": [], "nc_beeldvorming": [], "verschillende_stralen": False}


def fake_bestaand(monkeypatch, ingreep=INGREEP, assistent=False):
    gezien = fake(monkeypatch, assistent=assistent)

    async def bestaande(ingreep_id):
        gezien["id"] = ingreep_id
        return ingreep

    async def rijen(ingreep_id):
        return PROC_RIJEN, TARIEF

    async def bij_sleutels(sleutels):
        return {"p1": {"procedure_key": "p1", "procedure_name": "Eerste"}}

    async def laad(sleutels, streng=True):
        gezien["streng"] = streng
        return [P1], NOMENCLATUUR_TEST

    async def leeg(*a):
        return []

    monkeypatch.setattr(tarificatie, "bestaande_ingreep", bestaande)
    monkeypatch.setattr(tarificatie, "opgeslagen_rijen", rijen)
    monkeypatch.setattr(procedures, "bij_sleutels", bij_sleutels)
    monkeypatch.setattr(tarificatie_codes, "laad", laad)
    monkeypatch.setattr(tarificatie, "campussen", leeg)
    monkeypatch.setattr(tarificatie, "assistenten", leeg)
    return gezien


NOMENCLATUUR_TEST = {"RA": {"label": "Radioscopie", "n_waarde": "N 55", "verblijf": "ambulant", "partner": "RH"}}
URL_BESTAAND = "/api/tarificatie/ingreep/7"


def test_bestaande_tarificatie_zonder_sessie_401():
    from fastapi.testclient import TestClient

    from app.main import app

    assert TestClient(app).get(URL_BESTAAND).status_code == 401


def test_bestaande_tarificatie_toont_opgeslagen_codes_ongewijzigd(monkeypatch):
    gezien = fake_bestaand(monkeypatch)
    r = login(monkeypatch).get(URL_BESTAAND)
    assert r.status_code == 200 and gezien["id"] == 7 and gezien["streng"] is False
    d = r.json()
    assert d["patient"] == {"geslacht": "man", "leeftijd": 55} and d["voorinvulling"]["assistent"] == "42"
    assert d["voorinvulling"]["lateraliteit"] == "51440002" and d["voorinvulling"]["regio"] == "Knie"
    o = d["opgeslagen"]
    assert o["procedure_key"] == "p1"
    # Procedures met hun selecties; een onbekende (oude) procedure krijgt een minimaal object.
    assert [p["procedure"]["procedure_key"] for p in o["procedures"]] == ["p1", "oud"]
    assert o["procedures"][0]["selecties"] == [{"zijde": "Links", "straal": None}, {"zijde": "Rechts", "straal": None}]
    assert o["procedures"][1]["selecties"] == [{"zijde": "Rechts", "straal": 3}, {"zijde": "Rechts", "straal": 4}]
    assert o["procedures"][1]["procedure"]["verschillende_stralen"] is True
    # Codes zoals opgeslagen: procedurecodes eerst, dan extra, dan overig.
    assert [(x["code"], x["soort"], x["zijde"]) for x in o["rijen"]] == [
        ("A1", "Procedure", "Links"), ("A1", "Procedure", "Rechts"), ("RA", "Extra", None), ("ZZ", "Overig", None),
    ]
    assert o["rijen"][0]["procedure"] == "Eerste" and o["rijen"][0]["label"] == "Hoofd"


def test_bestaande_tarificatie_andere_arts_404(monkeypatch):
    fake_bestaand(monkeypatch, ingreep={**INGREEP, "arts_email": "andere@azdelta.be"})
    assert login(monkeypatch).get(URL_BESTAAND).status_code == 404  # gewone arts: enkel eigen ingrepen


def test_bestaande_tarificatie_assistent_mag_andere_arts(monkeypatch):
    fake_bestaand(monkeypatch, ingreep={**INGREEP, "arts_email": "andere@azdelta.be"}, assistent=True)
    assert login(monkeypatch).get(URL_BESTAAND).status_code == 200


def test_bestaande_tarificatie_arts_buiten_groep_404(monkeypatch):
    fake_bestaand(monkeypatch, ingreep={**INGREEP, "arts_email": "vreemd@ander.be"}, assistent=True)
    assert login(monkeypatch).get(URL_BESTAAND).status_code == 404  # andere groep, ook voor admins en assistenten


def test_bestaande_tarificatie_onbekend_en_ongeldig(monkeypatch):
    fake_bestaand(monkeypatch, ingreep=None)
    c = login(monkeypatch)
    assert c.get(URL_BESTAAND).status_code == 404
    assert c.get("/api/tarificatie/ingreep/0").status_code == 404
    assert c.get("/api/tarificatie/ingreep/abc").status_code == 422
