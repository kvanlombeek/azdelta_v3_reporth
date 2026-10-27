import { useState } from "react";
import { Procedures } from "./Procedures";
import { Tarificatie } from "./Tarificatie";
import { INPUT, Keuzerondjes, Uitklapknop, Veld } from "./velden";
import type { TarificatieAntwoord } from "./types";
import { foutmelding, nieuweKeuze, type Gekozen, type Zijde } from "./zijden";

type Hulp = "geen" | "assistent" | "collega";

type Waarden = {
  datum: string;
  campus_code: string;
  opname_id: string;
  ambulant_gehospitaliseerd: string;
  arts_email: string;
  hulp: Hulp;
  hulp_id: string; // internnummer van de assistent, of e-mail van de collega-arts
  regio: string;
  lateraliteit: string;
};
type Fouten = Partial<Record<keyof Waarden, string>>;

export function valideer(w: Waarden): Fouten {
  const f: Fouten = {};
  if (!/^\d{4}-\d{2}-\d{2}$/.test(w.datum)) f.datum = "Geef een geldige datum in.";
  if (!w.campus_code) f.campus_code = "Kies een campus.";
  if (!/^\d{8,9}$/.test(w.opname_id)) f.opname_id = "Het opnamenummer bestaat uit 8 of 9 cijfers.";
  if (!w.ambulant_gehospitaliseerd) f.ambulant_gehospitaliseerd = "Kies ambulant of gehospitaliseerd.";
  if (!w.arts_email) f.arts_email = "Kies de uitvoerende arts.";
  if (w.hulp !== "geen" && !w.hulp_id) f.hulp_id = w.hulp === "assistent" ? "Kies een assistent." : "Kies een collega arts.";
  if (!w.regio) f.regio = "Kies een lichaamsregio.";
  if (!w.lateraliteit) f.lateraliteit = "Kies de lateraliteit.";
  return f;
}

// Beginwaarden komen uit de planning (of straks een bestaande ingreep, of blanco): het formulier
// kijkt enkel naar `voorinvulling` en weet niet waar die vandaan komt.
// De opgeslagen (zijde, straal)-rijen terug naar de keuze zoals de arts ze maakte.
function gekozenUitOpslag({ procedure, selecties }: NonNullable<TarificatieAntwoord["opgeslagen"]>["procedures"][number]): Gekozen {
  const g = nieuweKeuze(procedure);
  g.zijden = [...new Set(selecties.map((s) => s.zijde))] as Zijde[];
  for (const s of selecties) if (s.straal) g.stralen[s.zijde].push(s.straal);
  return g;
}

