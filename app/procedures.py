"""Procedures zoeken voor de tarificatie: semantisch (Gemini-embedding) + trigram + RIZIV-code.

Overgenomen uit azdelta_procedure_finder. Alles komt uit curated_form_fields.procedure_embeddings.
Enkel de zoektekst gaat naar Gemini (procedurewoorden, nooit patiëntgegevens); de zoektekst wordt niet gelogd.
"""

import math
import re

from psycopg.rows import dict_row

from app import db
from app.config import settings

EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
RRF_K = 60
CANDIDATES = 50
CODE_RE = re.compile(r"^[0-9.\-]{4,}$")
# Populariteit telt licht mee: score x (1 + gewicht x populariteit/5), dus max. +15%.
POPULARITY_WEIGHT = 0.15
# Populariteit 0-5 op een log-schaal (~factor 3 per stap): 1-2, 3-9, 10-29, 30-99, >=100.
POPULARITY_STEPS = [1, 3, 10, 30, 100]

# Alleen de naam staat als regel "Procedure: ..." in search_text; een naam kan meerdere regels beslaan.
SEARCH_TEXT_FIELD = re.compile(r"^(Procedure|Type ingreep|Domein|Omschrijving|Details): ", re.M)

# Het domein-filter is optioneel (NULL = alle regio's); altijd als parameter, nooit in de SQL-tekst.
DOMEIN_FILTER = "(%(domein)s::text IS NULL OR domein = %(domein)s)"

SQL_CODE = f"""
    SELECT procedure_key,
           "nc_main_A" LIKE ANY(%(prefixes)s) AS match_a,
           "nc_main_H" LIKE ANY(%(prefixes)s) AS match_h,
           ("nc_main_A" = ANY(%(parts)s) OR "nc_main_H" = ANY(%(parts)s)) AS exact
    FROM curated_form_fields.procedure_embeddings
    WHERE ("nc_main_A" LIKE ANY(%(prefixes)s) OR "nc_main_H" LIKE ANY(%(prefixes)s)) AND {DOMEIN_FILTER}
    LIMIT 200
"""
SQL_VECTOR = f"""
    SELECT procedure_key FROM curated_form_fields.procedure_embeddings
    WHERE {DOMEIN_FILTER}
    ORDER BY embedding <=> %(v)s::vector
    LIMIT %(n)s
"""
# word_similarity i.p.v. similarity: search_text is lang, similarity() blijft dan rond 0.08.
SQL_TRGM = f"""
    SELECT procedure_key FROM curated_form_fields.procedure_embeddings
    WHERE word_similarity(%(q)s, search_text) > 0.3 AND {DOMEIN_FILTER}
    ORDER BY word_similarity(%(q)s, search_text) DESC, procedure_key
    LIMIT %(n)s
"""
SQL_POPULAIR = f"""
    SELECT procedure_key FROM curated_form_fields.procedure_embeddings
    WHERE {DOMEIN_FILTER}
    ORDER BY frequentie DESC NULLS LAST, procedure_key
    LIMIT %(n)s
"""
# label_short_nl: de korte omschrijving die het RIZIV aan de nomenclatuurcode geeft (A = ambulant, H = gehospitaliseerd).
SQL_DETAILS = """
    SELECT e.procedure_key, e.search_text, e.domein, e."nc_main_A", e."nc_main_H", e.frequentie,
           a.label_short_nl AS label_a, h.label_short_nl AS label_h, pr.verschillende_stralen
    FROM curated_form_fields.procedure_embeddings e
    LEFT JOIN curated_form_fields.procedures pr ON pr.procedure_key = e.procedure_key
    LEFT JOIN curated_form_fields.nomenclatuur a ON a.nc_main = e."nc_main_A"
    LEFT JOIN curated_form_fields.nomenclatuur h ON h.nc_main = e."nc_main_H"
    WHERE e.procedure_key = ANY(%(keys)s)
"""

