from datetime import date

from fastapi.testclient import TestClient

from app import planning, tarificatie
from app.main import app
from tests.test_planning import ARTSEN, login

URL = "/api/tarificatie/nieuw/P1/abcdef123456"
VANDAAG = date(2026, 10, 24)

PLAN = {
    "patient_id": "P1",
    "planning_hash": "abcdef123456",
    "datum": "2026-10-23",
    "campus_code": "1100",
    "opname_id": "204798102",
    "ambulant_gehospitaliseerd": "Gehospitaliseerd",
    "arts_email": "dr.test@azdelta.be",
    "domein": "Heup",
    "lateraliteit": "7771000",
    "beschrijving": " Artroscopie knie ",
    "procedure_keys": ["39137000 _VOET", " 66339000_A0", "39137000_VOET", 5],
    "geslacht": "man",
    "geboortedatum": date(1970, 10, 24),
}
CAMPUSSEN = [{"campus_code": "1100", "campus_naam": "AZ Delta Brugsesteenweg"}]
ASSISTENTEN = [{"internnummer": "42", "naam": "dr. Assistent"}]


def fake_db(monkeypatch, plan=PLAN):
    calls = {}

    async def artsen(ortho_group):
        return ARTSEN

    async def geplande_ingreep(ortho_group, patient_id, van):
        calls["plan"] = (ortho_group, patient_id, van)
        return plan

    async def campussen():
        return CAMPUSSEN

    async def assistenten(ortho_group, datum):
        calls["assistenten"] = (ortho_group, datum)
        return ASSISTENTEN

    monkeypatch.setattr(planning, "artsen", artsen)
    monkeypatch.setattr(planning, "vandaag", lambda: VANDAAG)
    monkeypatch.setattr(tarificatie, "geplande_ingreep", geplande_ingreep)
    monkeypatch.setattr(tarificatie, "campussen", campussen)
    monkeypatch.setattr(tarificatie, "assistenten", assistenten)

    async def gematchte(sleutels, arts_email, k):
        calls["sleutels"] = (sleutels, arts_email, k)
        return [{"procedure_key": s} for s in sleutels]

    from app import procedures

    monkeypatch.setattr(procedures, "gematchte_procedures", gematchte)
    return calls


def test_zonder_sessie_401():
    r = TestClient(app, follow_redirects=False).get(URL)
    assert r.status_code == 401


def test_voorinvulling_en_opties(monkeypatch):
    calls = fake_db(monkeypatch)
    r = login(monkeypatch).get(URL)
    assert r.status_code == 200
    data = r.json()
    assert data["voorinvulling"] == {
        "datum": "2026-10-23",
        "campus_code": "1100",
        "opname_id": "204798102",
        "ambulant_gehospitaliseerd": "Gehospitaliseerd",
        "arts_email": "dr.test@azdelta.be",
        "regio": "Heup",
        "lateraliteit": "7771000",
        "beschrijving": "Artroscopie knie",
    }
    assert data["patient"] == {"geslacht": "man", "leeftijd": 55}  # geboortedatum zelf gaat niet mee
    assert "1970" not in r.text
    # Gematchte procedures uit de planning: spaties weg, geen dubbels, volgorde behouden.
    assert calls["sleutels"] == (["39137000_VOET", "66339000_A0"], "dr.test@azdelta.be", 10)
    assert [p["procedure_key"] for p in data["gematchte_procedures"]] == ["39137000_VOET", "66339000_A0"]
    assert data["opties"]["campussen"] == CAMPUSSEN
    assert data["opties"]["assistenten"] == ASSISTENTEN
    assert data["opties"]["regios"] == tarificatie.LICHAAMSREGIOS
    # Isolatie: query filtert op de groep, en enkel recente planningen (30 dagen).
    assert calls["plan"] == ("AZDelta", "P1", date(2026, 9, 24))
    # Assistenten worden gefilterd op de datum van de ingreep, niet op vandaag.
    assert calls["assistenten"] == ("AZDelta", date(2026, 10, 23))


def test_onbekende_of_andere_groep_404(monkeypatch):
    fake_db(monkeypatch, plan=None)
    assert login(monkeypatch).get(URL).status_code == 404


def test_arts_buiten_groep_404(monkeypatch):
    fake_db(monkeypatch, plan={**PLAN, "arts_email": "vreemd@ander.be"})
    assert login(monkeypatch).get(URL).status_code == 404


def test_gewijzigde_planning_409(monkeypatch):
    fake_db(monkeypatch, plan={**PLAN, "planning_hash": "000000000000"})
    assert login(monkeypatch).get(URL).status_code == 409


