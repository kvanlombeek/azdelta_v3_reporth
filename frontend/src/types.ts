// Vorm van het API-antwoord (zie app/api.py). Alle bronnen (planning, bestaande ingreep, blanco)
// geven dezelfde vorm terug; het formulier weet niet waar de beginwaarden vandaan komen.
export type Voorinvulling = {
  datum: string | null;
  campus_code: string | null;
  opname_id: string | null;
  ambulant_gehospitaliseerd: string | null;
  arts_email: string | null;
  regio: string | null;
  lateraliteit: string | null; // SNOMED-code
  beschrijving: string | null; // omschrijving uit de planning, startpunt voor het zoeken
  assistent?: string | null; // internnummer van de assistent (enkel bij een opgeslagen ingreep)
};

export type Opties = {
  campussen: { campus_code: string; campus_naam: string }[];
  artsen: { email: string; naam: string }[];
  assistenten: { internnummer: string; naam: string }[];
  regios: string[];
  ambulant_gehospitaliseerd: string[];
  lateraliteiten: { code: string; naam: string }[];
};

export type TarificatieAntwoord = {
  patient_id: string;
  patient: { geslacht: string | null; leeftijd: number | null };
  gematchte_procedures: Procedure[]; // in de planning vooraf gematcht; staan bovenaan de procedurelijst
  planning_hash?: string; // enkel bij een nieuwe ingreep vanuit de planning
  voorinvulling: Voorinvulling;
  opties: Opties;
  opgeslagen?: Opgeslagen; // enkel bij een bestaande ingreep
};

// Wat voor een bestaande ingreep in de database staat (zie GET /api/tarificatie/ingreep/{id}); niet opnieuw berekend.
export type Opgeslagen = {
  ingreep_id: number;
  procedure_key: string | null;
  procedures: { procedure: Procedure; selecties: Selectie[] }[];
  rijen: Rij[];
};

export type PlanningIngreep = {
  tijd: string;
  beschrijving: string | null;
  geslacht: string | null;
  geboortedatum: string | null;
  patient_id: string;
  planning_hash: string;
};
export type PlanningDag = {
  datum: string;
  aantal_open: number;
  zalen: { zaal: string | null; ingrepen: PlanningIngreep[] }[];
};
export type PlanningAntwoord = {
  vandaag: string;
  maandag: string;
  weeknummer: number;
  artsen: { email: string; naam: string }[];
  arts_email: string | null;
  dag_index: number;
  overzicht: { totaal: number; gerapporteerd: number; dagen: PlanningDag[] } | null;
};

export type Procedure = {
  procedure_key: string;
  procedure_name: string | null;
  domein: string | null;
  nc_main_A: string | null;
  nc_main_H: string | null;
  label_A: string | null; // korte RIZIV-omschrijving (label_short_nl) bij de ambulante code
  label_H: string | null;
  verschillende_stralen: boolean; // de arts geeft aan op welke stralen (1-5) de procedure gebeurde
  code_match: string[];
  frequentie: number | null; // hoe vaak al uitgevoerd
};
export type ProcedureAntwoord = { totaal: number; resultaten: Procedure[]; waarschuwingen: string[] };

// Alle procedures met hun RIZIV-codes (zie app/procedures.py, catalogus()).
export type CatalogusProcedure = {
  procedure_key: string;
  procedure_name: string | null;
  domein: string | null;
  nc_main_A: string | null;
  nc_main_H: string | null;
  nc_extra: string[];
  nc_gips: string[];
  nc_beeldvorming: string[];
  infiltratie: boolean;
  courant: boolean;
  revisie: boolean;
  detail_formulier: string | null;
  verschillende_stralen: boolean;
};
export type Codeinfo = {
  label: string | null;
  n_waarde: string | null;
  verblijf: string | null; // "ambulant" | "gehospitaliseerd"
  partner: string | null; // dezelfde dienst in de andere variant (A <-> H)
};
export type Catalogus = {
  procedures: CatalogusProcedure[];
  nomenclatuur: Record<string, Codeinfo>; // per RIZIV-code
  radioscopie: { nc_main: string; label: string | null; n_waarde: string | null; verblijf: string }[];
  gips: { nc_main: string; n_waarde: string | null; verblijf: string; beschrijving: string | null; zeldzaam: boolean; domeinen: string[] }[];
};

// Antwoord van POST /api/tarificatie/berekenen (zie app/tarificatie_codes.py): een voorstel, nog niets bewaard.
export type Rij = {
  id: string; // stabiel: blijft gelijk als het voorstel opnieuw berekend wordt (nodig voor de afwijkingen van de arts)
  code: string;
  soort: string; // Procedure | Extra | Beeldvorming | Gips | Radioscopie
  label: string | null;
  n_waarde: string | null;
  procedure: string | null;
  zijde: "Links" | "Rechts" | null;
  straal: number | null;
};
export type Voorstel = { rijen: Rij[]; aangepast: string[]; weggelaten: string[]; ingreep_procedure_key: string | null };
export type Selectie = { zijde: "Links" | "Rechts" | "Geen"; straal: number | null };
export type BerekenVerzoek = {
  ambulant_gehospitaliseerd: string;
  procedures: { procedure_key: string; selecties: Selectie[] }[];
};

// Antwoord van GET /api/ingrepen (zie app/ingrepen.py): de reeds geregistreerde ingrepen.
export type IngreepProcedure = { procedure_key: string; naam: string | null; zijden: string[]; stralen: number[] };
export type HistorischeIngreep = {
  ingreep_id: number;
  datum: string | null;
  patient_id: string;
  geslacht: string | null;
  leeftijd: number | null;
  arts: string | null;
  regio: string | null;
  lateraliteit: string | null;
  campus: string | null;
  verblijf: string | null;
  detailformulier: string | null;
  procedures: IngreepProcedure[];
};
export type IngrepenAntwoord = {
  totaal: number;
  pagina: number;
  per_pagina: number;
  mag_alle_artsen: boolean;
  artsen: { email: string; naam: string }[];
  regios: string[];
  ingrepen: HistorischeIngreep[];
};