# Catalogus: alle (niet-draft) procedures met hun RIZIV-codes, één keer op te halen door de frontend.
# Zonder lange tekstvelden (Contentfull_brief e.d.), zodat het klein blijft.
SQL_CATALOGUS = """
    SELECT procedure_key, procedure_name, domein, "nc_main_A", "nc_main_H",
           nc_extra, nc_gips, nc_beeldvorming, infiltratie, courant, revisie, detail_formulier, verschillende_stralen
    FROM curated_form_fields.procedures
    WHERE NOT draft
    ORDER BY procedure_key
"""
# Per code: omschrijving, N-waarde, verblijf en de "partner" (zelfde dienst, andere variant: A <-> H).
SQL_NOMENCLATUUR = """
    SELECT n.nc_main, n.label_short_nl, n.n_waarde, lower(n.ambulant_gehospitaliseerd) AS verblijf, p.nc_main AS partner
    FROM curated_form_fields.nomenclatuur n
    LEFT JOIN curated_form_fields.nomenclatuur p
           ON p.label_short_nl = n.label_short_nl AND p.n_waarde = n.n_waarde
          AND lower(p.ambulant_gehospitaliseerd) <> lower(n.ambulant_gehospitaliseerd)
    WHERE n.nc_main = ANY(%(codes)s)
"""
SQL_NOMENCLATUUR_ZONDER_PARTNER = """
    SELECT nc_main, label_short_nl, n_waarde, lower(ambulant_gehospitaliseerd) AS verblijf
    FROM curated_form_fields.nomenclatuur
    WHERE nc_main = ANY(%(codes)s)
"""
SQL_RADIOSCOPIE = """
    SELECT nc_main, label_short_nl AS label, n_waarde, lower(ambulant_gehospitaliseerd) AS verblijf
    FROM curated_form_fields.nomenclatuur
    WHERE categoriepaul = 'Radioscopie'
    ORDER BY label_short_nl, nc_main
"""
# domein: komma-gescheiden lijst van regio's; zeldzaam = 'x' voor weinig gebruikte gipsen.
SQL_GIPS = """
    SELECT nc_main, n_waarde, lower(ambulant_gehospitaliseerd) AS verblijf, beschrijving, zeldzaam, domein
    FROM curated_form_fields.gips_nomenclatuur
    ORDER BY beschrijving, nc_main
"""
CODE = re.compile(r"^\d+$")

_embeddings: dict[str, str] = {}  # eenvoudige cache (max. 512 zoekvragen)
_gemini = None


# Aantal resultaten in de lijst; de gematchte procedures uit de planning nemen de eerste plaatsen.
RESULTATEN = 10

SORTEREN = ("fit", "populariteit")
# Bij sorteren op populariteit wordt gekozen uit de beste POOL treffers, zodat onbelangrijke treffers niet bovenaan komen.
POOL = 25


def orden(gerangschikt: list[tuple[str, list[str]]], details: dict[str, dict], sorteer: str, k: int) -> list[tuple[str, list[str]]]:
    """'fit': de volgorde van de zoekopdracht. 'populariteit': de beste POOL treffers, meest uitgevoerd eerst."""
    if sorteer != "populariteit":
        return gerangschikt[:k]
    pool = sorted(gerangschikt[:POOL], key=lambda t: -(details[t[0]]["frequentie"] or 0))  # stabiel: gelijk = op fit
    return pool[:k]


def codes(tekst: str | None) -> list[str]:
    """'288945|288960' -> ['288945', '288960']. Alles wat geen cijfercode is (bv. 'true') wordt genegeerd."""
    return [c for c in (deel.strip() for deel in (tekst or "").split("|")) if CODE.match(c)]


def popularity(freq: float | None) -> int:
    return sum(1 for t in POPULARITY_STEPS if (freq or 0) >= t)


def boost(score: float, freq: float | None) -> float:
    return score * (1 + POPULARITY_WEIGHT * popularity(freq) / len(POPULARITY_STEPS))


def code_parts(q: str) -> list[str]:
    """'285250-285261' -> ['285250', '285261']; punten worden genegeerd."""
    return [p for p in (re.sub(r"\D", "", deel) for deel in q.split("-")) if p]


