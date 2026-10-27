"""JSON-API van Reporth v3 (alles onder /api; de login-middleware geeft hier 401 zonder sessie)."""

import re
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import ingrepen, planning, procedures, tarificatie, tarificatie_codes
from app.auth import log
from app.config import ORTHO_GROUP

router = APIRouter(prefix="/api")

HASH_RE = re.compile(r"^[0-9a-f]{12}$")


@router.get("/planning")
async def weekplanning(request: Request, week: str = "", arts: str = ""):
    """Weekoverzicht van een arts uit de eigen groep (standaard de aangemelde gebruiker)."""
    user = request.session["user"]  # de login-middleware garandeert een gebruiker
    vandaag = planning.vandaag()
    try:
        maandag = planning.maandag_van(date.fromisoformat(week))
    except ValueError:
        maandag = planning.maandag_van(vandaag)
    try:
        artsen = await planning.artsen(ORTHO_GROUP)
        # Enkel artsen uit de eigen groep; onbekende waarden vallen terug op de aangemelde gebruiker.
        emails = {a["email"].lower() for a in artsen if a["email"]}
        arts_email = next((e for e in (arts.lower(), user["email"]) if e in emails), None)
        overzicht = None
        if arts_email:
            rows = await planning.geplande_ingrepen(ORTHO_GROUP, arts_email, maandag)
            overzicht = planning.weekoverzicht(rows, maandag)
    except Exception as exc:
        log.warning("planning niet geladen fout=%s", type(exc).__name__)
        return JSONResponse({"detail": "De database is even niet bereikbaar."}, status_code=503)

    return {
        "vandaag": vandaag.isoformat(),
        "maandag": maandag.isoformat(),
        "weeknummer": maandag.isocalendar().week,
        "artsen": [{"email": a["email"].lower(), "naam": a["naam"]} for a in artsen if a["email"]],
        "arts_email": arts_email,
        "dag_index": planning.standaard_dag(vandaag, maandag, overzicht),
        "overzicht": overzicht,
    }


