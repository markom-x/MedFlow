"use server";

import { redirect } from "next/navigation";

import { getSupabaseAuthServerClient } from "@/lib/supabase/auth-server";
import { getSupabaseServiceRoleClient } from "@/lib/supabase/server";

export type SignInResult = { ok: false; error: string } | void;

/**
 * Ensures the demo doctor exists in Supabase Auth with the password from env.
 * Requires SUPABASE_SERVICE_ROLE_KEY on the server (Vercel). Idempotent: safe
 * on every allowed sign-in attempt.
 */
async function ensureDemoDoctorAuthUser(
  demoEmail: string,
  password: string
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const admin = getSupabaseServiceRoleClient();
    const { data: created, error: createError } =
      await admin.auth.admin.createUser({
        email: demoEmail,
        password,
        email_confirm: true,
      });

    if (!createError) {
      return { ok: true };
    }

    const msg = (createError.message || "").toLowerCase();
    const alreadyExists =
      msg.includes("already") ||
      msg.includes("registered") ||
      msg.includes("exists");

    if (!alreadyExists) {
      return { ok: false, error: createError.message };
    }

    const { data: listData, error: listError } =
      await admin.auth.admin.listUsers({ page: 1, perPage: 200 });
    if (listError) {
      return { ok: false, error: listError.message };
    }

    const existing = (listData?.users ?? []).find(
      (u) => (u.email || "").trim().toLowerCase() === demoEmail
    );
    if (!existing?.id) {
      return {
        ok: false,
        error:
          "Demo user exists but could not be found. Check DEMO_DOCTOR_EMAIL in Supabase Auth.",
      };
    }

    const { error: updateError } = await admin.auth.admin.updateUserById(
      existing.id,
      { password, email_confirm: true }
    );
    if (updateError) {
      return { ok: false, error: updateError.message };
    }
    return { ok: true };
  } catch (e) {
    const message = e instanceof Error ? e.message : "Service role unavailable.";
    return { ok: false, error: message };
  }
}

/**
 * Gated demo sign-in.
 *
 * The login form looks like a normal email field, but only allow-listed
 * addresses can enter. The founder types their invited email; the server opens
 * the shared demo doctor session (DEMO_DOCTOR_EMAIL) without OTP.
 *
 * Env (Vercel):
 * - DEMO_DOCTOR_EMAIL / DEMO_DOCTOR_PASSWORD — Supabase Auth user for the demo.
 * - DEMO_ALLOWED_EMAILS — comma-separated invite emails (optional).
 * - SUPABASE_SERVICE_ROLE_KEY — syncs the Auth user password from env on each
 *   sign-in (recommended; fixes "Invalid login credentials" after env changes).
 */
export async function signInWithEmail(emailInput: string): Promise<SignInResult> {
  const email = (emailInput || "").trim().toLowerCase();
  if (!email) {
    return { ok: false, error: "Enter the email you were given for the demo." };
  }

  const demoEmail = (process.env.DEMO_DOCTOR_EMAIL || "").trim().toLowerCase();
  const password = (process.env.DEMO_DOCTOR_PASSWORD || "").trim();
  if (!demoEmail || !password) {
    return {
      ok: false,
      error:
        "Demo not configured: set DEMO_DOCTOR_EMAIL and DEMO_DOCTOR_PASSWORD on Vercel.",
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

  if (process.env.SUPABASE_SERVICE_ROLE_KEY) {
    const ensured = await ensureDemoDoctorAuthUser(demoEmail, password);
    if (!ensured.ok) {
      return {
        ok: false,
        error: `Could not prepare demo account: ${ensured.error}`,
      };
    }
  }

  const supabase = await getSupabaseAuthServerClient();
  const { error } = await supabase.auth.signInWithPassword({
    email: demoEmail,
    password,
  });
  if (error) {
    const hint = process.env.SUPABASE_SERVICE_ROLE_KEY
      ? " Check that DEMO_DOCTOR_EMAIL matches the Supabase Auth user."
      : " Add SUPABASE_SERVICE_ROLE_KEY on Vercel, or create the user in Supabase → Authentication → Users with that exact email and password.";
    return { ok: false, error: `Sign-in failed: ${error.message}.${hint}` };
  }

  redirect("/dashboard");
}
