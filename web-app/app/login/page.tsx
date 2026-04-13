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
          emailRedirectTo: window.location.origin,
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
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-4 py-10">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(6,182,212,0.15),transparent_38%),radial-gradient(circle_at_85%_80%,rgba(168,85,247,0.16),transparent_40%)]" />
      <section className="relative w-full max-w-md rounded-2xl border border-slate-800/90 bg-slate-900/70 p-6 shadow-2xl shadow-black/40 backdrop-blur-md sm:p-8">
        <div className="mb-6">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.jpg" alt="MedFlow Logo" className="mb-4 h-12 w-12 rounded-lg" />
          <div className="mb-3 inline-flex rounded-xl bg-cyan-500/15 p-2 text-cyan-300">
            <Stethoscope className="size-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-white">Accesso Dashboard Medica</h1>
            <p className="text-sm text-slate-400">
              Login sicuro con Magic Link Supabase in ambiente protetto.
            </p>
          </div>
        </div>

        {hasInvalidLinkError ? (
          <div className="mb-4 rounded-lg border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
            Il link e&apos; scaduto o non valido. Richiedine uno nuovo.
          </div>
        ) : null}

        <form className="space-y-4" onSubmit={onSubmit}>
          <label className="block text-sm font-medium text-slate-300" htmlFor="email">
            Email professionale
          </label>
          <div className="relative">
            <Mail className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="medico@studio.it"
              className="w-full rounded-lg border border-slate-700 bg-slate-900 py-2.5 pl-9 pr-3 text-sm text-white placeholder:text-slate-500 transition focus:outline-none focus:ring-2 focus:ring-cyan-500"
              autoComplete="email"
              required
            />
          </div>

          <button
            type="submit"
            disabled={sending}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-cyan-500 to-purple-600 px-4 py-2.5 text-sm font-bold text-white transition-transform duration-200 hover:scale-[1.02] hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
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

        <p className="mt-4 text-xs leading-relaxed text-slate-400">
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
        <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-10">
          <div className="inline-flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300 shadow-sm">
            <Loader2 className="size-4 animate-spin" />
            Caricamento pagina di accesso...
          </div>
        </main>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