def procedure_naam(search_text: str | None) -> str | None:
    stukken = SEARCH_TEXT_FIELD.split(search_text or "")
    velden = {label: waarde.strip() for label, waarde in zip(stukken[1::2], stukken[2::2])}
    naam = velden.get("Procedure")
    return re.sub(r"\s*\n\s*", " ", naam) if naam else None


async def embed_query(q: str) -> str:
    """Embed de zoekvraag, L2-normaliseer, en geef terug als pgvector-literal."""
    global _gemini
    if q in _embeddings:
        return _embeddings[q]
    if _gemini is None:
        from google import genai  # pas laden als nodig: zonder sleutel wordt het nooit gebruikt

        _gemini = genai.Client(api_key=settings.gemini_api_key)
    from google.genai import types

    res = await _gemini.aio.models.embed_content(
        model=EMBED_MODEL,
        contents=q,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY", output_dimensionality=EMBED_DIM),
    )
    v = res.embeddings[0].values
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    literal = "[" + ",".join(f"{x / norm:.7f}" for x in v) + "]"
    if len(_embeddings) >= 512:
        _embeddings.pop(next(iter(_embeddings)))
    _embeddings[q] = literal
    return literal


def fuseer(lijsten: list[list[str]]) -> dict[str, float]:
    """Reciprocal rank fusion over meerdere rangordes."""
    scores: dict[str, float] = {}
    for sleutels in lijsten:
        for rang, sleutel in enumerate(sleutels, start=1):
            scores[sleutel] = scores.get(sleutel, 0.0) + 1 / (RRF_K + rang)
    return scores


def resultaat(sleutel: str, d: dict, code_match: list[str]) -> dict:
    freq = d["frequentie"]
    return {
        "procedure_key": sleutel,
        "procedure_name": procedure_naam(d["search_text"]),
        "domein": d["domein"],
        "nc_main_A": d["nc_main_A"],
        "nc_main_H": d["nc_main_H"],
        "label_A": d["label_a"],
        "label_H": d["label_h"],
        "verschillende_stralen": bool(d["verschillende_stralen"]),
        "code_match": code_match,
        "frequentie": int(freq) if freq else None,
    }


async def _sleutels(cur, sql: str, params: dict) -> list[str]:
    await cur.execute(sql, params)
    return [r["procedure_key"] for r in await cur.fetchall()]


async def _details(cur, sleutels: list[str]) -> dict[str, dict]:
    await cur.execute(SQL_DETAILS, {"keys": sleutels})
    return {r["procedure_key"]: r for r in await cur.fetchall()}


SQL_AANTAL_ARTS = """
    SELECT i.procedure_key, count(DISTINCT i.ingreep_id) AS aantal
    FROM procedures_production.procedures_ingrepen_autoid i
    JOIN procedures_production.ingrepen g ON g.ingreep_id = i.ingreep_id
    WHERE lower(g.arts_email) = %(arts)s AND i.procedure_key = ANY(%(keys)s)
    GROUP BY i.procedure_key
"""


def orden_gematcht(sleutels: list[str], aantal_arts: dict[str, int], details: dict[str, dict], k: int) -> list[str]:
    """Meest gekozen door deze arts eerst, dan de globale frequentie, dan de volgorde uit de planning. Hoogstens k."""
    bestaand = [s for s in sleutels if s in details]
    rang = sorted(bestaand, key=lambda s: (-aantal_arts.get(s, 0), -(details[s]["frequentie"] or 0), bestaand.index(s)))
    return rang[:k]


async def bij_sleutels(sleutels: list[str]) -> dict[str, dict]:
    """{procedure_key: procedure in de vorm van zoek()} voor de sleutels die (nog) bestaan."""
    if not sleutels:
        return {}
    async with db.pool.connection(timeout=5) as conn:
        cur = conn.cursor(row_factory=dict_row)
        details = await _details(cur, sleutels)
    return {s: resultaat(s, d, []) for s, d in details.items()}


