import { useEffect, useState } from "react";
import { ApiFout, haalIngrepen } from "./api";
import { Kader } from "./Kader";
import { INPUT } from "./velden";
import type { HistorischeIngreep, IngrepenAntwoord, IngreepProcedure } from "./types";

const FOCUS = "focus:outline-none focus-visible:ring-4 focus-visible:ring-accent";
const FILTERS = ["arts", "regio", "q", "patient", "van", "tot"] as const;

const datum = (iso: string | null) => (iso ? iso.split("-").reverse().join("/") : "–");

function procedureDetail(p: IngreepProcedure): string {
  const zijden = p.zijden.join(" + ");
  const stralen = p.stralen.length ? `straal ${p.stralen.join(", ")}` : "";
  return [zijden, stralen].filter(Boolean).join(" · ");
}

// De drie vervolgstappen van een ingreep. Het detailformulier en de brief bestaan nog niet: tot dan uitgeschakelde knoppen.
const KNOP = "rounded-md px-2 py-1 text-xs font-medium text-primary ring-1 ring-line";

function Stappen({ ingreep }: { ingreep: HistorischeIngreep }) {
  return (
    <div className="flex flex-wrap justify-end gap-1.5">
      <a href={`/tarificatie/ingreep/${ingreep.ingreep_id}`} className={`${KNOP} hover:bg-surface ${FOCUS}`}>Tarificatie</a>
      {["Detailformulier", "Brief"].map((naam) => (
        <button key={naam} type="button" disabled title="Nog niet beschikbaar" aria-label={`${naam} van ingreep ${ingreep.ingreep_id}`}
          className={`${KNOP} disabled:cursor-not-allowed disabled:opacity-40`}>
          {naam}
        </button>
      ))}
    </div>
  );
}