export function TarificatieFormulier({ antwoord }: { antwoord: TarificatieAntwoord }) {
  const { voorinvulling: v, opties, opgeslagen } = antwoord;
  // Een bestaande ingreep opent met alles ingevuld en ingeklapt, de tarificatie zoals opgeslagen.
  const assistent = opties.assistenten.some((a) => a.internnummer === v.assistent) ? (v.assistent ?? "") : "";
  const [w, setW] = useState<Waarden>({
    datum: v.datum ?? "",
    campus_code: v.campus_code ?? "",
    opname_id: v.opname_id ?? "",
    ambulant_gehospitaliseerd: v.ambulant_gehospitaliseerd ?? "",
    arts_email: v.arts_email ?? "",
    hulp: assistent ? "assistent" : "geen",
    hulp_id: assistent,
    regio: v.regio ?? "",
    lateraliteit: v.lateraliteit ?? "",
  });
  const [fouten, setFouten] = useState<Fouten>({});
  const [kaart1Open, setKaart1Open] = useState(!opgeslagen);
  const [kaart2, setKaart2] = useState(!!opgeslagen); // verschijnt na "Volgende" en blijft daarna staan
  const [kaart2Open, setKaart2Open] = useState(false);
  const [kaart3, setKaart3] = useState(!!opgeslagen);
  const [gekozen, setGekozen] = useState<Gekozen[]>(() => (opgeslagen?.procedures ?? []).map(gekozenUitOpslag));
  const compleet = gekozen.every((g) => !foutmelding(g, w.lateraliteit)); // alle zijden en stralen gekozen

  const zet = <K extends keyof Waarden>(k: K, waarde: Waarden[K]) => setW((oud) => ({ ...oud, [k]: waarde }));

  const verstuur = (e: React.FormEvent) => {
    e.preventDefault();
    const f = valideer(w);
    setFouten(f);
    if (Object.keys(f).length) {
      document.querySelector<HTMLElement>("[role=alert]")?.scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }
    setKaart1Open(false);
    if (!kaart2) {
      setKaart2(true);
      setKaart2Open(true);
    }
  };

  const collegas = opties.artsen.filter((a) => a.email !== w.arts_email);
  const naam = (lijst: { email: string; naam: string }[], email: string) => lijst.find((a) => a.email === email)?.naam;
  const samenvatting = [
    w.datum.split("-").reverse().join("/"),
    opties.campussen.find((c) => c.campus_code === w.campus_code)?.campus_naam,
    w.ambulant_gehospitaliseerd,
    naam(opties.artsen, w.arts_email),
    w.regio,
    opties.lateraliteiten.find((l) => l.code === w.lateraliteit)?.naam,
  ].filter(Boolean).join(" · ");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{opgeslagen ? "Ingreep: tarificatie" : "Nieuwe ingreep: tarificatie"}</h1>
        <p className="mt-1 text-sm text-muted" aria-label="Patiënt">
          Patiënt {antwoord.patient_id}
          {[antwoord.patient.geslacht, antwoord.patient.leeftijd != null && `${antwoord.patient.leeftijd} jaar`]
            .filter(Boolean).map((x) => ` · ${x}`).join("")}
        </p>
      </div>

      <form onSubmit={verstuur} noValidate className="rounded-xl border border-line bg-white">
        <div className="flex items-start gap-3 p-5 sm:px-6">
          {kaart2 && !kaart1Open && (
            <span aria-hidden className="mt-0.5 flex h-6 w-6 flex-none items-center justify-center rounded-full bg-accent text-accent-ink">✓</span>
          )}
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-semibold tracking-tight">1. Algemene gegevens</h2>
            <p className="mt-0.5 text-sm text-muted">
              {kaart1Open ? "Deze gegevens komen uit de planning. Pas aan wat niet klopt." : samenvatting}
            </p>
          </div>
          {kaart2 && <Uitklapknop open={kaart1Open} onClick={() => setKaart1Open(!kaart1Open)} label="algemene gegevens" />}
        </div>

        {kaart1Open && (
          <div className="space-y-6 border-t border-line p-5 sm:p-6">
        <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-5">
              <Veld label="Datum" verplicht htmlFor="datum" fout={fouten.datum}>
                <input id="datum" type="date" value={w.datum} onChange={(e) => zet("datum", e.target.value)} className={INPUT} aria-invalid={!!fouten.datum} />
              </Veld>
              <Veld label="Opnamenummer" verplicht htmlFor="opname" hint="Inschrijvingsnummer uit HIX: 8 of 9 cijfers." fout={fouten.opname_id}>
                <input id="opname" inputMode="numeric" value={w.opname_id} onChange={(e) => zet("opname_id", e.target.value.trim())} className={INPUT} aria-invalid={!!fouten.opname_id} />
              </Veld>
            </div>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <Keuzerondjes
              legende="Campus" verplicht naam="campus" waarde={w.campus_code} fout={fouten.campus_code}
              opties={opties.campussen.map((c) => ({ waarde: c.campus_code, label: c.campus_naam }))}
              onChange={(x) => zet("campus_code", x)}
            />
            <Keuzerondjes
              legende="Ambulant / gehospitaliseerd" verplicht naam="verblijf" waarde={w.ambulant_gehospitaliseerd} fout={fouten.ambulant_gehospitaliseerd}
              opties={opties.ambulant_gehospitaliseerd.map((x) => ({ waarde: x, label: x }))}
              onChange={(x) => zet("ambulant_gehospitaliseerd", x)}
            />
          </div>

          <hr className="border-line" />

          <div className="grid gap-5 sm:grid-cols-2">
            <Veld label="Uitvoerende arts" verplicht htmlFor="arts" fout={fouten.arts_email}>
              <select id="arts" value={w.arts_email} onChange={(e) => zet("arts_email", e.target.value)} className={INPUT} aria-invalid={!!fouten.arts_email}>
                <option value="">Kies een arts…</option>
                {opties.artsen.map((a) => <option key={a.email} value={a.email}>{a.naam}</option>)}
              </select>
            </Veld>
            <div className="space-y-2">
              <Keuzerondjes
                inline legende="Assistent of collega arts" naam="hulp" waarde={w.hulp}
                opties={[{ waarde: "geen", label: "Geen" }, { waarde: "assistent", label: "Assistent" }, { waarde: "collega", label: "Collega arts" }]}
                onChange={(x) => { setW((o) => ({ ...o, hulp: x as Hulp, hulp_id: "" })); }}
              />
              {w.hulp !== "geen" && (
                <Veld label={w.hulp === "assistent" ? "Assistent" : "Collega arts"} verplicht htmlFor="hulp_id" fout={fouten.hulp_id}>
                  <select id="hulp_id" value={w.hulp_id} onChange={(e) => zet("hulp_id", e.target.value)} className={INPUT} aria-invalid={!!fouten.hulp_id}>
                    <option value="">Kies…</option>
                    {w.hulp === "assistent"
                      ? opties.assistenten.map((a) => <option key={a.internnummer} value={a.internnummer}>{a.naam}</option>)
                      : collegas.map((a) => <option key={a.email} value={a.email}>{a.naam}</option>)}
                  </select>
                </Veld>
              )}
            </div>
          </div>

          <hr className="border-line" />

          <div className="grid gap-5 sm:grid-cols-2">
            <Keuzerondjes
              legende="Lichaamsregio" verplicht naam="regio" waarde={w.regio} fout={fouten.regio}
              opties={opties.regios.map((r) => ({ waarde: r, label: r }))}
              onChange={(x) => zet("regio", x)}
            />
            <Keuzerondjes
              legende="Lateraliteit" verplicht naam="lateraliteit" waarde={w.lateraliteit} fout={fouten.lateraliteit}
              opties={opties.lateraliteiten.map((l) => ({ waarde: l.code, label: l.naam }))}
              onChange={(x) => zet("lateraliteit", x)}
            />
          </div>

            <div className="flex flex-wrap items-center gap-4">
              <button type="submit" className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-accent-ink hover:brightness-95 focus:outline-none focus-visible:ring-4 focus-visible:ring-primary/30">
                Volgende: procedures
              </button>
              <a href="/" className="text-sm text-muted hover:text-primary">Annuleren</a>
            </div>
          </div>
        )}
      </form>

      {kaart2 && (
        <Procedures
          startzoek={v.beschrijving} gematcht={antwoord.gematchte_procedures} regio={w.regio} verblijf={w.ambulant_gehospitaliseerd} lateraliteit={w.lateraliteit}
          gekozen={gekozen} setGekozen={setGekozen}
          open={kaart2Open} klaar={kaart3} onToggle={() => setKaart2Open(!kaart2Open)}
          onVolgende={() => { setKaart2Open(false); setKaart3(true); }}
        />
      )}
      {kaart3 && compleet && (
        <Tarificatie gekozen={gekozen} verblijf={w.ambulant_gehospitaliseerd} regio={w.regio} kop={w.lateraliteit} opgeslagen={opgeslagen} />
      )}
    </div>
  );
}
