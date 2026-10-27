import { foutmelding, gekozenZijden, kopZijden, STRALEN, zijdeRijen, type Gekozen, type Zijde } from "./zijden";

const FOCUS = "peer-focus-visible:ring-4 peer-focus-visible:ring-accent";

// Eén aanvinkbaar vakje; zijden en stralen hebben dezelfde vorm.
function Vakje({ label, aan, fout, onChange, aria }: { label: string; aan: boolean; fout?: boolean; onChange: () => void; aria?: string }) {
  return (
    <label className="cursor-pointer">
      <input type="checkbox" checked={aan} onChange={onChange} aria-label={aria} className="peer sr-only" />
      <span className={`flex h-7 min-w-7 items-center justify-center rounded-md px-2 text-sm ring-1 ${fout ? "text-red-600 ring-red-400" : "ring-line"} peer-checked:bg-surface peer-checked:font-semibold peer-checked:text-primary peer-checked:ring-2 peer-checked:ring-primary ${FOCUS}`}>
        {label}
      </span>
    </label>
  );
}

// Zijde (en straal) van één gekozen procedure. De lateraliteit bovenaan is de voorinvulling.
export function Zijdekeuze({ g, kop, toonFout, onChange }: {
  g: Gekozen; kop: string; toonFout: boolean; onChange: (g: Gekozen) => void;
}) {
  const melding = toonFout ? foutmelding(g, kop) : null;

  if (!g.procedure.verschillende_stralen) {
    if (zijdeRijen(kop)[0] === "Geen") return null;
    const nu = gekozenZijden(g, kop);
    const wissel = (z: Zijde) =>
      onChange({ ...g, zijden: (["Links", "Rechts"] as Zijde[]).filter((x) => (x === z ? !nu.includes(z) : nu.includes(x))) });
    return (
      <div className="flex flex-none flex-col items-end gap-1" role="group" aria-label={`Zijde van ${g.procedure.procedure_name}`}>
        <div className="flex gap-1.5">
          {(["Links", "Rechts"] as Zijde[]).map((z) => (
            <Vakje key={z} label={z} aan={nu.includes(z)} fout={!!melding} onChange={() => wissel(z)} />
          ))}
        </div>
        {melding && <span role="alert" className="text-xs text-red-600">{melding}</span>}
      </div>
    );
  }

  const wisselStraal = (z: Zijde, n: number) => {
    const huidig = g.stralen[z];
    const nieuw = huidig.includes(n) ? huidig.filter((x) => x !== n) : [...huidig, n].sort();
    onChange({ ...g, stralen: { ...g.stralen, [z]: nieuw } });
  };
  const verwacht = kopZijden(kop);
  const vakjes = (z: Zijde) =>
    STRALEN.map((n) => <Vakje key={n} label={String(n)} aan={g.stralen[z].includes(n)} onChange={() => wisselStraal(z, n)} aria={`Straal ${n}`} />);
  const rij = (z: Zijde, label: string) => (
    <div role="group" aria-label={label} className="flex items-center gap-2">
      <span className={`w-12 text-right text-xs ${verwacht.includes(z) && g.stralen[z].length === 0 ? "font-semibold text-primary" : "font-medium text-muted"}`}>{label}</span>
      <div className="flex gap-1.5">{vakjes(z)}</div>
    </div>
  );
  // Rechts uitgelijnd, op dezelfde plaats als de vinkjes Links/Rechts bij procedures zonder stralen.
  return (
    <div className="flex flex-none flex-col items-end gap-1.5">
      {zijdeRijen(kop)[0] === "Geen" ? rij("Geen", "Straal") : (<>{rij("Links", "Links")}{rij("Rechts", "Rechts")}</>)}
      {melding && <p role="alert" className="text-xs text-red-600">{melding}</p>}
    </div>
  );
}
