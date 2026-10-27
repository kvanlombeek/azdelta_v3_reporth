import { useEffect, useMemo, useRef, useState } from "react";
import { berekenTarificatie } from "./api";
import { useCatalogus } from "./catalogus";
import type { Opgeslagen, Rij, Voorstel } from "./types";
import { selecties, type Gekozen } from "./zijden";

const FOCUS = "focus:outline-none focus-visible:ring-4 focus-visible:ring-accent";

export function Tarificatie({ gekozen, verblijf, regio, kop, opgeslagen }: {
  gekozen: Gekozen[]; verblijf: string; regio: string; kop: string; // kop: lateraliteit bovenaan (SNOMED-code)
  opgeslagen?: Opgeslagen; // bestaande ingreep: zolang de procedures niet wijzigen, tonen we de opgeslagen codes
}) {
  const catalogus = useCatalogus();
  const [voorstel, setVoorstel] = useState<Voorstel | null>(null);
  const [fout, setFout] = useState(false);
  const [poging, setPoging] = useState(0);
  const [uit, setUit] = useState<Set<string>>(new Set()); // ids van voorgestelde regels die de arts verwijderde
  const [aan, setAan] = useState<Map<string, string>>(new Map()); // code -> soort, door de arts toegevoegd
  const [meerGips, setMeerGips] = useState(false);
  const [opslagMelding, setOpslagMelding] = useState(false);
  const v = verblijf.toLowerCase(); // "ambulant" | "gehospitaliseerd"

  // De server rekent het voorstel uit; hier blijven enkel de afwijkingen van de arts (uit/aan) bewaard.
  const verzoek = useMemo(() => JSON.stringify({
    ambulant_gehospitaliseerd: verblijf,
    procedures: gekozen.map((g) => ({ procedure_key: g.procedure.procedure_key, selecties: selecties(g, kop) })),
  }), [gekozen, verblijf, kop]);

  const beginVerzoek = useRef(verzoek);

  useEffect(() => {
    const stop = new AbortController();
    setFout(false);
    if (opgeslagen && verzoek === beginVerzoek.current) {
      // Niets gewijzigd: de opgeslagen codes zoals ze zijn, niet opnieuw berekend.
      setVoorstel({ rijen: opgeslagen.rijen, aangepast: [], weggelaten: [], ingreep_procedure_key: opgeslagen.procedure_key });
      return;
    }
    if (gekozen.length === 0) { setVoorstel({ rijen: [], aangepast: [], weggelaten: [], ingreep_procedure_key: null }); return; }
    berekenTarificatie(JSON.parse(verzoek), stop.signal)
      .then(setVoorstel)
      .catch((e: unknown) => { if (!stop.signal.aborted) { console.warn(e); setFout(true); } });
    return () => stop.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verzoek, poging]);

  // Andere variant (A/H) betekent andere codes: aanpassingen van de arts gelden dan niet meer.
  useEffect(() => { setUit(new Set()); setAan(new Map()); }, [verblijf]);

  if (fout) {
    return (
      <section className="rounded-xl border border-line bg-white p-6 text-sm" role="alert">
        <p className="text-muted">De codes konden niet berekend worden.</p>
        <button type="button" onClick={() => setPoging((p) => p + 1)} className={`mt-3 rounded-md font-medium text-primary underline ${FOCUS}`}>Opnieuw proberen</button>
      </section>
    );
  }
  if (!catalogus || !voorstel) {
    return <p className="rounded-xl border border-line bg-white p-6 text-sm text-muted">Codes berekenen…</p>;
  }

  const rijen: Rij[] = voorstel.rijen.filter((r) => !uit.has(r.id));
  for (const [code, soort] of aan) {
    if (rijen.some((r) => r.code === code)) continue;
    const info = catalogus.nomenclatuur[code];
    rijen.push({ id: code, code, soort, label: info?.label ?? null, n_waarde: info?.n_waarde ?? null, procedure: null, zijde: null, straal: null });
  }
  const aanwezig = (code: string) => rijen.some((r) => r.code === code);

  const wissel = (code: string, soort: string) => {
    if (aanwezig(code)) {
      setUit(new Set(uit).add(code));
      const a = new Map(aan); a.delete(code); setAan(a);
    } else {
      const u = new Set(uit); u.delete(code); setUit(u);
      if (!voorstel.rijen.some((r) => r.code === code)) setAan(new Map(aan).set(code, soort));
    }
  };

  const radioscopie = catalogus.radioscopie.filter((r) => r.verblijf === v);
  const gipsen = catalogus.gips.filter((g) => g.verblijf === v && g.domeinen.includes(regio));
  const zichtbareGips = meerGips ? gipsen : gipsen.filter((g) => !g.zeldzaam);
  const nogMeer = gipsen.filter((g) => g.zeldzaam).length;

  return (
    <section className="rounded-xl border border-line bg-white" aria-labelledby="tarificatie-titel">
      <div className="p-5 sm:px-6">
        <h2 id="tarificatie-titel" className="text-lg font-semibold tracking-tight">3. Tarificatie</h2>
        <p className="mt-0.5 text-sm text-muted">RIZIV-nummers {v}. Verwijder wat niet van toepassing is of voeg toe.</p>
      </div>

      <div className="space-y-6 border-t border-line p-5 sm:p-6">
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">Nomenclatuur</th>
                <th className="px-3 py-2 font-medium">N</th>
                <th className="px-3 py-2 font-medium">Omschrijving</th>
                <th className="px-3 py-2 font-medium">Lateraliteit</th>
                <th className="w-10 px-3 py-2"><span className="sr-only">Verwijderen</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rijen.map((r) => (
                <tr key={r.id} className="align-top">
                  <td className="px-3 py-2 font-mono text-xs">{r.code}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-muted">{r.n_waarde ?? "—"}</td>
                  <td className="px-3 py-2">
                    {r.label ?? <span className="text-muted">Omschrijving niet gevonden</span>}
                    <span className="block text-xs text-muted">{r.procedure ?? r.soort}</span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2">{[r.zijde, r.straal && `straal ${r.straal}`].filter(Boolean).join(" · ")}</td>
                  <td className="px-3 py-2 text-right">
                    <button type="button" onClick={() => (r.procedure ? setUit(new Set(uit).add(r.id)) : wissel(r.code, r.soort))}
                      aria-label={`Verwijder ${r.code}`} className={`rounded-md px-2 text-lg leading-none text-muted hover:text-primary ${FOCUS}`}>×</button>
                  </td>
                </tr>
              ))}
              {rijen.length === 0 && (
                <tr><td colSpan={5} className="px-3 py-6 text-center text-muted">Geen codes. Voeg er hieronder toe.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {(voorstel.aangepast.length > 0 || voorstel.weggelaten.length > 0) && (
          <div className="space-y-1 text-xs text-muted">
            {voorstel.aangepast.length > 0 && <p>Aangepast aan {v}: {voorstel.aangepast.join(", ")}.</p>}
            {voorstel.weggelaten.map((w) => <p key={w}>Weggelaten: {w}.</p>)}
          </div>
        )}

        <div className="grid gap-6 sm:grid-cols-2">
          <fieldset>
            <legend className="text-sm font-semibold">Radioscopie</legend>
            <div className="mt-1">
              {radioscopie.map((r) => (
                <label key={r.nc_main} className="flex cursor-pointer items-start gap-2 py-0.5 text-sm">
                  <input type="checkbox" checked={aanwezig(r.nc_main)} onChange={() => wissel(r.nc_main, "Radioscopie")}
                    className={`mt-0.5 h-4 w-4 flex-none accent-[var(--color-primary)] ${FOCUS}`} />
                  <span><span className="font-mono text-xs">{r.nc_main}</span> {r.label}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="text-sm font-semibold">Gips {regio && <span className="font-normal text-muted">· {regio}</span>}</legend>
            <div className="mt-1">
              {zichtbareGips.map((g) => (
                <label key={g.nc_main} className="flex cursor-pointer items-start gap-2 py-0.5 text-sm">
                  <input type="checkbox" checked={aanwezig(g.nc_main)} onChange={() => wissel(g.nc_main, "Gips")}
                    className={`mt-0.5 h-4 w-4 flex-none accent-[var(--color-primary)] ${FOCUS}`} />
                  <span><span className="font-mono text-xs">{g.nc_main}</span> {g.beschrijving}</span>
                </label>
              ))}
              {zichtbareGips.length === 0 && <p className="text-sm text-muted">Geen gips voor deze regio.</p>}
              {nogMeer > 0 && (
                <button type="button" onClick={() => setMeerGips(!meerGips)} className={`mt-1 rounded text-xs font-medium text-primary underline ${FOCUS}`}>
                  {meerGips ? "Minder tonen" : `Meer gipsen (${nogMeer})`}
                </button>
              )}
            </div>
          </fieldset>
        </div>

        <div className="flex flex-wrap items-center gap-4 border-t border-line pt-5">
          <button type="button" disabled={rijen.length === 0} onClick={() => setOpslagMelding(true)}
            className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-accent-ink hover:brightness-95 disabled:opacity-40 disabled:hover:brightness-100 focus:outline-none focus-visible:ring-4 focus-visible:ring-primary/30">
            Tarificatie opslaan
          </button>
          {opslagMelding && <p role="status" className="text-sm text-muted">Opslaan is nog niet beschikbaar.</p>}
        </div>
      </div>
    </section>
  );
}
