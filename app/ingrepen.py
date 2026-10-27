"""Historiek: de ingrepen die al geregistreerd zijn (procedures_production.ingrepen), met filters.

Enkel lezen. Een ingreep heeft geen ortho_group; de isolatie loopt via de artsen van de groep:
alleen ingrepen van artsen uit de eigen groep komen terug.
"""

from datetime import date

from psycopg.rows import dict_row

from app import db
from app.config import settings
from app.tarificatie import LATERALITEIT, leeftijd

PER_PAGINA = 50

ARTSEN_SQL = """
SELECT naam, email, actief
FROM procedures_production.artsen
WHERE ortho_group = %(ortho_group)s AND email IS NOT NULL AND email <> ''
ORDER BY naam
"""

# Assistenten (actief op de opgegeven datum) mogen alle artsen van de groep zien.
ASSISTENT_SQL = """
SELECT 1
FROM procedures_production.assistenten
WHERE ortho_group = %(ortho_group)s AND lower(email) = %(email)s
  AND actief_vanaf <= %(vandaag)s AND (actief_tot IS NULL OR actief_tot >= %(vandaag)s)
LIMIT 1
"""

# Filters zijn optioneel (NULL = geen filter) en altijd parameters, nooit in de SQL-tekst.
# Zoekterm: patiënt- of opnamenummer (begint met), of procedurenaam/-key (bevat).
INGREPEN_SQL = """
SELECT g.ingreep_id, g.date_procedure, g.patient_id, g.arts_email, g.domein, g.lateraliteit, g.campus_naam,
       g.ambulant_gehospitaliseerd, g.detailformulier, g.procedure_key AS hoofd_key,
       h.procedure_name AS hoofd_naam, p.geslacht, p.date_of_birth::date AS geboortedatum,
       count(*) OVER () AS totaal
FROM procedures_production.ingrepen g
LEFT JOIN procedures_production.patient p ON p.patient_id = g.patient_id
LEFT JOIN curated_form_fields.procedures h ON h.procedure_key = g.procedure_key
WHERE g.arts_email = ANY(%(emails)s)
  AND (%(regio)s::text IS NULL OR g.domein = %(regio)s)
  AND (%(patient)s::text IS NULL OR g.patient_id = %(patient)s)
  AND (%(van)s::date IS NULL OR g.date_procedure >= %(van)s)
  AND (%(tot)s::date IS NULL OR g.date_procedure <= %(tot)s)
  AND (%(q)s::text IS NULL
       OR g.patient_id ILIKE %(begint)s OR g.opname_id ILIKE %(begint)s
       OR h.procedure_name ILIKE %(bevat)s OR g.procedure_key ILIKE %(bevat)s
       OR EXISTS (SELECT 1 FROM procedures_production.procedures_ingrepen_autoid i
                  WHERE i.ingreep_id = g.ingreep_id
                    AND (i.procedure_name ILIKE %(bevat)s OR i.procedure_key ILIKE %(bevat)s)))
ORDER BY g.date_procedure DESC, g.ingreep_id DESC
LIMIT %(limit)s OFFSET %(offset)s
"""

PROCEDURES_SQL = """
SELECT ingreep_id, procedure_key, procedure_name, lateraliteit, stralen
FROM procedures_production.procedures_ingrepen_autoid
WHERE ingreep_id = ANY(%(ids)s)
ORDER BY procedure_id
"""


async def _alle(sql: str, params: dict) -> list[dict]:
    async with db.pool.connection(timeout=5) as conn:
        cur = conn.cursor(row_factory=dict_row)
        await cur.execute(sql, params)
        return await cur.fetchall()


async def artsen(ortho_group: str) -> list[dict]:
    return await _alle(ARTSEN_SQL, {"ortho_group": ortho_group})


async def is_assistent(ortho_group: str, email: str, vandaag: date) -> bool:
    return bool(await _alle(ASSISTENT_SQL, {"ortho_group": ortho_group, "email": email.lower(), "vandaag": vandaag}))


def mag_alle_artsen(email: str, assistent: bool) -> bool:
    """Admins (ADMIN_EMAILS) en actieve assistenten zien alle artsen van de groep; een arts enkel zichzelf."""
    return assistent or email.lower() in settings.admin_emails


def like_escape(tekst: str) -> str:
    """% en _ in de zoekterm zijn gewone tekens."""
    return tekst.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def procedures_per_ingreep(rijen: list[dict]) -> dict[int, list[dict]]:
    """Groepeert de procedurerijen per ingreep: één regel per procedure, met de zijden en stralen erbij."""
    per_ingreep: dict[int, dict[str, dict]] = {}
    for r in rijen:
        p = per_ingreep.setdefault(r["ingreep_id"], {}).setdefault(
            r["procedure_key"], {"procedure_key": r["procedure_key"], "naam": r["procedure_name"], "zijden": [], "stralen": []}
        )
        # Opgeslagen als SNOMED-code ('7771000') en 'straal3'; de frontend krijgt "Links" en 3. "Niet van toepassing" blijft weg.
        zijde = LATERALITEIT.get(r["lateraliteit"] or "")
        if zijde and zijde != LATERALITEIT["24847006"] and zijde not in p["zijden"]:
            p["zijden"].append(zijde)
        straal = int(r["stralen"][6:]) if (r["stralen"] or "").startswith("straal") and r["stralen"][6:].isdigit() else None
        if straal and straal not in p["stralen"]:
            p["stralen"].append(straal)
    return {i: list(p.values()) for i, p in per_ingreep.items()}


async def zoek(
    emails: list[str], regio: str | None, van: date | None, tot: date | None, q: str, patient: str, pagina: int
) -> dict:
    q = q.strip()
    params = {
        "emails": emails, "regio": regio, "patient": patient.strip() or None, "van": van, "tot": tot, "q": q or None,
        "begint": like_escape(q) + "%", "bevat": "%" + like_escape(q) + "%",
        "limit": PER_PAGINA, "offset": (pagina - 1) * PER_PAGINA,
    }
    rijen = await _alle(INGREPEN_SQL, params)
    procs = procedures_per_ingreep(await _alle(PROCEDURES_SQL, {"ids": [r["ingreep_id"] for r in rijen]})) if rijen else {}
    return {"totaal": rijen[0]["totaal"] if rijen else 0, "rijen": rijen, "procedures": procs}


def ingreep_json(r: dict, procs: dict[int, list[dict]], arts_namen: dict[str, str]) -> dict:
    # Ingrepen zonder kindrijen (komt voor bij oudere Retool-opslag): val terug op de hoofdprocedure.
    lijst = procs.get(r["ingreep_id"]) or (
        [{"procedure_key": r["hoofd_key"], "naam": r["hoofd_naam"], "zijden": [], "stralen": []}] if r["hoofd_key"] else []
    )
    return {
        "ingreep_id": r["ingreep_id"],
        "datum": r["date_procedure"].isoformat() if r["date_procedure"] else None,
        "patient_id": r["patient_id"],
        "geslacht": r["geslacht"],
        "leeftijd": leeftijd(r["geboortedatum"], r["date_procedure"]) if r["date_procedure"] else None,
        "arts": arts_namen.get((r["arts_email"] or "").lower()),
        "regio": r["domein"],
        "lateraliteit": r["lateraliteit"],
        "campus": r["campus_naam"],
        "verblijf": r["ambulant_gehospitaliseerd"],
        "detailformulier": r["detailformulier"] or None,
        "procedures": lijst,
    }