@router.get("/tarificatie/nieuw/{patient_id}/{planning_hash}")
async def nieuwe_tarificatie(patient_id: str, planning_hash: str, request: Request):
    """Voorinvulling en keuzelijsten voor stap 1, vanuit een geplande ingreep.

    404: onbekend, te oud, andere groep of arts buiten de groep. 409: planning ondertussen gewijzigd.
    """
    if not HASH_RE.match(planning_hash):
        raise HTTPException(404)
    try:
        plan = await tarificatie.geplande_ingreep(ORTHO_GROUP, patient_id, tarificatie.vroegste_datum(planning.vandaag()))
        if plan is None:
            raise HTTPException(404)
        artsen = await planning.artsen(ORTHO_GROUP)
        if (plan["arts_email"] or "").lower() not in {a["email"].lower() for a in artsen if a["email"]}:
            raise HTTPException(404)
        if plan["planning_hash"] != planning_hash:
            raise HTTPException(409, "De planning is ondertussen gewijzigd. Ga terug naar de planning.")
        try:
            datum = date.fromisoformat(plan["datum"])
        except (TypeError, ValueError):
            raise HTTPException(404)
        campussen = await tarificatie.campussen()
        assistenten = await tarificatie.assistenten(ORTHO_GROUP, datum)
        gematcht = await procedures.gematchte_procedures(
            tarificatie.gematchte_sleutels(plan["procedure_keys"]), plan["arts_email"] or "", procedures.RESULTATEN
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("tarificatie niet geladen fout=%s", type(exc).__name__)
        return JSONResponse({"detail": "De database is even niet bereikbaar."}, status_code=503)

    return {
        "patient_id": plan["patient_id"],
        # Enkel ter herkenning, niet te wijzigen: geen geboortedatum, enkel de leeftijd op de dag van de ingreep.
        "patient": {"geslacht": plan["geslacht"], "leeftijd": tarificatie.leeftijd(plan["geboortedatum"], datum)},
        "planning_hash": plan["planning_hash"],
        "gematchte_procedures": gematcht,  # uit de planning; de zoekfunctie zelf blijft enkel op tekst werken
        "voorinvulling": tarificatie.voorinvulling(plan, {c["campus_code"] for c in campussen}),
        "opties": {
            "campussen": campussen,
            "artsen": [{"email": a["email"].lower(), "naam": a["naam"]} for a in artsen if a["email"]],
            "assistenten": assistenten,
            "regios": tarificatie.LICHAAMSREGIOS,
            "ambulant_gehospitaliseerd": tarificatie.AMBULANT_GEHOSPITALISEERD,
            "lateraliteiten": [{"code": c, "naam": n} for c, n in tarificatie.LATERALITEIT.items()],
        },
    }


@router.get("/procedures/catalogus")
async def catalogus_procedures():
    """Alle procedures met RIZIV-codes, door de frontend bij het openen van de app opgehaald en bijgehouden."""
    try:
        data = await procedures.catalogus()
    except Exception as exc:
        log.warning("catalogus niet geladen fout=%s", type(exc).__name__)
        return JSONResponse({"detail": "De database is even niet bereikbaar."}, status_code=503)
    # De lijst wijzigt zelden: een uur in de browser bijhouden volstaat.
    return JSONResponse(data, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/procedures")
async def zoek_procedures(q: str = Query("", max_length=200), domein: str = "", k: int = Query(procedures.RESULTATEN, ge=1, le=50), sorteer: str = "fit"):
    """Procedures zoeken (tekst of RIZIV-code). Zonder zoekvraag: de populairste, eventueel per lichaamsregio."""
    if domein and domein not in tarificatie.LICHAAMSREGIOS:
        raise HTTPException(422, "Onbekende lichaamsregio.")
    if sorteer not in procedures.SORTEREN:
        raise HTTPException(422, "Onbekende sortering.")
    try:
        return await procedures.zoek(q, domein or None, k, sorteer)
    except Exception as exc:
        log.warning("procedures niet geladen fout=%s", type(exc).__name__)
        return JSONResponse({"detail": "De database is even niet bereikbaar."}, status_code=503)


class Selectie(BaseModel):
    zijde: Literal["Links", "Rechts", "Geen"]
    straal: int | None = Field(None, ge=1, le=5)


class ProcedureKeuze(BaseModel):
    procedure_key: str = Field(max_length=100)
    selecties: list[Selectie] = Field(min_length=1, max_length=10)


class BerekenVerzoek(BaseModel):
    ambulant_gehospitaliseerd: Literal["Ambulant", "Gehospitaliseerd"]
    procedures: list[ProcedureKeuze] = Field(min_length=1, max_length=20)


@router.post("/tarificatie/berekenen")
async def bereken_tarificatie(verzoek: BerekenVerzoek):
    """Voorstel voor de RIZIV-codes bij de gekozen procedures, zijden en stralen. Bewaart niets."""
    keys = [p.procedure_key for p in verzoek.procedures]
    if len(set(keys)) != len(keys):
        raise HTTPException(422, "Een procedure komt meer dan één keer voor.")
    try:
        gekozen, nomenclatuur = await tarificatie_codes.laad(keys)
    except tarificatie_codes.OnbekendeProcedure:
        raise HTTPException(422, "Onbekende procedure.")
    except Exception as exc:
        log.warning("tarificatie niet berekend fout=%s", type(exc).__name__)
        return JSONResponse({"detail": "De database is even niet bereikbaar."}, status_code=503)

    keuzes = {}
    for p, k in zip(gekozen, verzoek.procedures):
        # Stralen horen enkel bij procedures met verschillende stralen, en dan altijd.
        if any((s.straal is not None) != p["verschillende_stralen"] for s in k.selecties):
            raise HTTPException(422, "Ongeldige straalkeuze voor deze procedure.")
        keuzes[p["procedure_key"]] = [(s.zijde, s.straal) for s in k.selecties]
    return tarificatie_codes.voorstel(
        gekozen, keuzes, tarificatie_codes.VERBLIJVEN[verzoek.ambulant_gehospitaliseerd], nomenclatuur
    )


async def _toegang(request: Request) -> tuple[bool, dict[str, str], list[str]]:
    """Wie mag welke ingrepen zien? (alle artsen?, {e-mail: naam} van de groep, toegelaten e-mails).

    Een arts ziet enkel de eigen ingrepen. Admins (ADMIN_EMAILS) en actieve assistenten zien alle artsen van de groep.
    Wie geen van beide is, krijgt 403.
    """
    email = request.session["user"]["email"].lower()
    namen = {a["email"].lower(): a["naam"] for a in await ingrepen.artsen(ORTHO_GROUP)}
    alle = ingrepen.mag_alle_artsen(email, await ingrepen.is_assistent(ORTHO_GROUP, email, planning.vandaag()))
    if alle:
        return True, namen, list(namen)
    if email in namen:
        return False, namen, [email]
    raise HTTPException(403, "Geen toegang tot de historiek.")


@router.get("/ingrepen")
async def historiek(
    request: Request, arts: str = "", regio: str = "", q: str = Query("", max_length=100), patient: str = Query("", max_length=40),
    van: str = "", tot: str = "", pagina: int = Query(1, ge=1, le=10000),
):
    """Reeds geregistreerde ingrepen, nieuwste eerst, met filters.

    `arts` (leeg = alle) kan enkel bij admins en assistenten; een gewone arts ziet altijd enkel de eigen ingrepen.
    """
    if regio and regio not in tarificatie.LICHAAMSREGIOS:
        raise HTTPException(422, "Onbekende lichaamsregio.")
    try:
        datums = [date.fromisoformat(d) if d else None for d in (van, tot)]
    except ValueError:
        raise HTTPException(422, "Ongeldige datum.")
    try:
        alle, namen, emails = await _toegang(request)
        if alle and arts:
            if arts.lower() not in namen:
                raise HTTPException(422, "Onbekende arts.")
            emails = [arts.lower()]
        resultaat = await ingrepen.zoek(emails, regio or None, datums[0], datums[1], q, patient, pagina)
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("ingrepen niet geladen fout=%s", type(exc).__name__)
        return JSONResponse({"detail": "De database is even niet bereikbaar."}, status_code=503)

    return {
        "totaal": resultaat["totaal"],
        "pagina": pagina,
        "per_pagina": ingrepen.PER_PAGINA,
        "mag_alle_artsen": alle,
        # De keuzelijst toont altijd wie bekeken wordt; een gewone arts heeft enkel zichzelf (niet te wijzigen).
        "artsen": [{"email": e, "naam": namen[e]} for e in (namen if alle else emails)],
        "regios": tarificatie.LICHAAMSREGIOS,
        "ingrepen": [ingrepen.ingreep_json(r, resultaat["procedures"], namen) for r in resultaat["rijen"]],
    }


@router.get("/tarificatie/ingreep/{ingreep_id}")
async def bestaande_tarificatie(ingreep_id: int, request: Request):
    """Een reeds opgeslagen ingreep in dezelfde vorm als de nieuwe tarificatie, plus wat er opgeslagen staat.

    De opgeslagen codes worden getoond zoals ze zijn en niet opnieuw berekend. 404: onbekend of niet toegelaten
    (ook voor ingrepen van andere artsen, zodat het bestaan niet verraden wordt).
    """
    if not 0 < ingreep_id < 2**31:
        raise HTTPException(404)
    try:
        alle, namen, emails = await _toegang(request)
        ingreep = await tarificatie.bestaande_ingreep(ingreep_id)
        if ingreep is None or (ingreep["arts_email"] or "").lower() not in emails:
            raise HTTPException(404)
        procedure_rijen, tarief = await tarificatie.opgeslagen_rijen(ingreep_id)
        sleutels = list(dict.fromkeys(r["procedure_key"] for r in procedure_rijen))
        gevonden = await procedures.bij_sleutels(sleutels)
        gekozen, nomenclatuur = await tarificatie_codes.laad(sleutels, streng=False)
        campussen = await tarificatie.campussen()
        assistenten = await tarificatie.assistenten(ORTHO_GROUP, ingreep["date_procedure"])
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("bestaande tarificatie niet geladen fout=%s", type(exc).__name__)
        return JSONResponse({"detail": "De database is even niet bereikbaar."}, status_code=503)

    voorinvulling = tarificatie.voorinvulling(
        {
            "datum": ingreep["date_procedure"].isoformat(), "campus_code": ingreep["campus_code"], "opname_id": ingreep["opname_id"],
            "ambulant_gehospitaliseerd": ingreep["ambulant_gehospitaliseerd"], "arts_email": ingreep["arts_email"],
            "domein": ingreep["domein"], "lateraliteit": ingreep["cd_ltrlty"], "beschrijving": None,
        },
        {c["campus_code"] for c in campussen},
    )
    return {
        "patient_id": ingreep["patient_id"],
        "patient": {"geslacht": ingreep["geslacht"], "leeftijd": tarificatie.leeftijd(ingreep["geboortedatum"], ingreep["date_procedure"])},
        "gematchte_procedures": [],
        "voorinvulling": {**voorinvulling, "assistent": ingreep["assistent_interne_nummer"] or None},
        "opties": {
            "campussen": campussen,
            "artsen": [{"email": e, "naam": n} for e, n in namen.items()],
            "assistenten": assistenten,
            "regios": tarificatie.LICHAAMSREGIOS,
            "ambulant_gehospitaliseerd": tarificatie.AMBULANT_GEHOSPITALISEERD,
            "lateraliteiten": [{"code": c, "naam": n} for c, n in tarificatie.LATERALITEIT.items()],
        },
        "opgeslagen": {
            "ingreep_id": ingreep_id,
            "procedure_key": ingreep["procedure_key"],
            "procedures": tarificatie.opgeslagen_procedures(procedure_rijen, gevonden),
            "rijen": tarificatie.opgeslagen_codes(tarief, gekozen, nomenclatuur),
        },
    }
