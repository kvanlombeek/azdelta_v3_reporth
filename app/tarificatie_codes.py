"""Tarificatie, stap 3: welke RIZIV-codes horen bij de gekozen procedures?

`voorstel()` is een zuivere functie (geen database): ze rekent een *voorstel* uit. De arts kan er
codes aan toevoegen of van afvinken; bij het opslaan wordt de eindlijst opnieuw door de server
gecontroleerd. De frontend toont enkel het voorstel en bewaart de afwijkingen.

Regels:
- De hoofdcode (A = ambulant, H = gehospitaliseerd) wordt één keer per (zijde, straal) aangerekend.
  TODO: uitzonderingen op die regel volgen nog (door Kasper aan te leveren); ze komen in voorstel().
- Extra-, beeldvorming- en gipscodes komen één keer voor per ingreep (zonder zijde of straal),
  ook als meerdere procedures ze delen. Staat een code in de andere variant (A <-> H), dan wordt
  de partnercode genomen; bestaat die niet, dan wordt de code weggelaten.
"""

import re

from psycopg.rows import dict_row

from app import db, procedures

VERBLIJVEN = {"Ambulant": "ambulant", "Gehospitaliseerd": "gehospitaliseerd"}
ZIJDEN = ("Links", "Rechts", "Geen")  # Geen = lateraliteit niet van toepassing

SQL_PROCEDURES = """
    SELECT procedure_key, procedure_name, domein, "nc_main_A", "nc_main_H",
           nc_extra, nc_gips, nc_beeldvorming, infiltratie, courant, revisie, detail_formulier, verschillende_stralen
    FROM curated_form_fields.procedures
    WHERE NOT draft AND procedure_key = ANY(%(keys)s)
"""


def n_getal(n_waarde: str | None) -> int:
    """'N 588', 'N588' en 'K 35' -> 588, 588, 35. Zonder getal: 0. De letter (K of N) telt niet mee."""
    m = re.search(r"\d+", n_waarde or "")
    return int(m.group()) if m else 0


def hoofdcode(p: dict, verblijf: str) -> str | None:
    return p["nc_main_H"] if verblijf == "gehospitaliseerd" else p["nc_main_A"]


def ingreep_procedure_key(gekozen: list[dict], verblijf: str, nomenclatuur: dict) -> str | None:
    """De procedure_key van de ingreep: de procedure met de hoogste (K/N-)waarde van haar hoofdcode.

    Bij een gelijke stand telt de eerst gekozen procedure.
    """
    beste = max(
        gekozen,
        key=lambda p: n_getal(nomenclatuur.get(hoofdcode(p, verblijf) or "", {}).get("n_waarde")),
        default=None,
    )
    return beste["procedure_key"] if beste else None


def naar_verblijf(code: str, verblijf: str, nomenclatuur: dict) -> tuple[str | None, bool]:
    """(code in het gekozen verblijf, vervangen?). Dezelfde code, de partner (A <-> H) of None."""
    info = nomenclatuur.get(code)
    if not info or info["verblijf"] == verblijf:
        return code, False  # onbekende codes blijven zoals ze zijn
    return (info["partner"], True) if info["partner"] else (None, False)


def _rij(code: str, soort: str, nomenclatuur: dict, **extra) -> dict:
    info = nomenclatuur.get(code) or {}
    return {
        "id": code, "code": code, "soort": soort, "label": info.get("label"), "n_waarde": info.get("n_waarde"),
        "procedure_key": None, "procedure": None, "zijde": None, "straal": None, **extra,
    }


def soort_van(code: str, gekozen: list[dict], nomenclatuur: dict) -> tuple[str, str | None]:
    """(soort, procedurenaam) van een opgeslagen code: hoofdcode, extra, beeldvorming of gips van een gekozen procedure.

    Ook de partnercode (A <-> H) telt mee. Onbekend: 'Overig' (bv. een door de arts toegevoegde code).
    """
    for p in gekozen:
        if code in (p["nc_main_A"], p["nc_main_H"]):
            return "Procedure", p["procedure_name"] or p["procedure_key"]
    partner = (nomenclatuur.get(code) or {}).get("partner")
    for soort, veld in (("Extra", "nc_extra"), ("Beeldvorming", "nc_beeldvorming"), ("Gips", "nc_gips")):
        if any(code in p[veld] or partner in p[veld] for p in gekozen):
            return soort, None
    return "Overig", None


