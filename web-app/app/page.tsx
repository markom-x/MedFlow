import Link from "next/link";
import { Brain, MessageSquare, ShieldCheck } from "lucide-react";

export default function Home() {
  return (
    <main className="min-h-dvh bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-3 md:px-6">
          <Link href="/" className="text-lg font-semibold tracking-tight text-blue-700">
            MedFlow
          </Link>
          <Link
            href="/login"
            className="rounded-lg border border-blue-200 bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
          >
            Accedi
          </Link>
        </div>
      </header>

      <section className="mx-auto w-full max-w-6xl px-4 pb-10 pt-12 md:px-6 md:pb-16 md:pt-20">
        <div className="max-w-3xl">
          <p className="inline-flex items-center rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-cyan-700">
            Startup MedTech
          </p>
          <h1 className="mt-4 text-3xl font-bold leading-tight tracking-tight text-slate-900 md:text-5xl">
            Il tuo assistente di Triage intelligente su WhatsApp
          </h1>
          <p className="mt-4 text-base leading-relaxed text-slate-600 md:text-lg">
            MedFlow usa l&apos;IA per leggere i messaggi dei pazienti, estrarre i dati clinici e
            organizzare le priorita&apos; in una dashboard chiara. Meno caos operativo, piu&apos;
            tempo clinico per il medico.
          </p>
          <div className="mt-6">
            <a
              href="#features"
              className="inline-flex rounded-lg bg-cyan-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-cyan-700"
            >
              Scopri come funziona
            </a>
          </div>
        </div>
      </section>

      <section id="features" className="mx-auto w-full max-w-6xl px-4 pb-14 md:px-6 md:pb-20">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3 md:gap-6">
          <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-3 inline-flex rounded-xl bg-blue-50 p-2 text-blue-700">
              <MessageSquare className="size-5" />
            </div>
            <h2 className="text-lg font-semibold text-slate-900">Integrazione WhatsApp</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              Ricevi e centralizza i messaggi paziente in tempo reale, senza cambiare le abitudini
              di comunicazione dello studio.
            </p>
          </article>

          <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-3 inline-flex rounded-xl bg-cyan-50 p-2 text-cyan-700">
              <Brain className="size-5" />
            </div>
            <h2 className="text-lg font-semibold text-slate-900">Estrazione Dati Clinici</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              L&apos;IA sintetizza sintomi, red flags e livello di urgenza in JSON strutturato per
              accelerare il triage quotidiano.
            </p>
          </article>

          <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-3 inline-flex rounded-xl bg-emerald-50 p-2 text-emerald-700">
              <ShieldCheck className="size-5" />
            </div>
            <h2 className="text-lg font-semibold text-slate-900">Privacy e RLS Sicura</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              Accesso protetto, policy RLS e separazione dei ruoli per mantenere i dati sanitari
              al sicuro in ogni passaggio.
            </p>
          </article>
        </div>
      </section>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-4 text-xs text-slate-500 md:px-6">
          <p>© {new Date().getFullYear()} MedFlow</p>
          <p>Triage intelligente per Medicina Generale</p>
        </div>
      </footer>
    </main>
  );
}
