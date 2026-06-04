import Link from "next/link";
import { Activity, BrainCircuit, MessageCircle, ShieldCheck } from "lucide-react";

import { FlowPreview } from "@/components/FlowPreview";

export default function Home() {
  return (
    <main className="relative min-h-dvh overflow-x-hidden text-slate-800">
      {/* Full-bleed Stripe-style mesh — independent of content width */}
      <div
        className="pointer-events-none absolute inset-0 -z-10 w-full min-h-screen overflow-hidden"
        aria-hidden
      >
        <div className="absolute inset-0 bg-gradient-to-b from-white via-slate-50 to-slate-100/90" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_120%_80%_at_50%_-20%,rgba(255,255,255,0.75),transparent_55%)]" />

        <div className="absolute -left-[28%] -top-[22%] h-[800px] w-[800px] rounded-full bg-violet-300 blur-[120px] mix-blend-multiply opacity-50 animate-hero-mesh-a" />
        <div className="absolute -right-[26%] -top-[18%] h-[800px] w-[800px] rounded-full bg-blue-300 blur-[120px] mix-blend-multiply opacity-50 animate-hero-mesh-b" />
        <div className="absolute -bottom-[32%] left-1/2 h-[800px] w-[800px] -translate-x-1/2 rounded-full bg-cyan-300 blur-[120px] mix-blend-multiply opacity-50 animate-hero-mesh-c" />
        <div className="absolute left-[8%] top-[38%] h-[720px] w-[720px] rounded-full bg-fuchsia-200 blur-[120px] mix-blend-multiply opacity-45 animate-hero-mesh-b [animation-delay:-9s]" />
      </div>

      <header className="sticky top-0 z-30 border-b border-white/40 bg-white/70 shadow-sm shadow-slate-900/[0.03] backdrop-blur-md supports-[backdrop-filter]:bg-white/55">
        <div className="relative z-10 mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-3.5 md:px-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2.5 text-lg font-bold tracking-tight text-slate-900 transition-opacity hover:opacity-90"
          >
            <span className="rounded-xl border border-violet-200/60 bg-gradient-to-br from-white to-violet-50 p-2 text-violet-600 shadow-sm shadow-violet-500/10">
              <Activity className="size-4" />
            </span>
            MedFlow
          </Link>
          <Link
            href="/login"
            className="rounded-full bg-gradient-to-r from-violet-600 to-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-600/25 transition hover:scale-[1.03] hover:shadow-xl hover:shadow-blue-600/30 active:scale-[0.98] sm:px-5"
          >
            Doctor area
          </Link>
        </div>
      </header>

      <div className="relative z-10 mx-auto w-full max-w-7xl px-4 md:px-6">
        <section className="pb-12 pt-12 md:pb-20 md:pt-20">
          <div className="relative max-w-4xl">
            <p className="mb-4 inline-flex items-center rounded-full border border-slate-200/80 bg-white/60 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-slate-600 shadow-sm backdrop-blur-sm">
              Patient record · WhatsApp · AI
            </p>
            <h1 className="text-[2.5rem] font-bold leading-[1.05] tracking-tight text-slate-900 sm:text-5xl md:text-6xl lg:text-7xl">
              An intelligent patient record,{" "}
              <span className="bg-gradient-to-r from-violet-600 via-blue-600 to-cyan-600 bg-clip-text text-transparent">
                built over WhatsApp.
              </span>
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-relaxed text-slate-600 md:text-xl md:leading-relaxed">
              Patients just text their doctor on WhatsApp. No app, no sign-up, nothing
              to learn. The AI turns every message, voice note and report into a living
              clinical record — one the doctor can simply ask.
            </p>
            <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:items-center">
              <Link
                href="/login"
                className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-violet-600 to-blue-600 px-8 py-3.5 text-sm font-semibold text-white shadow-xl shadow-blue-600/20 ring-1 ring-white/20 transition hover:scale-[1.02] hover:shadow-2xl hover:shadow-blue-600/25 active:scale-[0.98]"
              >
                Start the demo
              </Link>
              <Link
                href="/#features"
                className="inline-flex items-center justify-center rounded-full border border-slate-200/80 bg-white/70 px-8 py-3.5 text-sm font-semibold text-slate-800 shadow-md shadow-slate-900/[0.04] backdrop-blur-sm transition hover:border-slate-300/90 hover:bg-white hover:shadow-lg active:scale-[0.98]"
              >
                See how it works
              </Link>
            </div>
          </div>

          <FlowPreview />
        </section>

        <section id="features" className="pb-16 md:pb-24">
          <div className="mb-10 max-w-2xl">
            <h2 className="text-2xl font-bold tracking-tight text-slate-900 md:text-3xl">
              Everything your practice needs
            </h2>
            <p className="mt-2 text-slate-600 md:text-lg">
              Tools designed to cut the administrative load without compromising care.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-3 md:gap-6">
            <article className="group rounded-3xl border border-white/50 bg-white/70 p-7 shadow-xl shadow-slate-900/[0.06] backdrop-blur-sm transition hover:-translate-y-0.5 hover:border-slate-200/80 hover:bg-white hover:shadow-2xl hover:shadow-slate-900/[0.08]">
              <div className="mb-5 inline-flex rounded-2xl border border-blue-100/80 bg-gradient-to-br from-blue-50 to-white p-3 text-blue-600 shadow-sm transition group-hover:scale-105">
                <MessageCircle className="size-5" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">Just WhatsApp, no app</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                Patients use the chat they already know. No download, no account —
                accessible even to elderly and less tech-savvy patients.
              </p>
            </article>

            <article className="group rounded-3xl border border-white/50 bg-white/70 p-7 shadow-xl shadow-slate-900/[0.06] backdrop-blur-sm transition hover:-translate-y-0.5 hover:border-slate-200/80 hover:bg-white hover:shadow-2xl hover:shadow-slate-900/[0.08]">
              <div className="mb-5 inline-flex rounded-2xl border border-violet-100/80 bg-gradient-to-br from-violet-50 to-white p-3 text-violet-600 shadow-sm transition group-hover:scale-105">
                <BrainCircuit className="size-5" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">Ask the record</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                The AI reads messages, voice notes and report photos or PDFs, then lets the
                doctor just ask the patient&apos;s record a question.
              </p>
            </article>

            <article className="group rounded-3xl border border-white/50 bg-white/70 p-7 shadow-xl shadow-slate-900/[0.06] backdrop-blur-sm transition hover:-translate-y-0.5 hover:border-slate-200/80 hover:bg-white hover:shadow-2xl hover:shadow-slate-900/[0.08]">
              <div className="mb-5 inline-flex rounded-2xl border border-emerald-100/80 bg-gradient-to-br from-emerald-50 to-white p-3 text-emerald-600 shadow-sm transition group-hover:scale-105">
                <ShieldCheck className="size-5" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">Privacy guaranteed</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                Multi-tenant architecture with Row Level Security. Your data and your
                patients&apos; data stay locked down.
              </p>
            </article>
          </div>
        </section>
      </div>

      <footer className="relative z-10 border-t border-slate-200/60 bg-white/50 backdrop-blur-md">
        <div className="mx-auto w-full max-w-7xl px-4 py-6 text-center text-xs text-slate-500 md:px-6">
          © 2026 MedFlow. Designed by Marco Carbone.
        </div>
      </footer>
    </main>
  );
}
