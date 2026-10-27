import type { BerekenVerzoek, Catalogus, IngrepenAntwoord, PlanningAntwoord, ProcedureAntwoord, TarificatieAntwoord, Voorstel } from "./types";

export class ApiFout extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const FOUTTEKSTEN: Record<number, string> = {
  403: "Je hebt geen toegang tot deze pagina.",
  404: "Deze ingreep werd niet gevonden, of is te oud om te tarificeren.",
  409: "De planning is ondertussen gewijzigd. Ga terug naar de planning en open de ingreep opnieuw.",
  503: "De database is even niet bereikbaar. Probeer het zo meteen opnieuw.",
};

async function haal<T>(url: string, signal?: AbortSignal, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method: body === undefined ? "GET" : "POST",
    headers: { Accept: "application/json", ...(body !== undefined && { "Content-Type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (r.status === 401) {
    window.location.href = "/aanmelden";
    return new Promise(() => {}); // pagina wordt verlaten
  }
  if (!r.ok) throw new ApiFout(r.status, FOUTTEKSTEN[r.status] ?? "Er ging iets mis. Probeer het opnieuw.");
  return r.json();
}

export const haalNieuweTarificatie = (patientId: string, hash: string) =>
  haal<TarificatieAntwoord>(`/api/tarificatie/nieuw/${encodeURIComponent(patientId)}/${encodeURIComponent(hash)}`);

export const haalBestaandeTarificatie = (ingreepId: number) => haal<TarificatieAntwoord>(`/api/tarificatie/ingreep/${ingreepId}`);

export const haalPlanning = (week: string, arts: string) =>
  haal<PlanningAntwoord>(`/api/planning?${new URLSearchParams({ ...(week && { week }), ...(arts && { arts }) })}`);

export const haalGebruiker = () => haal<{ name: string }>("/auth/me");

export const haalProcedures = (q: string, domein: string, sorteer: string, signal: AbortSignal) =>
  haal<ProcedureAntwoord>(`/api/procedures?${new URLSearchParams({ q, domein, sorteer, k: "10" })}`, signal);

export const haalCatalogus = () => haal<Catalogus>("/api/procedures/catalogus");

export const berekenTarificatie = (verzoek: BerekenVerzoek, signal: AbortSignal) =>
  haal<Voorstel>("/api/tarificatie/berekenen", signal, verzoek);

export const haalIngrepen = (filters: Record<string, string>, signal: AbortSignal) =>
  haal<IngrepenAntwoord>(`/api/ingrepen?${new URLSearchParams(Object.entries(filters).filter(([, w]) => w))}`, signal);
