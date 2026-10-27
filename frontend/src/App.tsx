import { useEffect, useState } from "react";
import { ApiFout, haalBestaandeTarificatie, haalNieuweTarificatie } from "./api";
import { Afgemeld, Aanmelden, Fout } from "./Aanmelding";
import { Ingrepen } from "./Ingrepen";
import { Kader } from "./Kader";
import { Planning } from "./Planning";
import { TarificatieFormulier } from "./TarificatieFormulier";
import type { TarificatieAntwoord } from "./types";

type Toestand =
  | { soort: "laden" }
  | { soort: "fout"; bericht: string }
  | { soort: "klaar"; data: TarificatieAntwoord };

// /tarificatie/nieuw/{patient_id}/{hash} (vanuit de planning) en /tarificatie/ingreep/{ingreep_id} (bestaande ingreep).
// Blanco volgt later.
type Route = { soort: "nieuw"; patientId: string; hash: string } | { soort: "ingreep"; id: number };
function routeVanPad(pad: string): Route | null {
  const nieuw = pad.match(/^\/tarificatie\/nieuw\/([^/]+)\/([0-9a-f]{12})\/?$/);
  if (nieuw) return { soort: "nieuw", patientId: decodeURIComponent(nieuw[1]), hash: nieuw[2] };
  const bestaand = pad.match(/^\/tarificatie\/ingreep\/(\d{1,10})\/?$/);
  return bestaand ? { soort: "ingreep", id: Number(bestaand[1]) } : null;
}

export default function App() {
  const pad = window.location.pathname;
  if (pad === "/") return <Planning />;
  if (pad === "/ingrepen") return <Ingrepen />;
  if (pad === "/aanmelden") return <Aanmelden />;
  if (pad === "/afgemeld") return <Afgemeld />;
  if (pad === "/fout") return <Fout />;
  return <Tarificatie />;
}

function Tarificatie() {
  const route = routeVanPad(window.location.pathname);
  const sleutel = route ? (route.soort === "nieuw" ? `${route.patientId}/${route.hash}` : String(route.id)) : "";
  const [toestand, setToestand] = useState<Toestand>({ soort: "laden" });
  const [poging, setPoging] = useState(0);

  useEffect(() => {
    if (!route) return;
    let geannuleerd = false;
    setToestand({ soort: "laden" });
    (route.soort === "nieuw" ? haalNieuweTarificatie(route.patientId, route.hash) : haalBestaandeTarificatie(route.id))
      .then((data) => !geannuleerd && setToestand({ soort: "klaar", data }))
      .catch((e: unknown) => {
        if (geannuleerd) return;
        setToestand({ soort: "fout", bericht: e instanceof ApiFout ? e.message : "Er ging iets mis." });
      });
    return () => {
      geannuleerd = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sleutel, poging]);

  if (!route) {
    return (
      <Kader>
        <Melding titel="Pagina niet gevonden" tekst="Open een ingreep via de planning." />
      </Kader>
    );
  }
  return (
    <Kader>
      {toestand.soort === "laden" && <p className="py-20 text-center text-sm text-muted">Ingreep laden…</p>}
      {toestand.soort === "fout" && (
        <Melding titel="Tarificatie niet beschikbaar" tekst={toestand.bericht} opnieuw={() => setPoging((p) => p + 1)} />
      )}
      {toestand.soort === "klaar" && <TarificatieFormulier antwoord={toestand.data} />}
    </Kader>
  );
}

function Melding({ titel, tekst, opnieuw }: { titel: string; tekst: string; opnieuw?: () => void }) {
  return (
    <div className="mx-auto max-w-md rounded-xl bg-white p-8 shadow-sm ring-1 ring-line">
      <h1 className="text-lg font-semibold text-primary">{titel}</h1>
      <p className="mt-2 text-sm text-muted">{tekst}</p>
      <div className="mt-6 flex gap-3">
        <a href="/" className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-4 focus-visible:ring-accent">
          Terug naar planning
        </a>
        {opnieuw && (
          <button onClick={opnieuw} className="rounded-lg px-4 py-2 text-sm font-medium text-primary ring-1 ring-line hover:bg-surface focus:outline-none focus-visible:ring-4 focus-visible:ring-accent">
            Opnieuw proberen
          </button>
        )}
      </div>
    </div>
  );
}
