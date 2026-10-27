"""Tarificatie, stap 1: de geplande ingreep controleren.

Leest de geplande ingreep (patient.geplande_procedure) en de keuzelijsten voor het
controleformulier. Enkel lezen; het opslaan in procedures_production.ingrepen volgt later.
"""

import re
from datetime import date, timedelta

from psycopg.rows import dict_row

from app import db, tarificatie_codes

# Enkel recente planningen: de patiënttabel bevat ook heel oude planningen.
MAX_DAGEN_TERUG = 30

# Voorlopig enkel AZ Delta. Later af te leiden van de aangemelde gebruiker (tid).
ZIEKENHUIS_CAMPUSSEN = "AZ Delta"

LICHAAMSREGIOS = ["Elleboog/Voorarm", "Enkel/Voet", "Hand/Pols", "Heup", "Knie", "Rug", "Schouder", "Bekken"]
AMBULANT_GEHOSPITALISEERD = ["Ambulant", "Gehospitaliseerd"]
# SNOMED-code (zoals in planning en ingrepen.cd_ltrlty) -> tekst (ingrepen.lateraliteit).
LATERALITEIT = {
    "7771000": "Links",
    "24028007": "Rechts",
    "51440002": "Bilateraal",
    "24847006": "Niet van toepassing",
}

# Gedeeld met de planningsquery: de hash in de link moet exact overeenkomen.
PLANNING_HASH_SQL = "left(md5(p.geplande_procedure::text), 12)"

PLANNING_SQL = f"""
SELECT
    p.patient_id,
    {PLANNING_HASH_SQL} AS planning_hash,
    p.geplande_procedure->>'date_procedure' AS datum,
    p.geplande_procedure->>'campus' AS campus_code,
    p.geplande_procedure->>'opname_id' AS opname_id,
    p.geplande_procedure->>'ambulant_gehospitaliseerd' AS ambulant_gehospitaliseerd,
    p.geplande_procedure->>'arts_email' AS arts_email,
    p.geplande_procedure->>'domein' AS domein,
    p.geplande_procedure->>'beschrijving' AS beschrijving,
    p.geplande_procedure->>'lateraliteit' AS lateraliteit,
    p.geplande_procedure->'geplande_procedure_keys' AS procedure_keys,
    p.geslacht,
    p.date_of_birth::date AS geboortedatum
FROM procedures_production.patient p
WHERE p.patient_id = %(patient_id)s
  AND p.ortho_group = %(ortho_group)s
  AND p.geplande_procedure->>'date_procedure' >= %(van)s
"""

CAMPUSSEN_SQL = """
SELECT campus_code, campus_naam
FROM curated_form_fields.ziekenhuizen_campussen
WHERE ziekenhuis = %(ziekenhuis)s
ORDER BY campus_naam
"""

# Assistenten moeten op de datum van de ingreep actief zijn en een RIZIV-nummer hebben.
ASSISTENTEN_SQL = """
SELECT internnummer, naam
FROM procedures_production.assistenten
WHERE ortho_group = %(ortho_group)s
  AND actief_vanaf <= %(datum)s
  AND (actief_tot IS NULL OR actief_tot >= %(datum)s)
  AND rizivnr IS NOT NULL AND rizivnr <> ''
ORDER BY naam
"""


async def _alle(sql: str, params: dict) -> list[dict]:
    async with db.pool.connection(timeout=5) as conn:
        cur = conn.cursor(row_factory=dict_row)
        await cur.execute(sql, params)
        return await cur.fetchall()


async def geplande_ingreep(ortho_group: str, patient_id: str, van: date) -> dict | None:
    rijen = await _alle(PLANNING_SQL, {"ortho_group": ortho_group, "patient_id": patient_id, "van": van.isoformat()})
    return rijen[0] if rijen else None


async def campussen() -> list[dict]:
    return await _alle(CAMPUSSEN_SQL, {"ziekenhuis": ZIEKENHUIS_CAMPUSSEN})


async def assistenten(ortho_group: str, datum: date) -> list[dict]:
    return await _alle(ASSISTENTEN_SQL, {"ortho_group": ortho_group, "datum": datum})


def vroegste_datum(vandaag: date) -> date:
    return vandaag - timedelta(days=MAX_DAGEN_TERUG)


def gematchte_sleutels(waarde) -> list[str]:
    """De vooraf gematchte procedure_keys uit de planning (JSON-lijst): zonder spaties of dubbels, in volgorde.

    Sommige sleutels in de planning hebben een spatie midden in (bv. '39137000 _VOET'); die wordt weggehaald.
    """
    if not isinstance(waarde, list):
        return []
    schoon = (re.sub(r"\s+", "", s) for s in waarde if isinstance(s, str))
    return list(dict.fromkeys(s for s in schoon if s))


def leeftijd(geboortedatum: date | None, op: date) -> int | None:
    """Leeftijd in hele jaren op de datum van de ingreep."""
    if not geboortedatum or geboortedatum > op:
        return None
    return op.year - geboortedatum.year - ((op.month, op.day) < (geboortedatum.month, geboortedatum.day))


def _keuze(waarde: str | None, toegelaten) -> str | None:
    return waarde if waarde in toegelaten else None


