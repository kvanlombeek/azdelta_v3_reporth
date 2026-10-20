"""Weekplanning van een arts: de geplande ingrepen uit patient.geplande_procedure.

Vervangt de Retool-queries GetArtsen en QueryPatientenWithIngrepenDezeWeek plus
de JavaScript die daar de week uit filterde. Het filteren gebeurt nu in SQL.
"""

from datetime import date, datetime, timedelta
from itertools import groupby
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

from app import db

TZ = ZoneInfo("Europe/Brussels")

ARTSEN_SQL = """
SELECT naam, email
FROM procedures_production.artsen
WHERE actief
  AND rizivnr <> ''  -- sluit ook NULL uit
  AND ortho_group = %(ortho_group)s
ORDER BY naam
"""

# Een geplande ingreep telt als gerapporteerd (getarificeerd) als er voor die patiënt
# een ingreep bestaat tot 1 dag voor of na de geplande datum.
# De datumfilter vergelijkt de ISO-tekst, zodat de index idx_patient_date_procedure bruikbaar is.
WEEK_SQL = """
SELECT
    p.geslacht,
    p.date_of_birth::date AS geboortedatum,
    (p.geplande_procedure->>'date_procedure')::date AS datum,
    p.geplande_procedure->>'geplande_start_tijd' AS starttijd,
    p.geplande_procedure->>'operatie_zaal' AS zaal,
    p.geplande_procedure->>'beschrijving' AS beschrijving,
    EXISTS (
        SELECT 1
        FROM procedures_production.ingrepen i
        WHERE i.patient_id = p.patient_id
          AND i.date_procedure BETWEEN (p.geplande_procedure->>'date_procedure')::date - 1
                                   AND (p.geplande_procedure->>'date_procedure')::date + 1
    ) AS gerapporteerd
FROM procedures_production.patient p
WHERE p.ortho_group = %(ortho_group)s
  AND lower(p.geplande_procedure->>'arts_email') = %(arts_email)s
  AND p.geplande_procedure->>'date_procedure' >= %(van)s
  AND p.geplande_procedure->>'date_procedure' < %(tot)s
"""


async def artsen(ortho_group: str) -> list[dict]:
    async with db.pool.connection(timeout=5) as conn:
        cur = conn.cursor(row_factory=dict_row)
        await cur.execute(ARTSEN_SQL, {"ortho_group": ortho_group})
        return await cur.fetchall()


async def geplande_ingrepen(ortho_group: str, arts_email: str, maandag: date) -> list[dict]:
    params = {
        "ortho_group": ortho_group,
        "arts_email": arts_email.lower(),
        "van": maandag.isoformat(),
        "tot": (maandag + timedelta(days=7)).isoformat(),
    }
    async with db.pool.connection(timeout=5) as conn:
        cur = conn.cursor(row_factory=dict_row)
        await cur.execute(WEEK_SQL, params)
        return await cur.fetchall()


def vandaag() -> date:
    return datetime.now(TZ).date()


def maandag_van(d: date) -> date:
    return d - timedelta(days=d.weekday())


def tijd(starttijd: str | None) -> tuple[int, int] | None:
    """'7:45', '07:45' of '07:45:00' -> (7, 45). Onleesbaar of leeg -> None."""
    try:
        uur, minuut = (int(deel) for deel in (starttijd or "").split(":")[:2])
    except ValueError:
        return None
    return (uur, minuut) if 0 <= uur < 24 and 0 <= minuut < 60 else None


def _toon_tijd(starttijd: str | None) -> str:
    t = tijd(starttijd)
    return f"{t[0]}:{t[1]:02d}" if t else "–"


def weekoverzicht(rows: list[dict], maandag: date) -> dict:
    """Telt de week en groepeert de openstaande ingrepen per dag en per zaal (op starttijd)."""
    dagen = []
    for i in range(7):
        datum = maandag + timedelta(days=i)
        # Zonder leesbare starttijd achteraan.
        open_ = sorted(
            (r for r in rows if r["datum"] == datum and not r["gerapporteerd"]),
            key=lambda r: (r["zaal"] or "", tijd(r["starttijd"]) or (99, 0)),
        )
        open_ = [{**r, "tijd": _toon_tijd(r["starttijd"])} for r in open_]
        zalen = [(zaal, list(items)) for zaal, items in groupby(open_, key=lambda r: r["zaal"])]
        dagen.append({"datum": datum, "aantal_open": len(open_), "zalen": zalen})
    return {
        "totaal": len(rows),
        "gerapporteerd": sum(1 for r in rows if r["gerapporteerd"]),
        "dagen": dagen,
    }