export function Ingrepen() {
  const url = new URLSearchParams(window.location.search);
  const [filters, setFilters] = useState<Record<(typeof FILTERS)[number], string>>(
    Object.fromEntries(FILTERS.map((f) => [f, url.get(f) ?? ""])) as Record<(typeof FILTERS)[number], string>,
  );
  const [zoek, setZoek] = useState(filters.q); // wat getypt wordt; pas na even wachten een filter
  const [pagina, setPagina] = useState(Number(url.get("pagina")) || 1);
  const [data, setData] = useState<IngrepenAntwoord | null>(null);
  const [fout, setFout] = useState<string | null>(null);
  const [poging, setPoging] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => {
      if (zoek.trim() === filters.q) return; // niets gewijzigd (ook bij het openen): pagina en filters blijven
      setFilters((f) => ({ ...f, q: zoek.trim() }));
      setPagina(1);
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoek]);

  useEffect(() => {
    const stop = new AbortController();
    setFout(null);
    haalIngrepen({ ...filters, pagina: pagina > 1 ? String(pagina) : "" }, stop.signal)
      .then(setData)
      .catch((e: unknown) => {
        if (stop.signal.aborted) return;
        setFout(e instanceof ApiFout ? e.message : "Er ging iets mis.");
      });
    // Filters en pagina blijven in de URL: herlaadbaar en deelbaar.
    const q = new URLSearchParams(Object.entries({ ...filters, pagina: pagina > 1 ? String(pagina) : "" }).filter(([, w]) => w)).toString();
    window.history.replaceState(null, "", q ? `/ingrepen?${q}` : "/ingrepen");
    return () => stop.abort();
  }, [filters, pagina, poging]);

  const zet = (k: (typeof FILTERS)[number], w: string) => { setFilters((f) => ({ ...f, [k]: w })); setPagina(1); };
  const filtersActief = FILTERS.some((f) => filters[f]);
  const wis = () => { setZoek(""); setFilters({ arts: "", regio: "", q: "", patient: "", van: "", tot: "" }); setPagina(1); };

  if (fout) {
    return (
      <Kader breed>
        <div className="mx-auto max-w-md rounded-xl bg-white p-8 shadow-sm ring-1 ring-line">
          <h1 className="text-lg font-semibold text-primary">Ingrepen niet beschikbaar</h1>
          <p className="mt-2 text-sm text-muted">{fout}</p>
          <button onClick={() => setPoging((p) => p + 1)} className={`mt-6 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90 ${FOCUS}`}>
            Opnieuw proberen
          </button>
        </div>
      </Kader>
    );
  }

  const eerste = data ? (data.pagina - 1) * data.per_pagina + 1 : 0;
  const laatste = data ? eerste + data.ingrepen.length - 1 : 0;
  const veld = "block text-xs font-medium text-muted";

  return (
    <Kader breed>
      <h1 className="text-2xl font-semibold tracking-tight text-primary">Ingrepen</h1>
      <p className="mt-1 text-sm text-muted">Je chirurgisch logboek: alle geregistreerde ingrepen, nieuwste eerst.</p>

      <form onSubmit={(e) => e.preventDefault()} className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-6" role="search">
        <div className="lg:col-span-2">
          <label htmlFor="f-arts" className={veld}>Arts</label>
          {/* Een gewone arts ziet enkel de eigen ingrepen: de keuze staat vast. Assistenten en admins kiezen vrij. */}
          <select id="f-arts" value={data?.mag_alle_artsen ? filters.arts : (data?.artsen[0]?.email ?? "")} disabled={!data?.mag_alle_artsen}
            onChange={(e) => zet("arts", e.target.value)} className={`mt-1 ${INPUT} disabled:bg-surface disabled:text-muted`}>
            {data?.mag_alle_artsen && <option value="">Alle artsen</option>}
            {(data?.artsen ?? []).map((a) => <option key={a.email} value={a.email}>{a.naam}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="f-regio" className={veld}>Lichaamsregio</label>
          <select id="f-regio" value={filters.regio} onChange={(e) => zet("regio", e.target.value)} className={`mt-1 ${INPUT}`}>
            <option value="">Alle regio's</option>
            {(data?.regios ?? []).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="f-van" className={veld}>Van</label>
          <input id="f-van" type="date" value={filters.van} max={filters.tot || undefined} onChange={(e) => zet("van", e.target.value)} className={`mt-1 ${INPUT}`} />
        </div>
        <div>
          <label htmlFor="f-tot" className={veld}>Tot en met</label>
          <input id="f-tot" type="date" value={filters.tot} min={filters.van || undefined} onChange={(e) => zet("tot", e.target.value)} className={`mt-1 ${INPUT}`} />
        </div>
        <div className="lg:col-span-2">
          <label htmlFor="f-patient" className={veld}>Patiënt-id</label>
          <input id="f-patient" type="search" autoComplete="off" inputMode="numeric" value={filters.patient}
            onChange={(e) => zet("patient", e.target.value.trim())} placeholder="Plak een patiënt-id" className={`mt-1 ${INPUT}`} />
        </div>
        <div className="sm:col-span-2 lg:col-span-4">
          <label htmlFor="f-q" className={veld}>Zoeken</label>
          <input id="f-q" type="search" autoComplete="off" value={zoek} onChange={(e) => setZoek(e.target.value)}
            placeholder="Procedure, patiënt- of opnamenummer" className={`mt-1 ${INPUT}`} />
        </div>
      </form>

      <div className="mt-6 flex min-h-5 items-center justify-between text-sm text-muted" aria-live="polite">
        <span>
          {!data ? "Laden…" : data.totaal === 0 ? "Geen ingrepen gevonden." : `${eerste}–${laatste} van ${data.totaal} ingrepen`}
        </span>
        {filtersActief && (
          <button type="button" onClick={wis} className={`rounded-md font-medium text-primary hover:underline ${FOCUS}`}>Filters wissen</button>
        )}
      </div>

      {data && data.ingrepen.length > 0 && (
        <div className="mt-2 overflow-x-auto rounded-xl border border-line bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">Datum</th>
                <th className="px-3 py-2 font-medium">Patiënt</th>
                <th className="px-3 py-2 font-medium">Procedures</th>
                {data.mag_alle_artsen && <th className="px-3 py-2 font-medium">Arts</th>}
                <th className="px-3 py-2 font-medium">Regio</th>
                <th className="px-3 py-2"><span className="sr-only">Openen</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.ingrepen.map((i) => (
                <tr key={i.ingreep_id} className="align-top">
                  <td className="whitespace-nowrap px-3 py-2.5 tabular-nums">{datum(i.datum)}</td>
                  <td className="whitespace-nowrap px-3 py-2.5">
                    {i.patient_id}
                    <span className="block text-xs text-muted">
                      {[i.geslacht, i.leeftijd != null && `${i.leeftijd} jaar`].filter(Boolean).join(" · ")}
                    </span>
                  </td>
                  <td className="min-w-64 px-3 py-2.5">
                    {i.procedures.length === 0 && <span className="text-muted">–</span>}
                    {i.procedures.map((p) => (
                      <div key={p.procedure_key} className="pb-1 last:pb-0">
                        {p.naam ?? p.procedure_key}
                        <span className="block text-xs text-muted">
                          <span className="font-mono">{p.procedure_key}</span>
                          {procedureDetail(p) && ` · ${procedureDetail(p)}`}
                        </span>
                      </div>
                    ))}
                    {i.procedures.length === 0 && i.lateraliteit && <span className="text-xs text-muted">{i.lateraliteit}</span>}
                  </td>
                  {data.mag_alle_artsen && <td className="px-3 py-2.5">{i.arts ?? "–"}</td>}
                  <td className="whitespace-nowrap px-3 py-2.5">{i.regio ?? "–"}</td>
                  <td className="px-3 py-2.5"><Stappen ingreep={i} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.totaal > data.per_pagina && (
        <nav className="mt-4 flex items-center justify-between text-sm" aria-label="Pagina's">
          <button type="button" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}
            className={`rounded-md px-3 py-1.5 font-medium text-primary ring-1 ring-line disabled:opacity-40 ${FOCUS}`}>‹ Vorige</button>
          <span className="tabular-nums text-muted">Pagina {data.pagina} van {Math.ceil(data.totaal / data.per_pagina)}</span>
          <button type="button" disabled={laatste >= data.totaal} onClick={() => setPagina(pagina + 1)}
            className={`rounded-md px-3 py-1.5 font-medium text-primary ring-1 ring-line disabled:opacity-40 ${FOCUS}`}>Volgende ›</button>
        </nav>
      )}
    </Kader>
  );
}
