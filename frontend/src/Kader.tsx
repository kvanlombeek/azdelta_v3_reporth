import { useEffect, useState, type ReactNode } from "react";

const LOGO_PATH =
  "M37.207 0C47.0575 0.000138117 52.6689 4.35833 52.6689 12C52.6689 18.5075 48.9081 22.3881 41.3857 23.1045V23.582C44.9679 24.5373 46.3414 26.4479 47.834 29.2539L53.625 40H43.2363L37.7441 29.6123C36.1322 26.5078 34.6392 25.4932 29.9824 25.4932H24.0723V18.7461H37.1465C41.3853 18.7461 43.2959 17.5522 43.2959 13.373C43.2958 9.43285 41.3853 8.05957 37.1465 8.05957H24.0723V0H37.207ZM19.1191 39.998H5.94238V34.7344L0 28.4307H19.1191V39.998ZM19.1191 25.7852H5.94238V20.5166L0 14.2119H19.1191V25.7852ZM19.1191 11.5674H5.94238V6.30273L0 0H19.1191V11.5674Z";

export function Logo({ className }: { className: string }) {
  return (
    <svg role="img" aria-label="Reporth" className={className} viewBox="0 0 80 80">
      <rect width="80" height="80" rx="16" fill="var(--color-accent)" />
      <path transform="translate(13 20)" fill="var(--color-primary)" d={LOGO_PATH} />
    </svg>
  );
}

const FOCUS = "focus:outline-none focus-visible:ring-4 focus-visible:ring-accent";

export function Kader({ children, breed, kaal }: { children: ReactNode; breed?: boolean; kaal?: boolean }) {
  const [naam, setNaam] = useState<string | null>(null);
  useEffect(() => {
    if (kaal) return;
    fetch("/auth/me").then((r) => (r.ok ? r.json() : null)).then((u) => setNaam(u?.name ?? null)).catch(() => {});
  }, [kaal]);
  return (
    <>
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:px-8">
          <a href="/" className={`flex items-center gap-3 rounded-lg ${FOCUS}`}>
            <Logo className="h-8 w-8" />
            <span className="text-lg font-semibold tracking-tight text-primary">Reporth</span>
          </a>
          {!kaal && <nav className="ml-4 flex gap-5 text-sm sm:ml-8">
            {[["/", "Planning"], ["/ingrepen", "Ingrepen"]].map(([pad, naam]) => {
              const actief = pad === "/" ? !window.location.pathname.startsWith("/ingrepen") : window.location.pathname.startsWith(pad);
              return (
                <a key={pad} href={pad} aria-current={actief ? "page" : undefined}
                  className={`py-1 ${actief ? "border-b-2 border-primary font-medium text-primary" : "text-muted hover:text-primary"} ${FOCUS}`}>
                  {naam}
                </a>
              );
            })}
          </nav>}
          {!kaal && <div className="ml-auto flex items-center gap-4 text-sm text-muted">
            {naam && <span className="hidden md:inline">{naam}</span>}
            <a href="/auth/logout" className={`rounded-md hover:text-primary ${FOCUS}`}>Afmelden</a>
          </div>}
        </div>
      </header>
      <main className={`mx-auto px-4 py-8 sm:px-8 ${breed ? "max-w-6xl" : "max-w-5xl"}`}>{children}</main>
    </>
  );
}
