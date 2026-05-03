"use client";

import { Loader2, Mail, ShieldCheck, Stethoscope } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useMemo, useState } from "react";
import { toast } from "sonner";

import { getSupabaseAuthBrowserClient } from "@/lib/supabase/auth-browser";

function LoginForm() {
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);

  const nextPath = useMemo(() => params.get("next") || "/", [params]);
  const hasInvalidLinkError =
    params.get("error") === "link_non_valido_o_scaduto";

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail) {
      toast.error("Inserisci un indirizzo email valido.");
      return;
    }

    try {
      setSending(true);
      const supabase = getSupabaseAuthBrowserClient();
      const { error } = await supabase.auth.signInWithOtp({
        email: normalizedEmail,
        options: {
          emailRedirectTo: `${window.location.origin}/auth/callback`,
        },
      });

      if (error) {
        toast.error(`Invio non riuscito: ${error.message}`);
        return;
      }

      toast.success("Link inviato! Controlla la tua email.");
      setEmail("");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Errore imprevisto.";
      toast.error(message);
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="relative flex min-h-dvh items-center justify-center overflow-x-hidden px-4 py-10 text-slate-800">
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

      <section className="relative z-10 w-full max-w-md rounded-3xl border border-white/40 bg-white/70 p-8 shadow-2xl shadow-slate-900/[0.08] backdrop-blur-xl">
        <div className="mb-6">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.jpg" alt="MedFlow Logo" className="mb-4 h-12 w-12 rounded-xl shadow-md shadow-slate-900/10 ring-1 ring-white/60" />
          <div className="mb-3 inline-flex rounded-2xl border border-violet-100/80 bg-gradient-to-br from-violet-50 to-white p-2.5 text-violet-600 shadow-sm shadow-violet-500/10">
            <Stethoscope className="size-5" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              Accedi a MedFlow
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              Login sicuro con Magic Link Supabase in ambiente protetto.
            </p>
          </div>
        </div>

        {hasInvalidLinkError ? (
          <div className="mb-4 rounded-2xl border border-amber-200/80 bg-amber-50/90 px-3 py-2.5 text-sm text-amber-900 shadow-sm backdrop-blur-sm">
            Il link e&apos; scaduto o non valido. Richiedine uno nuovo.
          </div>
        ) : null}

        <form className="space-y-4" onSubmit={onSubmit}>
          <label className="block text-sm font-semibold text-slate-700" htmlFor="email">
            Email professionale
          </label>
          <div className="relative">
            <Mail className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="medico@studio.it"
              className="w-full rounded-xl border-0 bg-slate-100/90 py-3 pl-10 pr-3 text-sm text-slate-900 shadow-inner shadow-slate-900/[0.03] ring-1 ring-slate-200/60 transition-all placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-0"
              autoComplete="email"
              required
            />
          </div>

          <button
            type="submit"
            disabled={sending}
            className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-gradient-to-r from-violet-600 to-blue-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-600/25 ring-1 ring-white/20 transition hover:scale-[1.02] hover:shadow-xl hover:shadow-blue-600/30 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:scale-100"
          >
            {sending ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Invio in corso...
              </>
            ) : (
              <>
                <ShieldCheck className="size-4" />
                Invia Link di Accesso
              </>
            )}
          </button>
        </form>

        <p className="mt-5 text-xs leading-relaxed text-slate-500">
          Riceverai un link monouso via email. Nessuna password da ricordare.
        </p>
      </section>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="relative flex min-h-dvh items-center justify-center overflow-x-hidden px-4 py-10 text-slate-800">
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
          <div className="relative z-10 inline-flex items-center gap-2 rounded-3xl border border-white/40 bg-white/70 px-5 py-3.5 text-sm font-medium text-slate-700 shadow-2xl shadow-slate-900/[0.08] backdrop-blur-xl">
            <Loader2 className="size-4 animate-spin text-violet-600" />
            Caricamento pagina di accesso...
          </div>
        </main>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
