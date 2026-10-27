import type { Procedure, Selectie } from "./types";

// Zijde en straal per gekozen procedure. Wat de arts aanvinkt zijn precies de rijen die later bewaard worden:
// één rij per (zijde, straal). "Geen": lateraliteit niet van toepassing.
export type Zijde = "Links" | "Rechts" | "Geen";
export const STRALEN = [1, 2, 3, 4, 5];

export type Gekozen = {
  procedure: Procedure;
  zijden: Zijde[] | null; // null = volgt de lateraliteit bovenaan, tot de arts zelf iets wijzigt
  stralen: Record<Zijde, number[]>; // enkel gebruikt bij procedures met verschillende stralen
};

// SNOMED-codes van de lateraliteit (zie app/tarificatie.py).
const LINKS = "7771000";
const RECHTS = "24028007";
const BILATERAAL = "51440002";
const NIET_VAN_TOEPASSING = "24847006";

export function nieuweKeuze(procedure: Procedure): Gekozen {
  return { procedure, zijden: null, stralen: { Links: [], Rechts: [], Geen: [] } };
}

/** De zijden die de lateraliteit bovenaan aanduidt. */
export function kopZijden(kop: string): Zijde[] {
  if (kop === LINKS) return ["Links"];
  if (kop === RECHTS) return ["Rechts"];
  if (kop === BILATERAAL) return ["Links", "Rechts"];
  return [];
}

/** De zijden waarvoor de arts een keuze krijgt: links en rechts, of niets bij "niet van toepassing". */
export function zijdeRijen(kop: string): Zijde[] {
  return kop === NIET_VAN_TOEPASSING ? ["Geen"] : ["Links", "Rechts"];
}

export function gekozenZijden(g: Gekozen, kop: string): Zijde[] {
  return g.zijden ?? kopZijden(kop);
}

/** Melding als de keuze nog onvolledig is, anders null. */
export function foutmelding(g: Gekozen, kop: string): string | null {
  if (g.procedure.verschillende_stralen) {
    return zijdeRijen(kop).some((z) => g.stralen[z].length > 0) ? null : "Kies minstens één straal.";
  }
  if (kop === NIET_VAN_TOEPASSING) return null;
  return gekozenZijden(g, kop).length > 0 ? null : "Kies links, rechts of beide.";
}

/** De (zijde, straal)-lijst van een gekozen procedure: precies de rijen die de server uitrekent en later bewaart. */
export function selecties(g: Gekozen, kop: string): Selectie[] {
  if (g.procedure.verschillende_stralen) {
    return zijdeRijen(kop).flatMap((z) => g.stralen[z].map((straal) => ({ zijde: z, straal })));
  }
  const zijden = kop === NIET_VAN_TOEPASSING ? (["Geen"] as Zijde[]) : gekozenZijden(g, kop);
  return zijden.map((zijde) => ({ zijde, straal: null }));
}
