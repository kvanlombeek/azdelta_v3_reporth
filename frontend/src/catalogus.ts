import { useEffect, useState } from "react";
import { haalCatalogus } from "./api";
import type { Catalogus } from "./types";

// Bij het openen van de app wordt de procedurelijst eenmalig op de achtergrond opgehaald en in het
// geheugen bijgehouden. Schermen die ze nodig hebben (tarificatieoverzicht) gebruiken useCatalogus().
let belofte: Promise<Catalogus> | null = null;

export function laadCatalogus(): Promise<Catalogus> {
  belofte ??= haalCatalogus().catch((e) => {
    belofte = null; // bij een fout later opnieuw proberen
    throw e;
  });
  return belofte;
}

export function useCatalogus(): Catalogus | null {
  const [catalogus, setCatalogus] = useState<Catalogus | null>(null);
  useEffect(() => {
    laadCatalogus().then(setCatalogus).catch(() => {});
  }, []);
  return catalogus;
}