async def gematchte_procedures(sleutels: list[str], arts_email: str, k: int) -> list[dict]:
    """De in de planning vooraf gematchte procedures, in dezelfde vorm als zoek(), geordend voor deze arts.
    Onbekende of draft-procedures worden overgeslagen."""
    if not sleutels:
        return []
    async with db.pool.connection(timeout=5) as conn:
        cur = conn.cursor(row_factory=dict_row)
        details = await _details(cur, sleutels)
        await cur.execute(SQL_AANTAL_ARTS, {"arts": arts_email.lower(), "keys": sleutels})
        aantal = {r["procedure_key"]: r["aantal"] for r in await cur.fetchall()}
    return [resultaat(s, details[s], []) for s in orden_gematcht(sleutels, aantal, details, k)]


async def zoek(q: str, domein: str | None, k: int, sorteer: str = "fit") -> dict:
    """Zoekt procedures. Lege zoekvraag: de populairste (van het domein)."""
    q = q.strip()
    waarschuwingen: list[str] = []
    params = {"domein": domein, "n": CANDIDATES}
    async with db.pool.connection(timeout=5) as conn:
        cur = conn.cursor(row_factory=dict_row)

        if not q:
            sleutels = (await _sleutels(cur, SQL_POPULAIR, {**params, "n": k}))
            details = await _details(cur, sleutels)
            gerangschikt = [(s, []) for s in sleutels]
        elif CODE_RE.match(q):
            # Een cijfercode zoekt enkel op nc_main_A / nc_main_H: exacte treffers eerst.
            delen = code_parts(q)
            await cur.execute(SQL_CODE, {**params, "parts": delen, "prefixes": [p + "%" for p in delen]})
            treffers = await cur.fetchall()
            details = await _details(cur, [t["procedure_key"] for t in treffers])
            basis = 2 / (RRF_K + 1)
            rij = sorted(
                (
                    (not t["exact"], -boost(basis if t["exact"] else basis * 0.9, details[t["procedure_key"]]["frequentie"]), t["procedure_key"],
                     [c for c, m in (("A", t["match_a"]), ("H", t["match_h"])) if m])
                    for t in treffers
                )
            )
            gerangschikt = [(sleutel, match) for _, _, sleutel, match in rij]
        else:
            vector: list[str] = []
            if settings.gemini_api_key:
                try:
                    vector = await _sleutels(cur, SQL_VECTOR, {**params, "v": await embed_query(q)})
                except Exception as exc:  # zonder Gemini blijft trigram-zoeken werken
                    waarschuwingen.append("Zoeken op betekenis is even niet beschikbaar.")
                    from app.auth import log

                    log.warning("embedding mislukt fout=%s", type(exc).__name__)
            trigram = await _sleutels(cur, SQL_TRGM, {**params, "q": q})
            scores = fuseer([vector, trigram])
            details = await _details(cur, list(scores))
            scores = {s: boost(sc, details[s]["frequentie"]) for s, sc in scores.items()}
            gerangschikt = [(s, []) for s in sorted(scores, key=lambda s: -scores[s])]

    return {
        "totaal": len(gerangschikt),
        "resultaten": [resultaat(s, details[s], match) for s, match in orden(gerangschikt, details, sorteer, k)],
        "waarschuwingen": waarschuwingen,
    }


def partners(rijen: list[dict]) -> dict[str, dict]:
    """Bouwt {code: {label, n_waarde, verblijf, partner}}. Een partner telt enkel als er precies één is."""
    codes: dict[str, dict] = {}
    for r in rijen:
        info = codes.setdefault(
            r["nc_main"], {"label": r["label_short_nl"], "n_waarde": r["n_waarde"], "verblijf": r["verblijf"], "partners": set()}
        )
        if r.get("partner"):
            info["partners"].add(r["partner"])
    return {
        code: {"label": i["label"], "n_waarde": i["n_waarde"], "verblijf": i["verblijf"], "partner": next(iter(i["partners"])) if len(i["partners"]) == 1 else None}
        for code, i in codes.items()
    }


