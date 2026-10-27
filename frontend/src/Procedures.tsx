import { useEffect, useState } from "react";
import { haalProcedures } from "./api";
import type { Procedure, ProcedureAntwoord } from "./types";
import { foutmelding, nieuweKeuze, type Gekozen } from "./zijden";
import { Uitklapknop } from "./velden";
import { Zijdekeuze } from "./Zijdekeuze";

const FOCUS = "focus:outline-none focus-visible:ring-4 focus-visible:ring-accent";

// Het verblijf bepaalt welke RIZIV-nomenclatuurcode (en omschrijving) geldt: A = ambulant, H = gehospitaliseerd.
function Rizivregel({ p, verblijf }: { p: Procedure; verblijf: string }) {
  const h = verblijf === "Gehospitaliseerd";
  const nummer = h ? p.nc_main_H : p.nc_main_A;
  const label = h ? p.label_H : p.label_A;
  if (!nummer) return <span className="text-xs text-muted">Geen RIZIV-code {h ? "gehospitaliseerd" : "ambulant"}</span>;
  return (
    // Eén regel; wat niet past wordt afgekapt, de volledige omschrijving staat in de tooltip.
    <span className="block truncate text-xs text-muted" title={label ? `${nummer} · ${label}` : nummer}>
      <span className="font-mono">{h ? "H" : "A"}: {nummer}</span>
      {label && <> · {label}</>}
    </span>
  );
}

