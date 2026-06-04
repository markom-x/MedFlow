"use server";

import { redirect } from "next/navigation";

import { getSupabaseAuthServerClient } from "@/lib/supabase/auth-server";

export type EnterDemoResult = { ok: false; error: string } | void;

/**
 * One-click demo login: authenticates a pre-seeded demo doctor account
 * (email+password from server-side env) and sets the session cookies, so the
 * founder enters the dashboard without typing email or password.
 *
 * Credentials stay server-side (never exposed to the browser). No passphrase is
 * required: the demo button is the primary, frictionless entry point.
 */
export async function enterDemo(): Promise<EnterDemoResult> {
  const email = process.env.DEMO_DOCTOR_EMAIL;
  const password = process.env.DEMO_DOCTOR_PASSWORD;

  if (!email || !password) {
    return {
      ok: false,
      error:
        "Demo not configured: set DEMO_DOCTOR_EMAIL and DEMO_DOCTOR_PASSWORD.",
    };
  }

  const supabase = await getSupabaseAuthServerClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) {
    return { ok: false, error: `Demo sign-in failed: ${error.message}` };
  }

  // redirect() throws internally: it must be called outside try/catch.
  redirect("/dashboard");
}
