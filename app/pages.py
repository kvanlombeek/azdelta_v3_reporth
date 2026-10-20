"""Server-side HTML. Alle dynamische tekst gaat door html.escape."""

from datetime import date, timedelta
from html import escape
from urllib.parse import urlencode

TAILWIND = "https://cdn.tailwindcss.com/3.4.17"

# Huisstijl Reporth, overgenomen uit azdelta_procedure_finder (static/index.html, assets/logo.svg).
LOGO_PATH = (
    "M37.207 0C47.0575 0.000138117 52.6689 4.35833 52.6689 12C52.6689 18.5075 48.9081 22.3881 41.3857 23.1045V23.582"
    "C44.9679 24.5373 46.3414 26.4479 47.834 29.2539L53.625 40H43.2363L37.7441 29.6123C36.1322 26.5078 34.6392 25.4932 "
    "29.9824 25.4932H24.0723V18.7461H37.1465C41.3853 18.7461 43.2959 17.5522 43.2959 13.373C43.2958 9.43285 41.3853 "
    "8.05957 37.1465 8.05957H24.0723V0H37.207ZM19.1191 39.998H5.94238V34.7344L0 28.4307H19.1191V39.998ZM19.1191 "
    "25.7852H5.94238V20.5166L0 14.2119H19.1191V25.7852ZM19.1191 11.5674H5.94238V6.30273L0 0H19.1191V11.5674Z"
)
FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 80'%3E"
    "%3Crect width='80' height='80' rx='16' fill='%2358ffe3'/%3E"
    f"%3Cpath transform='translate(13 20)' fill='%23003545' d='{LOGO_PATH}'/%3E%3C/svg%3E"
)


def _logo(css: str) -> str:
    return (
        f'<svg role="img" aria-label="Reporth" class="{css}" viewBox="0 0 80 80">'
        '<rect width="80" height="80" rx="16" fill="var(--color-accent)"/>'
        f'<path transform="translate(13 20)" fill="var(--color-primary)" d="{LOGO_PATH}"/></svg>'
    )


def _head(title: str) -> str:
    return f"""<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} · Reporth</title>
  <link rel="icon" type="image/svg+xml" href="{FAVICON}">
  <style>
    /* Huisstijl Reporth — hier bijsturen */
    :root {{
      --color-primary: #003545;      /* logo: R */
      --color-accent: #58ffe3;       /* logo: vlak — enkel interactieve elementen */
      --color-accent-ink: #003545;   /* tekst op accent */
      --color-surface: #f9fafb;
      --color-text: #111827;
      --color-text-muted: #6b7280;
      --color-border: #e5e7eb;
      --font-body: ui-sans-serif, system-ui, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
    }}
    body {{ font-family: var(--font-body); -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }}
  </style>
  <script src="{TAILWIND}"></script>
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          colors: {{
            primary: "var(--color-primary)",
            accent: "var(--color-accent)",
            "accent-ink": "var(--color-accent-ink)",
            surface: "var(--color-surface)",
            ink: "var(--color-text)",
            muted: "var(--color-text-muted)",
            line: "var(--color-border)",
          }},
        }},
      }},
    }};
  </script>
</head>"""


def _header(user_name: str | None = None) -> str:
    """Bovenbalk. Met een gebruiker erbij ook de navigatie en afmelden."""
    extra = ""
    if user_name:
        extra = f"""
      <nav class="ml-4 sm:ml-8 text-sm">
        <a href="/" aria-current="page" class="rounded-md font-medium text-primary {FOCUS}">Planning</a>
      </nav>
      <div class="ml-auto flex items-center gap-4 text-sm text-muted">
        <span class="hidden md:inline">{escape(user_name)}</span>
        <a href="/auth/logout" class="rounded-md hover:text-primary {FOCUS}">Afmelden</a>
      </div>"""
    return f"""<header class="border-b border-line bg-white">
    <div class="mx-auto max-w-6xl px-4 sm:px-8 h-16 flex items-center gap-3">
      <a href="/" class="flex items-center gap-3 rounded-lg focus:outline-none focus-visible:ring-4 focus-visible:ring-accent">
        {_logo("h-8 w-8")}
        <span class="text-lg font-semibold tracking-tight text-primary">Reporth</span>
      </a>{extra}
    </div>
  </header>"""