def test_ongeldige_hash_404(monkeypatch):
    fake_db(monkeypatch)
    assert login(monkeypatch).get("/api/tarificatie/nieuw/P1/zzz").status_code == 404


def test_db_onbereikbaar_503(monkeypatch):
    fake_db(monkeypatch)

    async def stuk(*a):
        raise ConnectionError

    monkeypatch.setattr(tarificatie, "campussen", stuk)
    assert login(monkeypatch).get(URL).status_code == 503


def test_ongeldige_waarden_blijven_leeg():
    plan = {**PLAN, "domein": "Domein nog onbekend", "ambulant_gehospitaliseerd": "F", "lateraliteit": "x", "campus_code": "9999", "opname_id": "", "beschrijving": "  "}
    v = tarificatie.voorinvulling(plan, {"1100"})
    assert v["regio"] is None
    assert v["ambulant_gehospitaliseerd"] is None
    assert v["lateraliteit"] is None
    assert v["campus_code"] is None
    assert v["opname_id"] is None
    assert v["beschrijving"] is None


def test_code_parts_en_naam():
    from app import procedures

    assert procedures.code_parts("285250-285261") == ["285250", "285261"]
    assert procedures.code_parts("28.52.50") == ["285250"]
    tekst = "Procedure: Carpale tunnel\n release\nDomein: Hand/Pols\nOmschrijving: x"
    assert procedures.procedure_naam(tekst) == "Carpale tunnel release"
    assert procedures.procedure_naam(None) is None


def test_populariteit_en_fusie():
    from app import procedures

    assert [procedures.popularity(f) for f in (None, 0, 1, 9, 10, 99, 100, 800)] == [0, 0, 1, 2, 3, 4, 5, 5]
    scores = procedures.fuseer([["a", "b"], ["b", "c"]])
    assert max(scores, key=scores.get) == "b"  # in beide lijsten


def test_api_procedures_valideert_domein_en_geeft_door(monkeypatch):
    from app import procedures

    gezien = []

    async def zoek(q, domein, k, sorteer):
        gezien.append((q, domein, k, sorteer))
        return {"totaal": 0, "resultaten": [], "waarschuwingen": []}

    monkeypatch.setattr(procedures, "zoek", zoek)
    c = login(monkeypatch)
    assert TestClient(app).get("/api/procedures").status_code == 401
    assert c.get("/api/procedures?domein=Onzin").status_code == 422  # whitelist
    assert c.get("/api/procedures?q=knie&domein=Knie&k=5").status_code == 200
    assert c.get("/api/procedures").status_code == 200
    assert c.get("/api/procedures?sorteer=onzin").status_code == 422  # whitelist
    assert c.get("/api/procedures?q=a&sorteer=populariteit").status_code == 200
    assert gezien == [("knie", "Knie", 5, "fit"), ("", None, 10, "fit"), ("a", None, 10, "populariteit")]


def test_api_procedures_zonder_database_503(monkeypatch):
    assert login(monkeypatch).get("/api/procedures?q=knie").status_code == 503


def test_orden_op_fit_of_populariteit():
    from app import procedures

    rij = [("a", []), ("b", []), ("c", [])]
    details = {"a": {"frequentie": 2.0}, "b": {"frequentie": None}, "c": {"frequentie": 50.0}}
    assert [s for s, _ in procedures.orden(rij, details, "fit", 2)] == ["a", "b"]
    assert [s for s, _ in procedures.orden(rij, details, "populariteit", 2)] == ["c", "a"]


def test_codes_splitst_en_negeert_rommel():
    from app import procedures

    assert procedures.codes("288945|288960") == ["288945", "288960"]
    assert procedures.codes("469125") == ["469125"]
    assert procedures.codes("true") == []  # bestaande rommel in de data
    assert procedures.codes(None) == [] and procedures.codes("") == []


def test_api_catalogus(monkeypatch):
    from app import procedures

    async def catalogus():
        return {"procedures": [{"procedure_key": "X"}], "nomenclatuur": {}}

    monkeypatch.setattr(procedures, "catalogus", catalogus)
    assert TestClient(app).get("/api/procedures/catalogus").status_code == 401
    r = login(monkeypatch).get("/api/procedures/catalogus")
    assert r.status_code == 200 and r.json()["procedures"][0]["procedure_key"] == "X"
    assert r.headers["cache-control"] == "private, max-age=3600"


def test_api_catalogus_zonder_database_503(monkeypatch):
    assert login(monkeypatch).get("/api/procedures/catalogus").status_code == 503


