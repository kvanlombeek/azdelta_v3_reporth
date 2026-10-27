import { useEffect, useState } from "react";
import { ApiFout, haalPlanning } from "./api";
import { Kader } from "./Kader";
import { INPUT } from "./velden";
import type { PlanningAntwoord, PlanningDag } from "./types";

const DAGEN = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"];
const MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"];
const FOCUS = "focus:outline-none focus-visible:ring-4 focus-visible:ring-accent";

// Datums blijven ISO-tekst (YYYY-MM-DD); rekenen op UTC om zomertijd te vermijden.
const naarDatum = (iso: string) => new Date(`${iso}T00:00:00Z`);
const plusDagen = (iso: string, n: number) => new Date(naarDatum(iso).getTime() + n * 86400000).toISOString().slice(0, 10);

function weeklabel(maandag: string): string {
  const a = naarDatum(maandag), z = naarDatum(plusDagen(maandag, 6));
  const deel = (d: Date, jaar = false, maand = true) => `${d.getUTCDate()}${maand ? ` ${MAANDEN[d.getUTCMonth()]}` : ""}${jaar ? ` ${d.getUTCFullYear()}` : ""}`;
  if (a.getUTCFullYear() !== z.getUTCFullYear()) return `${deel(a, true)} – ${deel(z, true)}`;
  if (a.getUTCMonth() !== z.getUTCMonth()) return `${deel(a)} – ${deel(z, true)}`;
  return `${deel(a, false, false)} – ${deel(z, true)}`;
}

