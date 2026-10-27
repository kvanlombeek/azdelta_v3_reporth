import { useEffect } from "react";
import { Kader, Logo } from "./Kader";

const FOCUS = "focus:outline-none focus-visible:ring-4 focus-visible:ring-accent";

// Foutcodes die Python meegeeft bij /fout?reden=... (zie app/auth.py). Enkel codes, nooit details.
const FOUTEN: Record<string, string> = {
  organisatie: "Je organisatie heeft (nog) geen toegang tot Reporth.",
  lijst: "Je account staat niet op de lijst van toegelaten gebruikers.",
  microsoft: "Microsoft meldt een fout bij het aanmelden.",
  token: "Het aanmeldtoken is ongeldig.",
  login: "De login kon niet worden voltooid.",
};

const knop = `inline-block rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90 ${FOCUS}`;

export function Aanmelden() {
  // Al aangemeld? Dan meteen naar de planning.
  useEffect(() => {
    fetch("/auth/me").then((r) => r.ok && (window.location.href = "/")).catch(() => {});
  }, []);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-black p-4 text-white">
      <main className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo className="h-20 w-20" />
          <h1 className="mt-6 text-3xl font-semibold tracking-tight">Reporth</h1>
          <p className="mt-2 text-sm text-white/60">Snel en efficiënt verslaggeven per procedure.</p>
        </div>
        <div className="rounded-2xl bg-primary p-6 ring-1 ring-accent/40 sm:p-8">
          <h2 className="text-lg font-semibold">Aanmelden</h2>
          <p className="mt-1 text-sm text-white/75">Gebruik het account van je ziekenhuis.</p>
          <a
            href="/auth/login"
            className={`mt-6 flex w-full items-center justify-center gap-3 rounded-full bg-white px-4 py-2.5 text-sm font-semibold text-ink transition hover:bg-white/90 ${FOCUS}`}
          >
            <svg aria-hidden="true" width="20" height="20" viewBox="0 0 21 21">
              <rect x="1" y="1" width="9" height="9" fill="#f25022" /><rect x="11" y="1" width="9" height="9" fill="#7fba00" />
              <rect x="1" y="11" width="9" height="9" fill="#00a4ef" /><rect x="11" y="11" width="9" height="9" fill="#ffb900" />
            </svg>
            Aanmelden met Microsoft
          </a>
          <p className="mt-6 text-xs text-white/65">Je meldt je aan via Microsoft. Reporth krijgt je wachtwoord nooit te zien.</p>
        </div>
        <p className="mt-6 text-center text-xs text-white/50">
          Gastaccount?{" "}
          <a href="/auth/login?via=reporth" className="font-medium text-accent hover:underline focus:outline-none focus-visible:underline">
            Aanmelden via Reporth
          </a>
        </p>
      </main>
    </div>
  );
}

export function Afgemeld() {
  return (
    <Kader kaal>
      <div className="mx-auto max-w-md rounded-xl bg-white p-8 shadow-sm ring-1 ring-line">
        <h1 className="text-xl font-semibold">Je bent afgemeld</h1>
        <p className="mt-3 text-sm text-muted">Je sessie bij Reporth is beëindigd.</p>
        <a href="/aanmelden" className={`mt-6 ${knop}`}>Opnieuw aanmelden</a>
      </div>
    </Kader>
  );
}

export function Fout() {
  const params = new URLSearchParams(window.location.search);
  const reden = params.get("reden") ?? "";
  const code = params.get("code");
  return (
    <Kader kaal>
      <div className="mx-auto max-w-md rounded-xl bg-white p-8 shadow-sm ring-1 ring-line">
        <h1 className="text-xl font-semibold text-red-700">Aanmelden mislukt</h1>
        <p className="mt-3 text-sm">{FOUTEN[reden] ?? "Er ging iets mis bij het aanmelden."}</p>
        {code && <p className="mt-2 text-xs text-muted">Code: {code}</p>}
        <a href="/aanmelden" className={`mt-6 ${knop}`}>Opnieuw aanmelden</a>
      </div>
    </Kader>
  );
}
