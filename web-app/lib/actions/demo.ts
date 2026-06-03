"use server";

import { redirect } from "next/navigation";

import { getSupabaseAuthServerClient } from "@/lib/supabase/auth-server";

export type EnterDemoResult = { ok: false; error: string } | void;

/**
 * Login "one-click" per la demo: autentica un account medico demo pre-seedato
 * (email+password in env, lato server) e imposta i cookie di sessione, cosi' il
 * founder entra nella dashboard senza email ne' password da digitare.
 *
 * Protezione opzionale: se DEMO_ACCESS_PASSPHRASE e' impostata, va fornita.
 * Credenziali e passphrase restano server-side (mai esposte al browser).
 */
export async function enterDemo(passphrase?: string): Promise<EnterDemoResult> {
  const email = process.env.DEMO_DOCTOR_EMAIL;
  const password = process.env.DEMO_DOCTOR_PASSWORD;

  if (!email || !password) {
    return {
      ok: false,
      error:
        "Demo non configurata: imposta DEMO_DOCTOR_EMAIL e DEMO_DOCTOR_PASSWORD.",
    };
  }

  const required = process.env.DEMO_ACCESS_PASSPHRASE;
  if (required && (passphrase ?? "").trim() !== required) {
    return { ok: false, error: "Codice demo non valido." };
  }

  const supabase = await getSupabaseAuthServerClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) {
    return { ok: false, error: `Accesso demo non riuscito: ${error.message}` };
  }

  // redirect() lancia internamente: va chiamato fuori da try/catch.
  redirect("/dashboard");
}
