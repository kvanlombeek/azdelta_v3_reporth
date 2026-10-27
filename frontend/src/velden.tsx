import type { ReactNode } from "react";

const FOCUS = "focus:outline-none focus-visible:ring-4 focus-visible:ring-accent";
export const INPUT = `block w-full rounded-lg border border-line bg-white px-3 py-2 text-sm ${FOCUS} aria-[invalid=true]:border-red-500`;

export function Veld({ label, verplicht, hint, fout, htmlFor, children }: {
  label: string; verplicht?: boolean; hint?: string; fout?: string; htmlFor?: string; children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-sm font-semibold">
        {label}
        {verplicht && <span className="text-red-600" aria-hidden> *</span>}
      </label>
      {hint && <p className="mb-1 text-xs text-muted">{hint}</p>}
      <div className="mt-1">{children}</div>
      {fout && <p role="alert" className="mt-1 text-xs text-red-600">{fout}</p>}
    </div>
  );
}

// Radio's, compact. `kolommen`: opties verdelen over twee kolommen; `inline`: naast elkaar op één regel.
export function Keuzerondjes({ legende, verplicht, naam, opties, waarde, onChange, fout, kolommen, inline }: {
  legende: string; verplicht?: boolean; naam: string; opties: { waarde: string; label: string }[];
  waarde: string | null; onChange: (w: string) => void; fout?: string; kolommen?: boolean; inline?: boolean;
}) {
  const indeling = inline ? "flex flex-wrap gap-x-5" : kolommen ? "grid grid-cols-2 gap-x-4" : "grid";
  return (
    <fieldset>
      <legend className="text-sm font-semibold">
        {legende}
        {verplicht && <span className="text-red-600" aria-hidden> *</span>}
      </legend>
      <div className={`mt-1 ${indeling}`}>
        {opties.map((o) => (
          <label key={o.waarde} className="flex cursor-pointer items-center gap-2 py-0.5 text-sm">
            <input
              type="radio" name={naam} value={o.waarde} checked={waarde === o.waarde} onChange={() => onChange(o.waarde)}
              className={`h-4 w-4 accent-[var(--color-primary)] ${FOCUS}`}
            />
            {o.label}
          </label>
        ))}
      </div>
      {fout && <p role="alert" className="mt-1 text-xs text-red-600">{fout}</p>}
    </fieldset>
  );
}

// Chevron om een kaart open of dicht te klappen (wijst omlaag als ze dicht is, omhoog als ze open is).
export function Uitklapknop({ open, onClick, label }: { open: boolean; onClick: () => void; label: string }) {
  return (
    <button type="button" onClick={onClick} aria-expanded={open} aria-label={`${open ? "Klap dicht" : "Klap open"}: ${label}`}
      className={`flex h-8 w-8 flex-none items-center justify-center rounded-full text-muted ring-1 ring-line hover:text-primary hover:ring-primary ${FOCUS}`}>
      <svg viewBox="0 0 16 16" aria-hidden className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3.5 6l4.5 4.5L12.5 6" />
      </svg>
    </button>
  );
}