export function Planning() {
  const params = new URLSearchParams(window.location.search);
  const [week, setWeek] = useState(params.get("week") ?? "");
  const [arts, setArts] = useState(params.get("arts") ?? "");
  const [data, setData] = useState<PlanningAntwoord | null>(null);
  const [fout, setFout] = useState<string | null>(null);
  const [dag, setDag] = useState<number | null>(null);
  const [poging, setPoging] = useState(0);

  useEffect(() => {
    let geannuleerd = false;
    setFout(null);
    haalPlanning(week, arts)
      .then((d) => {
        if (geannuleerd) return;
        setData(d);
        setDag((huidig) => huidig ?? d.dag_index);
      })
      .catch((e: unknown) => !geannuleerd && setFout(e instanceof ApiFout ? e.message : "Er ging iets mis."));
    return () => {
      geannuleerd = true;
    };
  }, [week, arts, poging]);

  // Houd week en arts in de URL, zodat de pagina herlaadbaar en deelbaar is.
  useEffect(() => {
    const q = new URLSearchParams({ ...(week && { week }), ...(arts && { arts }) }).toString();
    window.history.replaceState(null, "", q ? `/?${q}` : "/");
  }, [week, arts]);

  const kiesWeek = (w: string) => { setWeek(w); setDag(null); };
  const kiesArts = (a: string) => { setArts(a); };

  if (fout) {
    return (
      <Kader breed>
        <div className="mx-auto max-w-md rounded-xl bg-white p-8 shadow-sm ring-1 ring-line">
          <h1 className="text-lg font-semibold text-primary">Planning niet beschikbaar</h1>
          <p className="mt-2 text-sm text-muted">{fout}</p>
          <button onClick={() => setPoging((p) => p + 1)} className={`mt-6 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90 ${FOCUS}`}>
            Opnieuw proberen
          </button>
        </div>
      </Kader>
    );
  }
  if (!data) return <Kader breed><p className="py-20 text-center text-sm text-muted">Planning laden…</p></Kader>;

  const huidigeDag = dag ?? data.dag_index;
  const artsNaam = data.artsen.find((a) => a.email === data.arts_email)?.naam;
  const dezeWeek = data.maandag <= data.vandaag && data.vandaag < plusDagen(data.maandag, 7);
  const pijl = `rounded-md p-1 text-muted hover:text-primary ${FOCUS}`;

  return (
    <Kader breed>
      <div className="flex justify-end">
        <div className="w-full sm:w-64">
          <label htmlFor="arts" className="sr-only">Arts</label>
          <select id="arts" value={data.arts_email ?? ""} onChange={(e) => kiesArts(e.target.value)} className={INPUT}>
            {!data.arts_email && <option value="" disabled>Kies een arts…</option>}
            {data.artsen.map((a) => <option key={a.email} value={a.email}>{a.naam}</option>)}
          </select>
        </div>
      </div>

      {!data.overzicht ? (
        <>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-primary">Weekoverzicht</h1>
          <p className="mt-1 text-sm text-muted">Je account is niet gekoppeld aan een arts. Kies rechtsboven een arts om de planning te zien.</p>
        </>
      ) : (
        <>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-primary">{artsNaam}</h1>
          <p className="mt-1 text-sm text-muted">
            <span className="font-medium tabular-nums text-ink">{data.overzicht.gerapporteerd}/{data.overzicht.totaal}</span> ingrepen deze week reeds getarificeerd
          </p>

          <div className="mt-8 flex items-center gap-1 text-sm text-muted">
            {!dezeWeek && (
              <button onClick={() => kiesWeek("")} className={`mr-2 rounded-md font-medium text-primary hover:underline ${FOCUS}`}>Deze week</button>
            )}
            <button onClick={() => kiesWeek(plusDagen(data.maandag, -7))} className={pijl} aria-label="Vorige week">‹</button>
            <span className="tabular-nums">Week {data.weeknummer} · {weeklabel(data.maandag)}</span>
            <button onClick={() => kiesWeek(plusDagen(data.maandag, 7))} className={pijl} aria-label="Volgende week">›</button>
          </div>

          <div role="tablist" aria-label="Openstaande ingrepen per dag" className="mt-3 grid grid-cols-7 border-b border-line">
            {data.overzicht.dagen.map((d, i) => {
              const vandaag = d.datum === data.vandaag;
              return (
                <button
                  key={d.datum} role="tab" aria-selected={i === huidigeDag} onClick={() => setDag(i)}
                  aria-label={`${DAGEN[i]} ${naarDatum(d.datum).getUTCDate()}${vandaag ? " (vandaag)" : ""}, ${d.aantal_open} open`}
                  className={`-mb-px flex flex-col items-center gap-0.5 border-b-2 border-transparent px-1 pb-2 text-muted hover:text-primary aria-selected:border-primary aria-selected:text-primary ${FOCUS}`}
                >
                  <span className="text-xs"><span className="sm:hidden">{DAGEN[i].slice(0, 2)}</span><span className="hidden sm:inline">{DAGEN[i]}</span></span>
                  <span className={`font-medium tabular-nums ${vandaag ? "underline decoration-accent decoration-2 underline-offset-4" : ""}`}>{naarDatum(d.datum).getUTCDate()}</span>
                  <span className={`text-xs tabular-nums ${d.aantal_open ? "" : "opacity-40"}`}>{d.aantal_open} open</span>
                </button>
              );
            })}
          </div>
          <div className="mt-4"><Dagpaneel dag={data.overzicht.dagen[huidigeDag]} naam={DAGEN[huidigeDag]} /></div>
        </>
      )}
    </Kader>
  );
}

function Dagpaneel({ dag, naam }: { dag: PlanningDag; naam: string }) {
  return (
    <section role="tabpanel" aria-label={naam} className="rounded-xl border border-line bg-white">
      {dag.zalen.length === 0 && <p className="px-4 py-10 text-center text-sm text-muted">Geen openstaande ingrepen op deze dag.</p>}
      {dag.zalen.map((z) => (
        <div key={z.zaal ?? "onbekend"}>
          <h3 className="px-4 pt-4 pb-1 text-xs font-medium uppercase tracking-wide text-muted">{z.zaal || "Zaal onbekend"}</h3>
          <ul className="divide-y divide-line">
            {z.ingrepen.map((r) => (
              <li key={`${r.patient_id}-${r.planning_hash}`}>
                <a
                  href={`/tarificatie/nieuw/${encodeURIComponent(r.patient_id)}/${r.planning_hash}`}
                  className={`flex flex-col gap-0.5 px-4 py-3 hover:bg-surface sm:flex-row sm:items-baseline sm:gap-4 ${FOCUS}`}
                >
                  <span className="w-12 flex-none text-sm tabular-nums text-muted">{r.tijd}</span>
                  <span className="min-w-0 flex-1">{r.beschrijving || "Geen omschrijving"}</span>
                  <span className="text-sm tabular-nums text-muted">{[r.geslacht, r.geboortedatum].filter(Boolean).join(" · ")}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