def test_partners_enkel_bij_precies_een_partner():
    from app import procedures

    rijen = [
        {"nc_main": "469125", "label_short_nl": "Radioscopie", "n_waarde": "N 55", "verblijf": "gehospitaliseerd", "partner": "469114"},
        {"nc_main": "111111", "label_short_nl": "Dubbel", "n_waarde": "N 1", "verblijf": "ambulant", "partner": "222222"},
        {"nc_main": "111111", "label_short_nl": "Dubbel", "n_waarde": "N 1", "verblijf": "ambulant", "partner": "333333"},
        {"nc_main": "444444", "label_short_nl": "Alleen", "n_waarde": "N 2", "verblijf": "ambulant", "partner": None},
    ]
    p = procedures.partners(rijen)
    assert p["469125"]["partner"] == "469114"
    assert p["111111"]["partner"] is None  # twijfel: liever geen vervanging dan een verkeerde
    assert p["444444"]["partner"] is None


# --- Tarificatie berekenen (app/tarificatie_codes.py) ---

def code(label, n, verblijf, partner=None):
    return {"label": label, "n_waarde": n, "verblijf": verblijf, "partner": partner}


NOMENCLATUUR = {
    "A1": code("Hoofd A", "N 100", "ambulant"),
    "H1": code("Hoofd H", "N 120", "gehospitaliseerd"),
    "A2": code("Tweede A", "K 400", "ambulant"),
    "RA": code("Radioscopie A", "N 55", "ambulant", "RH"),
    "RH": code("Radioscopie H", "N 55", "gehospitaliseerd", "RA"),
    "GA": code("Gips A", "N 20", "ambulant"),  # geen partner
}


def proc(key, a=None, h=None, extra=(), beeld=(), gips=(), stralen=False):
    return {
        "procedure_key": key, "procedure_name": key.title(), "nc_main_A": a, "nc_main_H": h,
        "nc_extra": list(extra), "nc_beeldvorming": list(beeld), "nc_gips": list(gips), "verschillende_stralen": stralen,
    }


def bereken(gekozen, keuzes, verblijf="ambulant"):
    from app import tarificatie_codes

    return tarificatie_codes.voorstel(gekozen, keuzes, verblijf, NOMENCLATUUR)


def test_hoofdcode_per_zijde_en_extra_een_keer():
    r = bereken([proc("p", a="A1", h="H1", extra=["RA"])], {"p": [("Links", None), ("Rechts", None)]})
    assert [(x["code"], x["zijde"], x["straal"]) for x in r["rijen"]] == [("A1", "Links", None), ("A1", "Rechts", None), ("RA", None, None)]


def test_hoofdcode_per_straal():
    r = bereken([proc("p", a="A1", stralen=True)], {"p": [("Rechts", 4), ("Links", 3), ("Links", 5)]})
    assert [(x["zijde"], x["straal"]) for x in r["rijen"]] == [("Links", 3), ("Links", 5), ("Rechts", 4)]
    assert len({x["id"] for x in r["rijen"]}) == 3  # stabiele, unieke id's voor de afwijkingen in de frontend


def test_lateraliteit_niet_van_toepassing_geeft_geen_zijde():
    r = bereken([proc("p", a="A1")], {"p": [("Geen", None)]})
    assert r["rijen"][0]["zijde"] is None


def test_partnercode_bij_ander_verblijf_en_weglaten_zonder_partner():
    p = proc("p", a="A1", h="H1", extra=["RA"], gips=["GA"])
    r = bereken([p], {"p": [("Links", None)]}, verblijf="gehospitaliseerd")
    assert [x["code"] for x in r["rijen"]] == ["H1", "RH"]
    assert r["aangepast"] == ["RA → RH"]
    assert r["weggelaten"] == ["GA (gips): geen variant voor gehospitaliseerd"]


def test_gedeelde_extra_codes_komen_een_keer_voor():
    r = bereken([proc("p", a="A1", extra=["RA"]), proc("q", a="A2", beeld=["RA"])], {"p": [("Links", None)], "q": [("Links", None)]})
    assert [x["code"] for x in r["rijen"]].count("RA") == 1


def test_geen_hoofdcode_voor_verblijf_wordt_gemeld():
    r = bereken([proc("p", a="A1")], {"p": [("Links", None)]}, verblijf="gehospitaliseerd")
    assert r["rijen"] == [] and r["weggelaten"] == ["P: geen RIZIV-code voor gehospitaliseerd"]
    assert r["ingreep_procedure_key"] == "p"


def test_ingreep_procedure_key_hoogste_getal_k_telt_mee():
    from app import tarificatie_codes as tc

    assert [tc.n_getal(x) for x in ("N 588", "N588", "K 35", "K400", None, "")] == [588, 588, 35, 400, 0, 0]
    gekozen = [proc("p", a="A1"), proc("q", a="A2")]  # N 100 tegen K 400: K400 > N100
    assert tc.ingreep_procedure_key(gekozen, "ambulant", NOMENCLATUUR) == "q"
    assert tc.ingreep_procedure_key([], "ambulant", NOMENCLATUUR) is None