def _layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="nl">
{_head(title)}
<body class="min-h-screen bg-surface text-ink flex flex-col">
  {_header()}
  <div class="flex flex-1 items-center justify-center p-4">
    <main class="w-full max-w-md bg-white rounded-xl shadow-sm ring-1 ring-line p-6 sm:p-8">
      {body}
    </main>
  </div>
</body>
</html>"""


def _button(href: str, label: str) -> str:
    return (
        f'<a href="{escape(href)}" class="inline-block mt-6 rounded-lg bg-primary px-4 py-2 text-sm '
        f'font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-4 focus-visible:ring-accent">{escape(label)}</a>'
    )


DAGEN = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"]
FOCUS = "focus:outline-none focus-visible:ring-4 focus-visible:ring-accent"


def _weeklabel(maandag: date) -> str:
    zondag = maandag + timedelta(days=6)
    if maandag.year != zondag.year:
        return f"{maandag.day} {MAANDEN[maandag.month - 1]} {maandag.year} – {zondag.day} {MAANDEN[zondag.month - 1]} {zondag.year}"
    if maandag.month != zondag.month:
        return f"{maandag.day} {MAANDEN[maandag.month - 1]} – {zondag.day} {MAANDEN[zondag.month - 1]} {zondag.year}"
    return f"{maandag.day} – {zondag.day} {MAANDEN[zondag.month - 1]} {zondag.year}"


def _url(**params) -> str:
    return "/?" + urlencode({k: v for k, v in params.items() if v not in (None, "")})


def _ingreep(r: dict) -> str:
    patient = " · ".join(escape(str(x)) for x in (r["geslacht"], r["geboortedatum"]) if x)
    return f"""<li class="flex flex-col gap-0.5 px-4 py-3 sm:flex-row sm:items-baseline sm:gap-4">
            <span class="w-12 flex-none text-sm tabular-nums text-muted">{escape(r["tijd"])}</span>
            <span class="min-w-0 flex-1">{escape(r["beschrijving"] or "Geen omschrijving")}</span>
            <span class="text-sm tabular-nums text-muted">{patient}</span>
          </li>"""


def _dagpaneel(i: int, dag: dict, zichtbaar: bool) -> str:
    if dag["zalen"]:
        inhoud = "".join(
            f"""<div>
          <h3 class="px-4 pt-4 pb-1 text-xs font-medium uppercase tracking-wide text-muted">{escape(zaal or "Zaal onbekend")}</h3>
          <ul class="divide-y divide-line">{"".join(_ingreep(r) for r in items)}</ul>
        </div>"""
            for zaal, items in dag["zalen"]
        )
    else:
        inhoud = '<p class="px-4 py-10 text-center text-sm text-muted">Geen openstaande ingrepen op deze dag.</p>'
    return (
        f'<section role="tabpanel" data-panel="{i}" aria-label="{DAGEN[i]}" class="rounded-xl border border-line bg-white"'
        f'{"" if zichtbaar else " hidden"}>{inhoud}</section>'
    )


def landing_page(
    user_name: str,
    artsen: list[dict],
    arts_email: str | None,
    maandag: date,
    vandaag: date,
    overzicht: dict | None,
    dag: int,
) -> str:
    """Weekoverzicht van een arts. Zonder gekozen arts (overzicht None) enkel de keuzelijst."""
    arts_naam = next((a["naam"] for a in artsen if (a["email"] or "").lower() == (arts_email or "")), None)
    week = maandag.isoformat()
    vorige, volgende = (maandag + timedelta(days=d) for d in (-7, 7))

    opties = "".join(
        f'<option value="{escape((a["email"] or "").lower())}"{" selected" if (a["email"] or "").lower() == arts_email else ""}>{escape(a["naam"])}</option>'
        for a in artsen
    )
    pijl = f"rounded-md p-1 text-muted hover:text-primary {FOCUS}"
    keuze = f"""<div class="flex justify-end">
      <form method="get" action="/" class="w-full sm:w-64">
        <input type="hidden" name="week" value="{week}">
        <label for="arts" class="sr-only">Arts</label>
        <select id="arts" name="arts" onchange="this.form.submit()"
          class="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm focus:outline-none focus:ring-4 focus:ring-accent">
          {"" if arts_naam else '<option value="" selected disabled>Kies een arts…</option>'}{opties}
        </select>
        <noscript><button class="mt-2 text-sm font-medium text-primary underline">Toon</button></noscript>
      </form>
    </div>"""
    weeknav = f"""<div class="mt-8 flex items-center gap-1 text-sm text-muted">
        {"" if maandag <= vandaag < volgende else f'<a href="{escape(_url(arts=arts_email))}" class="mr-2 rounded-md font-medium text-primary hover:underline {FOCUS}">Deze week</a>'}
        <a href="{escape(_url(week=vorige.isoformat(), arts=arts_email))}" class="{pijl}" aria-label="Vorige week">
          <svg aria-hidden="true" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M12.8 15.3a.75.75 0 0 1-1.06 0l-4.8-4.77a.75.75 0 0 1 0-1.06l4.8-4.77a.75.75 0 1 1 1.06 1.06L8.53 10l4.27 4.24a.75.75 0 0 1 0 1.06Z" clip-rule="evenodd"/></svg>
        </a>
        <span class="tabular-nums">Week {maandag.isocalendar().week} · {_weeklabel(maandag)}</span>
        <a href="{escape(_url(week=volgende.isoformat(), arts=arts_email))}" class="{pijl}" aria-label="Volgende week">
          <svg aria-hidden="true" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M7.2 4.7a.75.75 0 0 1 1.06 0l4.8 4.77a.75.75 0 0 1 0 1.06l-4.8 4.77a.75.75 0 1 1-1.06-1.06L11.47 10 7.2 5.76a.75.75 0 0 1 0-1.06Z" clip-rule="evenodd"/></svg>
        </a>
      </div>"""

    if overzicht is None:
        inhoud = """<h1 class="mt-4 text-2xl font-semibold tracking-tight text-primary">Weekoverzicht</h1>
    <p class="mt-1 text-sm text-muted">Je account is niet gekoppeld aan een arts. Kies rechtsboven een arts om de planning te zien.</p>"""
    else:
        totaal, klaar = overzicht["totaal"], overzicht["gerapporteerd"]
        tabs = ""
        for i, d in enumerate(overzicht["dagen"]):
            n = d["aantal_open"]
            label = f'{DAGEN[i]} {d["datum"].day}' + (" (vandaag)" if d["datum"] == vandaag else "")
            tabs += f"""<a role="tab" href="{escape(_url(week=week, arts=arts_email, dag=i))}" data-tab="{i}" aria-selected="{"true" if i == dag else "false"}"
          aria-label="{label}, {n} open" class="-mb-px flex flex-col items-center gap-0.5 border-b-2 border-transparent px-1 pb-2 text-muted hover:text-primary
                 aria-selected:border-primary aria-selected:text-primary {FOCUS}">
          <span class="text-xs"><span class="sm:hidden">{DAGEN[i][:2]}</span><span class="hidden sm:inline">{DAGEN[i]}</span></span>
          <span class="font-medium tabular-nums{" underline decoration-accent decoration-2 underline-offset-4" if d["datum"] == vandaag else ""}">{d["datum"].day}</span>
          <span class="text-xs tabular-nums{"" if n else " opacity-40"}">{n} open</span>
        </a>"""

        panelen = "".join(_dagpaneel(i, d, i == dag) for i, d in enumerate(overzicht["dagen"]))
        inhoud = f"""<h1 class="mt-4 text-2xl font-semibold tracking-tight text-primary">{escape(arts_naam)}</h1>
    <p class="mt-1 text-sm text-muted"><span class="font-medium tabular-nums text-ink">{klaar}/{totaal}</span> ingrepen deze week reeds getarificeerd</p>

    {weeknav}
    <div role="tablist" aria-label="Openstaande ingrepen per dag" class="mt-3 grid grid-cols-7 border-b border-line">{tabs}</div>
    <div class="mt-4">{panelen}</div>
    <script>
      // Dagen wisselen zonder herladen; de links blijven werken zonder JavaScript.
      document.querySelectorAll('[role=tab]').forEach(tab => tab.addEventListener('click', e => {{
        e.preventDefault();
        document.querySelectorAll('[role=tab]').forEach(t => t.setAttribute('aria-selected', t === tab));
        document.querySelectorAll('[role=tabpanel]').forEach(p => p.hidden = p.dataset.panel !== tab.dataset.tab);
        history.replaceState(null, '', tab.href);
      }}));
    </script>"""

    return f"""<!doctype html>