export function Procedures({ startzoek, gematcht, regio, verblijf, lateraliteit, gekozen, setGekozen, open, klaar, onVolgende, onToggle }: {
  startzoek: string | null; gematcht: Procedure[]; regio: string; verblijf: string; lateraliteit: string; // lateraliteit: SNOMED-code uit de kop
  gekozen: Gekozen[]; setGekozen: (p: Gekozen[]) => void;
  open: boolean; klaar: boolean; onVolgende: () => void; onToggle: () => void; // klaar: de arts ging al door naar de tarificatie
}) {
  // De omschrijving uit de planning is het startpunt; de arts kan ze aanpassen of wissen.
  const [q, setQ] = useState(startzoek ?? "");
  const [enkelRegio, setEnkelRegio] = useState(true);
  const [antwoord, setAntwoord] = useState<ProcedureAntwoord | null>(null);
  const [fout, setFout] = useState<string | null>(null);
  const [sorteer, setSorteer] = useState<"fit" | "populariteit">("fit");
  const [toonFouten, setToonFouten] = useState(false); // na een poging om verder te gaan

  const domein = enkelRegio ? regio : "";

  // Zolang de zoektekst nog die van de planning is, staan de vooraf gematchte procedures bovenaan,
  // gevolgd door de zoekresultaten. Typt de arts iets anders, dan telt enkel nog het zoeken.
  const metPlanning = gematcht.length > 0 && q === (startzoek ?? "");
  const lijst = antwoord
    ? metPlanning
      ? [...gematcht, ...antwoord.resultaten.filter((p) => !gematcht.some((m) => m.procedure_key === p.procedure_key))].slice(0, Math.max(antwoord.resultaten.length, gematcht.length))
      : antwoord.resultaten
    : [];

  useEffect(() => {
    const controller = new AbortController();
    // Wachten tot de arts stopt met typen; een lege zoekvraag toont meteen de populairste.
    const timer = setTimeout(() => {
      setFout(null);
      haalProcedures(q.trim(), domein, sorteer, controller.signal)
        .then(setAntwoord)
        .catch((e: unknown) => {
          if (e instanceof DOMException && e.name === "AbortError") return;
          setFout("Zoeken is mislukt. Probeer het opnieuw.");
        });
    }, q ? 300 : 0);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [q, domein, sorteer]);

  const isGekozen = (p: Procedure) => gekozen.some((g) => g.procedure.procedure_key === p.procedure_key);
  const voegToe = (p: Procedure) => !isGekozen(p) && setGekozen([...gekozen, nieuweKeuze(p)]);
  const verwijder = (p: Procedure) => setGekozen(gekozen.filter((g) => g.procedure.procedure_key !== p.procedure_key));
  const wijzig = (nieuw: Gekozen) => setGekozen(gekozen.map((g) => (g.procedure.procedure_key === nieuw.procedure.procedure_key ? nieuw : g)));
  const verder = () => {
    if (gekozen.some((g) => foutmelding(g, lateraliteit))) {
      setToonFouten(true);
      return;
    }
    onVolgende();
  };

  return (
    <section className="rounded-xl border border-line bg-white" aria-labelledby="procedures-titel">
      <div className="flex items-start gap-3 p-5 sm:px-6">
        {klaar && !open && (
          <span aria-hidden className="mt-0.5 flex h-6 w-6 flex-none items-center justify-center rounded-full bg-accent text-accent-ink">✓</span>
        )}
        <div className="min-w-0 flex-1">
          <h2 id="procedures-titel" className="text-lg font-semibold tracking-tight">2. Procedures</h2>
          <p className="mt-0.5 text-sm text-muted">
            {open ? "Kies één of meer uitgevoerde procedures." : gekozen.map((g) => g.procedure.procedure_name).join(" · ")}
          </p>
        </div>
        {klaar && <Uitklapknop open={open} onClick={onToggle} label="procedures" />}
      </div>

      <div className={`space-y-5 border-t border-line p-5 sm:p-6 ${open ? "" : "hidden"}`}>
        <div>
          <label htmlFor="zoek" className="block text-sm font-semibold">Procedure zoeken</label>
          <input
            id="zoek" type="search" autoComplete="off" spellCheck={false} value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="bv. voorste kruisband, carpale tunnel, 285250"
            className={`mt-1 block w-full rounded-lg border border-line bg-white px-3 py-2 text-sm ${FOCUS}`}
          />
          {startzoek && q === startzoek ? (
            <p className="mt-1 text-xs text-muted">
              Ingevuld vanuit de planning. Pas aan of{" "}
              <button type="button" onClick={() => setQ("")} className={`rounded font-medium text-primary underline ${FOCUS}`}>wis</button>{" "}
              om de populairste procedures te zien.
            </p>
          ) : (
            <p className="mt-1 text-xs text-muted">Zoek op omschrijving of RIZIV-code. Geen patiëntgegevens invoeren.</p>
          )}
          {regio && (
            <label className="mt-2 flex cursor-pointer items-center gap-2 text-sm">
              <input type="checkbox" checked={enkelRegio} onChange={(e) => setEnkelRegio(e.target.checked)} className={`h-4 w-4 accent-[var(--color-primary)] ${FOCUS}`} />
              Enkel {regio}
            </label>
          )}
        </div>

        <div aria-live="polite">
          {fout && <p role="alert" className="text-sm text-red-600">{fout}</p>}
          {antwoord?.waarschuwingen.map((w) => <p key={w} className="text-xs text-muted">{w}</p>)}
          {antwoord && !fout && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-xs font-medium uppercase tracking-wide text-muted">
                  {q.trim() ? `${lijst.length} van ${antwoord.totaal} resultaten` : `Populairste procedures${domein ? ` · ${domein}` : ""}`}
                </h3>
                {q.trim() && (
                  <div className="flex items-center gap-1 text-xs text-muted" role="group" aria-label="Sorteren">
                    Sorteer op:
                    {([["fit", "Beste match", "Hoe goed de procedure past bij je zoektekst"], ["populariteit", "Populariteit", "Hoe vaak de procedure al werd uitgevoerd"]] as const).map(([w, label, uitleg]) => (
                      <button
                        key={w} type="button" title={uitleg} aria-pressed={sorteer === w} onClick={() => setSorteer(w)}
                        className={`rounded-md px-2 py-0.5 hover:text-primary ${sorteer === w ? "bg-surface font-semibold text-primary ring-1 ring-line" : ""} ${FOCUS}`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {lijst.length === 0 ? (
                <p className="mt-2 text-sm text-muted">Geen procedures gevonden.</p>
              ) : (
                <ul className="mt-2 divide-y divide-line rounded-lg border border-line">
                  {lijst.map((p) => (
                    <li key={p.procedure_key} className="flex items-center gap-3 px-3 py-2.5 text-sm">
                      {/* De hele naam is de knop: een klik voegt de procedure toe (of verwijdert ze weer). */}
                      <button
                        type="button" aria-pressed={isGekozen(p)} onClick={() => (isGekozen(p) ? verwijder(p) : voegToe(p))}
                        className={`group flex min-w-0 flex-1 items-center gap-3 rounded-md text-left ${FOCUS}`}
                      >
                        <span
                          aria-hidden
                          className={`flex h-6 w-6 flex-none items-center justify-center rounded-full ${
                            isGekozen(p) ? "bg-accent text-accent-ink" : "text-muted ring-1 ring-line group-hover:text-primary group-hover:ring-primary"
                          }`}
                        >
                          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            {isGekozen(p) ? <path d="M3 8.5l3.2 3L13 4.5" /> : <path d="M8 3v10M3 8h10" />}
                          </svg>
                        </span>
                        <span className="min-w-0 flex-1">
                          {p.procedure_name}
                          {!enkelRegio && p.domein && <span className="ml-2 text-xs text-muted">{p.domein}</span>}
                          <Rizivregel p={p} verblijf={verblijf} />
                        </span>
                      </button>
                      <span className="hidden flex-none text-right text-xs text-muted sm:block">
                        <span className="block font-mono" title="procedure_key">{p.procedure_key}</span>
                        {p.frequentie ? `${p.frequentie}× uitgevoerd` : "nog niet uitgevoerd"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>

        {gekozen.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold">Geselecteerd ({gekozen.length})</h3>
            <ul className="mt-2 divide-y divide-line rounded-lg border border-line">
              {gekozen.map((g) => (
                <li key={g.procedure.procedure_key} className={`flex gap-3 px-3 py-2 text-sm ${g.procedure.verschillende_stralen ? "items-start" : "items-center"}`}>
                  <span className="min-w-0 flex-1">
                    {g.procedure.procedure_name}
                    <Rizivregel p={g.procedure} verblijf={verblijf} />
                  </span>
                  <Zijdekeuze g={g} kop={lateraliteit} toonFout={toonFouten} onChange={wijzig} />
                  <button type="button" onClick={() => verwijder(g.procedure)} aria-label={`Verwijder ${g.procedure.procedure_name}`}
                    className={`rounded-md px-2 text-lg leading-none text-muted hover:text-primary ${FOCUS}`}>×</button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-4 border-t border-line pt-5">
          <button
            type="button" disabled={gekozen.length === 0} onClick={verder}
            className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-accent-ink hover:brightness-95 disabled:opacity-40 disabled:hover:brightness-100 focus:outline-none focus-visible:ring-4 focus-visible:ring-primary/30"
          >
            Volgende: tarificatie
          </button>
        </div>
      </div>
    </section>
  );
}