BEREKEN = "/api/tarificatie/berekenen"


def verzoek(**kw):
    body = {
        "ambulant_gehospitaliseerd": "Ambulant",
        "procedures": [{"procedure_key": "p", "selecties": [{"zijde": "Links", "straal": None}]}],
    }
    return {**body, **kw}


def fake_laad(monkeypatch, stralen=False):
    from app import tarificatie_codes

    async def laad(keys):
        if "onbekend" in keys:
            raise tarificatie_codes.OnbekendeProcedure
        return [proc(k, a="A1", stralen=stralen) for k in keys], NOMENCLATUUR

    monkeypatch.setattr(tarificatie_codes, "laad", laad)


def test_berekenen_zonder_sessie_401():
    assert TestClient(app).post(BEREKEN, json=verzoek()).status_code == 401


def test_berekenen_geeft_voorstel(monkeypatch):
    fake_laad(monkeypatch)
    r = login(monkeypatch).post(BEREKEN, json=verzoek())
    assert r.status_code == 200
    assert [x["code"] for x in r.json()["rijen"]] == ["A1"] and r.json()["ingreep_procedure_key"] == "p"


def test_berekenen_valideert_invoer(monkeypatch):
    fake_laad(monkeypatch)
    c = login(monkeypatch)
    sel = lambda **s: [{"procedure_key": "p", "selecties": [s]}]  # noqa: E731
    assert c.post(BEREKEN, json=verzoek(ambulant_gehospitaliseerd="F")).status_code == 422
    assert c.post(BEREKEN, json=verzoek(procedures=[])).status_code == 422
    assert c.post(BEREKEN, json=verzoek(procedures=sel(zijde="Boven", straal=None))).status_code == 422
    assert c.post(BEREKEN, json=verzoek(procedures=sel(zijde="Links", straal=6))).status_code == 422
    assert c.post(BEREKEN, json=verzoek(procedures=sel(zijde="Links", straal=2))).status_code == 422  # procedure kent geen stralen
    assert c.post(BEREKEN, json=verzoek(procedures=sel(zijde="Links", straal=None) + sel(zijde="Rechts", straal=None))).status_code == 422  # dubbel
    assert c.post(BEREKEN, json=verzoek(procedures=[{"procedure_key": "onbekend", "selecties": [{"zijde": "Links"}]}])).status_code == 422


def test_berekenen_stralenprocedure_vraagt_straal(monkeypatch):
    fake_laad(monkeypatch, stralen=True)
    c = login(monkeypatch)
    assert c.post(BEREKEN, json=verzoek()).status_code == 422  # straal ontbreekt
    ok = verzoek(procedures=[{"procedure_key": "p", "selecties": [{"zijde": "Links", "straal": 3}]}])
    assert c.post(BEREKEN, json=ok).status_code == 200


def test_berekenen_zonder_database_503(monkeypatch):
    assert login(monkeypatch).post(BEREKEN, json=verzoek()).status_code == 503


def test_leeftijd_op_dag_van_ingreep():
    assert tarificatie.leeftijd(date(1970, 10, 24), date(2026, 10, 23)) == 55
    assert tarificatie.leeftijd(date(1970, 10, 23), date(2026, 10, 23)) == 56
    assert tarificatie.leeftijd(None, date(2026, 10, 23)) is None
    assert tarificatie.leeftijd(date(2030, 1, 1), date(2026, 10, 23)) is None


def test_gematchte_sleutels_zonder_lijst():
    assert tarificatie.gematchte_sleutels(None) == []
    assert tarificatie.gematchte_sleutels("x") == []
    assert tarificatie.gematchte_sleutels([]) == []


def test_orden_gematcht_eerst_eigen_keuzes_van_de_arts():
    from app import procedures

    details = {"a": {"frequentie": 500.0}, "b": {"frequentie": 3.0}, "c": {"frequentie": None}, "d": {"frequentie": 3.0}}
    sleutels = ["a", "b", "c", "d", "onbekend"]
    # De arts koos c het vaakst; b en d staan gelijk (zelfde frequentie): planningsvolgorde.
    assert procedures.orden_gematcht(sleutels, {"c": 9, "b": 1, "d": 1}, details, 10) == ["c", "b", "d", "a"]
    assert procedures.orden_gematcht(sleutels, {}, details, 2) == ["a", "b"]  # zonder historiek: globale frequentie, max. k