<html lang="nl">
{_head("Planning")}
<body class="min-h-screen bg-surface text-ink">
  {_header(user_name)}
  <main class="mx-auto max-w-6xl px-4 sm:px-8 py-6">
    {keuze}
    {inhoud}
  </main>
</body>
</html>"""


def error_page(title: str, message: str, detail: str | None = None, button: tuple[str, str] = ("/auth/signin", "Opnieuw aanmelden")) -> str:
    detail_html = (
        f'<pre class="mt-4 whitespace-pre-wrap break-all rounded-lg bg-surface ring-1 ring-line p-3 text-xs">{escape(detail)}</pre>'
        if detail
        else ""
    )
    body = f"""
    <h1 class="text-xl font-semibold text-red-700">{escape(title)}</h1>
    <p class="mt-3 text-sm">{escape(message)}</p>
    {detail_html}
    {_button(*button)}"""
    return _layout(title, body)


def logged_out_page() -> str:
    body = """
    <h1 class="text-xl font-semibold">Je bent afgemeld</h1>
    <p class="mt-3 text-sm text-muted">Je sessie bij Reporth is beëindigd.</p>
    """ + _button("/auth/signin", "Opnieuw aanmelden")
    return _layout("Afgemeld", body)


# Officieel Microsoft-logo (vier vierkanten), zoals voorgeschreven voor "Sign in with Microsoft".
MICROSOFT_LOGO = """<svg aria-hidden="true" width="20" height="20" viewBox="0 0 21 21">
      <rect x="1" y="1" width="9" height="9" fill="#f25022"/><rect x="11" y="1" width="9" height="9" fill="#7fba00"/>
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef"/><rect x="11" y="11" width="9" height="9" fill="#ffb900"/>
    </svg>"""


def login_page() -> str:
    # Donker, zoals de publieke website van Reporth.
    return f"""<!doctype html>