def _volgorde(selectie: tuple[str, int | None]) -> tuple[int, int]:
    return ZIJDEN.index(selectie[0]), selectie[1] or 0


def voorstel(gekozen: list[dict], keuzes: dict[str, list[tuple[str, int | None]]], verblijf: str, nomenclatuur: dict) -> dict:
    """Rekent de codelijst uit.

    gekozen: procedures in de volgorde van de keuze (rijen zoals procedures.catalogusregel).
    keuzes: per procedure_key de lijst (zijde, straal); straal is None als de procedure geen stralen kent.
    """
    rijen: list[dict] = []
    aangepast: list[str] = []
    weggelaten: list[str] = []
    gezien: set[str] = set()  # id's; extra codes die twee procedures delen komen één keer voor

    def voeg_toe(rij: dict) -> None:
        if rij["id"] not in gezien:
            gezien.add(rij["id"])
            rijen.append(rij)

    for p in gekozen:
        naam = p["procedure_name"] or p["procedure_key"]
        code = hoofdcode(p, verblijf)
        if code:
            # TODO uitzonderingen: nu volle hoofdcode per (zijde, straal).
            for zijde, straal in sorted(set(keuzes[p["procedure_key"]]), key=_volgorde):
                voeg_toe(_rij(
                    code, "Procedure", nomenclatuur, procedure_key=p["procedure_key"], procedure=naam,
                    zijde=None if zijde == "Geen" else zijde, straal=straal,
                    id=f"hoofd:{p['procedure_key']}:{zijde}:{straal or '-'}",
                ))
        else:
            weggelaten.append(f"{naam}: geen RIZIV-code voor {verblijf}")

        for soort, codes in (("Extra", p["nc_extra"]), ("Beeldvorming", p["nc_beeldvorming"]), ("Gips", p["nc_gips"])):
            for oorspronkelijk in codes:
                nieuw, vervangen = naar_verblijf(oorspronkelijk, verblijf, nomenclatuur)
                if not nieuw:
                    weggelaten.append(f"{oorspronkelijk} ({soort.lower()}): geen variant voor {verblijf}")
                    continue
                if vervangen and nieuw not in gezien:
                    aangepast.append(f"{oorspronkelijk} → {nieuw}")
                voeg_toe(_rij(nieuw, soort, nomenclatuur))

    return {
        "rijen": rijen,
        "aangepast": aangepast,
        "weggelaten": weggelaten,
        "ingreep_procedure_key": ingreep_procedure_key(gekozen, verblijf, nomenclatuur),
    }


class OnbekendeProcedure(Exception):
    pass


async def laad(keys: list[str], streng: bool = True) -> tuple[list[dict], dict]:
    """De gekozen procedures (in de volgorde van `keys`) en de nomenclatuurinfo van al hun codes.

    streng: een onbekende procedure is een fout. Zonder streng worden onbekende (bv. oude) procedures overgeslagen.
    """
    async with db.pool.connection(timeout=5) as conn:
        cur = conn.cursor(row_factory=dict_row)
        await cur.execute(SQL_PROCEDURES, {"keys": keys})
        per_key = {r["procedure_key"]: procedures.catalogusregel(r) for r in await cur.fetchall()}
        if streng and any(k not in per_key for k in keys):
            raise OnbekendeProcedure
        gekozen = [per_key[k] for k in keys if k in per_key]
        alle = sorted({
            c for p in gekozen for c in (p["nc_main_A"], p["nc_main_H"], *p["nc_extra"], *p["nc_gips"], *p["nc_beeldvorming"]) if c
        })
        await cur.execute(procedures.SQL_GIPS)
        nomenclatuur = await procedures.nomenclatuur_info(cur, alle, await cur.fetchall())
    return gekozen, nomenclatuur