def voorinvulling(planning: dict, campus_codes: set[str]) -> dict:
    """Zet de planningsgegevens om naar formulierwaarden.

    Waarden die niet in de keuzelijst passen (bv. 'Domein nog onbekend', oude
    codes voor ambulant/gehospitaliseerd) blijven leeg, zodat de arts zelf kiest.
    """
    return {
        "datum": planning["datum"],
        "campus_code": _keuze(planning["campus_code"], campus_codes),
        "opname_id": planning["opname_id"] or None,
        "ambulant_gehospitaliseerd": _keuze(planning["ambulant_gehospitaliseerd"], AMBULANT_GEHOSPITALISEERD),
        "arts_email": (planning["arts_email"] or "").lower() or None,
        "regio": _keuze(planning["domein"], LICHAAMSREGIOS),
        "lateraliteit": _keuze(planning["lateraliteit"], LATERALITEIT),
        # Startpunt voor het zoeken naar procedures (korte tekst zoals "Cts release open").
        "beschrijving": (planning["beschrijving"] or "").strip() or None,
    }


# --- Een reeds opgeslagen ingreep (voor het openen in het formulier) ---

INGREEP_SQL = """
SELECT g.ingreep_id, g.date_procedure, g.campus_code, g.opname_id, g.ambulant_gehospitaliseerd, g.arts_email,
       g.assistent_interne_nummer, g.domein, g.cd_ltrlty, g.patient_id, g.procedure_key,
       p.geslacht, p.date_of_birth::date AS geboortedatum
FROM procedures_production.ingrepen g
LEFT JOIN procedures_production.patient p ON p.patient_id = g.patient_id
WHERE g.ingreep_id = %(ingreep_id)s
"""
OPGESLAGEN_PROCEDURES_SQL = """
SELECT procedure_key, procedure_name, lateraliteit, stralen
FROM procedures_production.procedures_ingrepen_autoid
WHERE ingreep_id = %(ingreep_id)s
ORDER BY procedure_id
"""
OPGESLAGEN_TARIFICATIE_SQL = """
SELECT nomenclatuur, n_waarde, lateraliteit, straal, label_short_nl
FROM procedures_production.tarificaties_ingrepen_autoid
WHERE ingreep_id = %(ingreep_id)s
"""


async def bestaande_ingreep(ingreep_id: int) -> dict | None:
    rijen = await _alle(INGREEP_SQL, {"ingreep_id": ingreep_id})
    return rijen[0] if rijen else None


async def opgeslagen_rijen(ingreep_id: int) -> tuple[list[dict], list[dict]]:
    """(procedurerijen, tarificatierijen) zoals ze in de database staan."""
    return (
        await _alle(OPGESLAGEN_PROCEDURES_SQL, {"ingreep_id": ingreep_id}),
        await _alle(OPGESLAGEN_TARIFICATIE_SQL, {"ingreep_id": ingreep_id}),
    )


ZIJDE_VAN_SNOMED = {"7771000": ["Links"], "24028007": ["Rechts"], "51440002": ["Links", "Rechts"], "24847006": ["Geen"]}


def _straal(tekst: str | None) -> int | None:
    t = tekst or ""
    return int(t[6:]) if t.startswith("straal") and t[6:].isdigit() else None


def opgeslagen_procedures(rijen: list[dict], gevonden: dict[str, dict]) -> list[dict]:
    """Per procedure (in opslagvolgorde): de procedure en de (zijde, straal)-selecties die de arts koos.

    gevonden: de procedures die nog in de lijst staan; voor een onbekende procedure (oude data) volstaat een minimaal object.
    """
    per_key: dict[str, dict] = {}
    for r in rijen:
        k = per_key.setdefault(r["procedure_key"], {"naam": r["procedure_name"], "selecties": [], "stralen": False})
        straal = _straal(r["stralen"])
        k["stralen"] = k["stralen"] or straal is not None
        for zijde in ZIJDE_VAN_SNOMED.get(r["lateraliteit"] or "", ["Geen"]):
            selectie = {"zijde": zijde, "straal": straal}
            if selectie not in k["selecties"]:
                k["selecties"].append(selectie)
    return [
        {
            "procedure": gevonden.get(key) or {
                "procedure_key": key, "procedure_name": k["naam"], "domein": None, "nc_main_A": None, "nc_main_H": None,
                "label_A": None, "label_H": None, "verschillende_stralen": k["stralen"], "code_match": [], "frequentie": None,
            },
            "selecties": k["selecties"],
        }
        for key, k in per_key.items()
    ]


def opgeslagen_codes(tarief: list[dict], gekozen: list[dict], nomenclatuur: dict) -> list[dict]:
    """De opgeslagen tarificatie als rijen voor het scherm, ongewijzigd (niet opnieuw berekend).

    Procedurecodes eerst (per zijde en straal), dan extra, beeldvorming, gips en overige. Ids als in tarificatie_codes.voorstel:
    hoofdcodes `hoofd:{code}:{zijde}:{straal}`, de rest de code zelf.
    """
    volgorde = {"Procedure": 0, "Extra": 1, "Beeldvorming": 2, "Gips": 3, "Overig": 4}
    rijen: list[dict] = []
    gezien: set[str] = set()
    for t in tarief:
        code = t["nomenclatuur"]
        soort, naam = tarificatie_codes.soort_van(code, gekozen, nomenclatuur)
        zijde = t["lateraliteit"] if t["lateraliteit"] in ("Links", "Rechts") else None
        straal = _straal(t["straal"])
        id_ = f"hoofd:{code}:{zijde or 'Geen'}:{straal or '-'}" if soort == "Procedure" else code
        if id_ in gezien:
            continue
        gezien.add(id_)
        rijen.append({
            "id": id_, "code": code, "soort": soort, "label": t["label_short_nl"], "n_waarde": t["n_waarde"],
            "procedure": naam, "zijde": zijde, "straal": straal,
        })
    return sorted(rijen, key=lambda r: (volgorde[r["soort"]], r["code"], r["zijde"] or "", r["straal"] or 0))