<html lang="nl">
{_head("Aanmelden")}
<body class="min-h-screen bg-black text-white flex flex-col items-center justify-center p-4">
  <main class="w-full max-w-sm">
    <div class="flex flex-col items-center text-center mb-8">
      {_logo("h-20 w-20")}
      <h1 class="mt-6 text-3xl font-semibold tracking-tight">Reporth</h1>
      <p class="mt-2 text-sm text-white/60">Snel en efficiënt verslaggeven per procedure.</p>
    </div>

    <div class="rounded-2xl bg-primary p-6 sm:p-8 ring-1 ring-accent/40 shadow-[0_0_40px_-20px_var(--color-accent)]">
      <h2 class="text-lg font-semibold">Aanmelden</h2>
      <p class="mt-1 text-sm text-white/75">Gebruik het account van je ziekenhuis.</p>

      <a href="/auth/login"
         class="mt-6 flex w-full items-center justify-center gap-3 rounded-full bg-white px-4 py-2.5
                text-sm font-semibold text-ink transition hover:bg-white/90
                focus:outline-none focus-visible:ring-4 focus-visible:ring-accent">
        {MICROSOFT_LOGO}
        Aanmelden met Microsoft
      </a>

      <div class="mt-6 flex items-start gap-2 text-xs text-white/65">
        <svg aria-hidden="true" class="mt-0.5 h-4 w-4 flex-none" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M10 1a4.5 4.5 0 0 0-4.5 4.5V9H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2h-.5V5.5A4.5 4.5 0 0 0 10 1Zm3 8V5.5a3 3 0 1 0-6 0V9h6Z" clip-rule="evenodd"/>
        </svg>
        <span>Je meldt je aan via Microsoft. Reporth krijgt je wachtwoord nooit te zien.</span>
      </div>
    </div>

    <p class="mt-6 text-center text-xs text-white/50">
      Gastaccount?
      <a href="/auth/login?via=reporth" class="font-medium text-accent hover:underline focus:outline-none focus-visible:underline">Aanmelden via Reporth</a>
    </p>
  </main>
</body>
</html>"""
