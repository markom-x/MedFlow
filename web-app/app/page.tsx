import Link from "next/link";
import { Activity, BrainCircuit, MessageCircle, ShieldCheck } from "lucide-react";

export default function Home() {
  return (
    <main className="relative min-h-dvh overflow-hidden bg-slate-50 text-slate-800">
      {/* Stripe-style mesh / ambient gradient */}
      <div
        className="pointer-events-none absolute inset-0 -z-10"
        aria-hidden
      >
        <div className="absolute -left-1/4 top-0 h-[520px] w-[520px] rounded-full bg-violet-400/25 blur-3xl md:h-[640px] md:w-[640px]" />
        <div className="absolute -right-1/4 top-24 h-[480px] w-[480px] rounded-full bg-blue-400/20 blur-3xl md:h-[600px] md:w-[600px]" />
        <div className="absolute bottom-0 left-1/3 h-[400px] w-[90%] max-w-3xl -translate-x-1/2 rounded-full bg-cyan-300/15 blur-3xl" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(99,102,241,0.18),transparent)]" />
      </div>

      <header className="sticky top-0 z-30 border-b border-white/40 bg-white/70 shadow-sm shadow-slate-900/[0.03] backdrop-blur-md supports-[backdrop-filter]:bg-white/55">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-3.5 md:px-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2.5 text-lg font-bold tracking-tight text-slate-900 transition-opacity hover:opacity-90"
          >
            <span className="rounded-xl border border-violet-200/60 bg-gradient-to-br from-white to-violet-50 p-2 text-violet-600 shadow-sm shadow-violet-500/10">
              <Activity className="size-4" />
            </span>
            MedFlow
          </Link>
          <div className="flex items-center gap-2 sm:gap-3">
            <Link
              href="/login"
              className="rounded-full px-3 py-2 text-sm font-semibold text-slate-700 transition-colors hover:bg-white/80 hover:text-slate-900 sm:px-4"
            >
              Accedi
            </Link>
            <Link
              href="/login"
              className="rounded-full bg-gradient-to-r from-violet-600 to-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-600/25 transition hover:scale-[1.03] hover:shadow-xl hover:shadow-blue-600/30 active:scale-[0.98] sm:px-5"
            >
              Area Medici
            </Link>
          </div>
        </div>
      </header>

      <section className="relative mx-auto w-full max-w-6xl px-4 pb-12 pt-12 md:px-6 md:pb-20 md:pt-20">
        <div className="relative max-w-4xl">
          <p className="mb-4 inline-flex items-center rounded-full border border-slate-200/80 bg-white/60 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-slate-600 shadow-sm backdrop-blur-sm">
            Triage clinico · WhatsApp · AI
          </p>
          <h1 className="text-[2.5rem] font-bold leading-[1.05] tracking-tight text-slate-900 sm:text-5xl md:text-6xl lg:text-7xl">
            Il triage AI{" "}
            <span className="bg-gradient-to-r from-violet-600 via-blue-600 to-cyan-600 bg-clip-text text-transparent">
              per il medico moderno.
            </span>
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-relaxed text-slate-600 md:text-xl md:leading-relaxed">
            Trasforma i messaggi WhatsApp dei tuoi pazienti in schede cliniche strutturate.
            Risparmia ore di lavoro ogni giorno, in totale sicurezza.
          </p>
          <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:items-center">
            <Link
              href="/login"
              className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-violet-600 to-blue-600 px-8 py-3.5 text-sm font-semibold text-white shadow-xl shadow-blue-600/20 ring-1 ring-white/20 transition hover:scale-[1.02] hover:shadow-2xl hover:shadow-blue-600/25 active:scale-[0.98]"
            >
              Inizia la Prova
            </Link>
            <Link
              href="/#features"
              className="inline-flex items-center justify-center rounded-full border border-slate-200/80 bg-white/70 px-8 py-3.5 text-sm font-semibold text-slate-800 shadow-md shadow-slate-900/[0.04] backdrop-blur-sm transition hover:border-slate-300/90 hover:bg-white hover:shadow-lg active:scale-[0.98]"
            >
              Scopri come funziona
            </Link>
          </div>
        </div>

        {/* Hero preview card — visual depth only, no logic */}
        <div className="mt-14 md:mt-20">
          <div className="relative mx-auto max-w-5xl rounded-3xl border border-white/60 bg-white/50 p-1 shadow-2xl shadow-slate-900/[0.08] backdrop-blur-md md:p-2">
            <div className="overflow-hidden rounded-[1.35rem] border border-slate-100/80 bg-gradient-to-br from-white via-slate-50/80 to-violet-50/30 p-6 md:p-10">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Anteprima flusso
                  </p>
                  <p className="mt-1 text-lg font-semibold text-slate-900 md:text-xl">
                    Messaggio → scheda strutturata
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800 ring-1 ring-emerald-100">
                    Urgenza stimata
                  </span>
                  <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-900 ring-1 ring-amber-100">
                    Red flags
                  </span>
                  <span className="rounded-full bg-violet-50 px-3 py-1 text-xs font-medium text-violet-800 ring-1 ring-violet-100">
                    RLS multi-tenant
                  </span>
                </div>
              </div>
              <div className="mt-6 grid gap-3 rounded-2xl border border-slate-100/90 bg-white/80 p-4 shadow-inner shadow-slate-900/[0.03] md:grid-cols-2 md:p-5">
                <div className="space-y-2 rounded-xl border border-slate-100 bg-white/90 p-4 shadow-sm">
                  <div className="h-2 w-3/4 rounded-full bg-slate-200/80" />
                  <div className="h-2 w-full rounded-full bg-slate-100" />
                  <div className="h-2 w-5/6 rounded-full bg-slate-100" />
                </div>
                <div className="space-y-2 rounded-xl border border-violet-100/80 bg-gradient-to-br from-violet-50/50 to-white p-4 shadow-sm">
                  <div className="h-2 w-2/3 rounded-full bg-violet-200/60" />
                  <div className="h-2 w-full rounded-full bg-slate-100" />
                  <div className="h-2 w-4/5 rounded-full bg-slate-100" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="relative mx-auto w-full max-w-6xl px-4 pb-16 md:px-6 md:pb-24">
        <div className="mb-10 max-w-2xl">
          <h2 className="text-2xl font-bold tracking-tight text-slate-900 md:text-3xl">
            Tutto ciò che serve al tuo studio
          </h2>
          <p className="mt-2 text-slate-600 md:text-lg">
            Strumenti pensati per ridurre il carico amministrativo senza compromettere la cura.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-3 md:gap-6">
          <article className="group rounded-3xl border border-white/50 bg-white/70 p-7 shadow-xl shadow-slate-900/[0.06] backdrop-blur-sm transition hover:-translate-y-0.5 hover:border-slate-200/80 hover:bg-white hover:shadow-2xl hover:shadow-slate-900/[0.08]">
            <div className="mb-5 inline-flex rounded-2xl border border-blue-100/80 bg-gradient-to-br from-blue-50 to-white p-3 text-blue-600 shadow-sm transition group-hover:scale-105">
              <MessageCircle className="size-5" />
            </div>
            <h3 className="text-lg font-semibold text-slate-900">Nessuna App da scaricare</h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              I pazienti ti scrivono sul tuo assistente virtuale WhatsApp. Nessuna frizione,
              massima accessibilita&apos;.
            </p>
          </article>

          <article className="group rounded-3xl border border-white/50 bg-white/70 p-7 shadow-xl shadow-slate-900/[0.06] backdrop-blur-sm transition hover:-translate-y-0.5 hover:border-slate-200/80 hover:bg-white hover:shadow-2xl hover:shadow-slate-900/[0.08]">
            <div className="mb-5 inline-flex rounded-2xl border border-violet-100/80 bg-gradient-to-br from-violet-50 to-white p-3 text-violet-600 shadow-sm transition group-hover:scale-105">
              <BrainCircuit className="size-5" />
            </div>
            <h3 className="text-lg font-semibold text-slate-900">Estrazione Dati AI</h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              Il nostro motore clinico legge i messaggi e genera schede di triage con livelli di
              urgenza e red flags.
            </p>
          </article>

          <article className="group rounded-3xl border border-white/50 bg-white/70 p-7 shadow-xl shadow-slate-900/[0.06] backdrop-blur-sm transition hover:-translate-y-0.5 hover:border-slate-200/80 hover:bg-white hover:shadow-2xl hover:shadow-slate-900/[0.08]">
            <div className="mb-5 inline-flex rounded-2xl border border-emerald-100/80 bg-gradient-to-br from-emerald-50 to-white p-3 text-emerald-600 shadow-sm transition group-hover:scale-105">
              <ShieldCheck className="size-5" />
            </div>
            <h3 className="text-lg font-semibold text-slate-900">Privacy Garantita</h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              Architettura Multi-tenant con Row Level Security. I tuoi dati e quelli dei tuoi
              pazienti sono blindati.
            </p>
          </article>
        </div>
      </section>

      <footer className="relative border-t border-slate-200/60 bg-white/50 backdrop-blur-md">
        <div className="mx-auto w-full max-w-6xl px-4 py-6 text-center text-xs text-slate-500 md:px-6">
          © 2026 MedFlow. Progettato da Marco Carbone.
        </div>
      </footer>
    </main>
  );
}