def catalogusregel(r: dict) -> dict:
    """Eén rij uit curated_form_fields.procedures in de vorm van de catalogus."""
    return {
        "procedure_key": r["procedure_key"],
        "procedure_name": r["procedure_name"],
        "domein": r["domein"],
        "nc_main_A": r["nc_main_A"] or None,
        "nc_main_H": r["nc_main_H"] or None,
        "nc_extra": codes(r["nc_extra"]),
        "nc_gips": codes(r["nc_gips"]),
        "nc_beeldvorming": codes(r["nc_beeldvorming"]),
        "infiltratie": bool(r["infiltratie"]),
        "courant": bool(r["courant"]),
        "revisie": bool(r["revisie"]),
        "detail_formulier": r["detail_formulier"] or None,
        "verschillende_stralen": bool(r["verschillende_stralen"]),
    }


async def nomenclatuur_info(cur, alle: list[str], gips: list[dict]) -> dict[str, dict]:
    """Per code: omschrijving, N-waarde, verblijf en partner (A <-> H). `gips`: rijen van SQL_GIPS."""
    await cur.execute(SQL_NOMENCLATUUR, {"codes": alle})
    nomenclatuur = partners(await cur.fetchall())
    # Partners die zelf niet in de lijst zaten (bv. de andere variant van een code) ook meegeven.
    ontbrekend = sorted({i["partner"] for i in nomenclatuur.values() if i["partner"] and i["partner"] not in nomenclatuur})
    if ontbrekend:
        await cur.execute(SQL_NOMENCLATUUR_ZONDER_PARTNER, {"codes": ontbrekend})
        for r in await cur.fetchall():
            herkomst = next((c for c, i in nomenclatuur.items() if i["partner"] == r["nc_main"]), None)
            nomenclatuur[r["nc_main"]] = {"label": r["label_short_nl"], "n_waarde": r["n_waarde"], "verblijf": r["verblijf"], "partner": herkomst}
    # Gipscodes die niet in de nomenclatuur staan: omschrijving en partner uit de gipslijst zelf.
    per_beschrijving: dict[str, list[dict]] = {}
    for g in gips:
        per_beschrijving.setdefault(g["beschrijving"], []).append(g)
    for g in gips:
        if g["nc_main"] not in nomenclatuur:
            tegenpolen = [x["nc_main"] for x in per_beschrijving[g["beschrijving"]] if x["verblijf"] != g["verblijf"]]
            nomenclatuur[g["nc_main"]] = {
                "label": g["beschrijving"], "n_waarde": g["n_waarde"], "verblijf": g["verblijf"],
                "partner": tegenpolen[0] if len(tegenpolen) == 1 else None,
            }
    return nomenclatuur


async def catalogus() -> dict:
    """Alle procedures met hun codes (hoofd A/H, extra, gips, beeldvorming), de keuzelijsten voor radioscopie en gips,
    en per code de omschrijving, N-waarde, het verblijf en de partnercode (A <-> H)."""
    async with db.pool.connection(timeout=5) as conn:
        cur = conn.cursor(row_factory=dict_row)
        await cur.execute(SQL_CATALOGUS)
        rijen = await cur.fetchall()
        await cur.execute(SQL_RADIOSCOPIE)
        radioscopie = await cur.fetchall()
        await cur.execute(SQL_GIPS)
        gips = [
            {
                "nc_main": r["nc_main"], "n_waarde": r["n_waarde"], "verblijf": r["verblijf"], "beschrijving": r["beschrijving"],
                "zeldzaam": (r["zeldzaam"] or "").strip() != "",
                "domeinen": [d.strip() for d in (r["domein"] or "").split(",") if d.strip()],
            }
            for r in await cur.fetchall()
        ]
        lijst = [catalogusregel(r) for r in rijen]
        alle = sorted(
            {c for p in lijst for c in (p["nc_main_A"], p["nc_main_H"], *p["nc_extra"], *p["nc_gips"], *p["nc_beeldvorming"]) if c}
            | {r["nc_main"] for r in radioscopie} | {g["nc_main"] for g in gips}
        )
        nomenclatuur = await nomenclatuur_info(cur, alle, gips)
    return {
        "procedures": lijst,
        "nomenclatuur": nomenclatuur,
        "radioscopie": [
            {"nc_main": r["nc_main"], "label": r["label"], "n_waarde": r["n_waarde"], "verblijf": r["verblijf"]} for r in radioscopie
        ],
        "gips": gips,
    }
