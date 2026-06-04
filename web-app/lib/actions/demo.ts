"use server";

import { redirect } from "next/navigation";

import { getSupabaseAuthServerClient } from "@/lib/supabase/auth-server";

export type SignInResult = { ok: false; error: string } | void;

/**
 * Gated demo sign-in.
 *
 * The login form looks like a normal email field, but only allow-listed
 * addresses can enter — this keeps the doctor's phone number, the patient data
 * and the AI WhatsApp number from being reachable by anyone who lands on the
 * site. The "special" address (given to the founder) logs in INSTANTLY: there
 * is no real inbox / one-time code round-trip, because under the hood we sign
 * in a single pre-seeded demo doctor account whose credentials live only on the
 * server.
 *
 * Env:
 * - DEMO_DOCTOR_EMAIL / DEMO_DOCTOR_PASSWORD: the pre-seeded demo account.
 * - DEMO_ALLOWED_EMAILS (optional, comma-separated): extra addresses allowed to
 *   enter. Defaults to just DEMO_DOCTOR_EMAIL. Whatever allowed address is
 *   typed, the same demo dashboard opens.
 */
export async function signInWithEmail(emailInput: string): Promise<SignInResult> {
  const email = (emailInput || "").trim().toLowerCase();
  if (!email) {
    return { ok: false, error: "Enter the email you were given for the demo." };
  }

  const demoEmail = (process.env.DEMO_DOCTOR_EMAIL || "").trim().toLowerCase();
  const password = process.env.DEMO_DOCTOR_PASSWORD;
  if (!demoEmail || !password) {
    return {
      ok: false,
      error:
        "Demo not configured: set DEMO_DOCTOR_EMAIL and DEMO_DOCTOR_PASSWORD.",
    };
  }

  const allowList = (process.env.DEMO_ALLOWED_EMAILS || demoEmail)
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);

  if (!allowList.includes(email)) {
    return {
      ok: false,
      error:
        "This email isn't authorized for the demo. Use the address you were given.",
    };
  }

  const supabase = await getSupabaseAuthServerClient();
  const { error } = await supabase.auth.signInWithPassword({
    email: demoEmail,
    password,
  });
  if (error) {
    return { ok: false, error: `Sign-in failed: ${error.message}` };
  }

  // redirect() throws internally: it must be called outside try/catch.
  redirect("/dashboard");
}
