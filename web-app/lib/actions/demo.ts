"use server";

import { getSupabaseAuthServerClient } from "@/lib/supabase/auth-server";
import { getSupabaseServiceRoleClient } from "@/lib/supabase/server";

export type SignInResult = { ok: true } | { ok: false; error: string };

const DEFAULT_DEMO_EMAIL = "founder@medflow.demo";

async function ensureDemoAuthUser(
  email: string,
  password: string
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const admin = getSupabaseServiceRoleClient();
    const { error: createError } = await admin.auth.admin.createUser({
      email,
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
      (u) => (u.email || "").trim().toLowerCase() === email
    );
    if (!existing?.id) {
      return { ok: false, error: "Demo user not found in Supabase Auth." };
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
    const message = e instanceof Error ? e.message : "Server config error.";
    return { ok: false, error: message };
  }
}

/**
 * Demo login: one email + one password (what the user types in the form).
 * Defaults: founder@medflow.demo — override with DEMO_DOCTOR_EMAIL /
 * DEMO_DOCTOR_PASSWORD on Vercel. Requires SUPABASE_SERVICE_ROLE_KEY to
 * auto-create/sync the Auth user.
 */
export async function signInWithDemo(
  emailInput: string,
  passwordInput: string
): Promise<SignInResult> {
  const email = (emailInput || "").trim().toLowerCase();
  const password = (passwordInput || "").trim();

  if (!email || !password) {
    return { ok: false, error: "Enter email and password." };
  }

  const demoEmail = (
    process.env.DEMO_DOCTOR_EMAIL || DEFAULT_DEMO_EMAIL
  )
    .trim()
    .toLowerCase();

  if (email !== demoEmail) {
    return {
      ok: false,
      error: "Invalid demo credentials.",
    };
  }

  const expectedPassword = (process.env.DEMO_DOCTOR_PASSWORD || "").trim();
  if (!expectedPassword) {
    return {
      ok: false,
      error: "Demo password not configured (DEMO_DOCTOR_PASSWORD on Vercel).",
    };
  }

  if (password !== expectedPassword) {
    return { ok: false, error: "Invalid demo credentials." };
  }

  if (!process.env.SUPABASE_SERVICE_ROLE_KEY) {
    return {
      ok: false,
      error:
        "Add SUPABASE_SERVICE_ROLE_KEY on Vercel (Settings → Environment Variables).",
    };
  }

  const ensured = await ensureDemoAuthUser(demoEmail, expectedPassword);
  if (!ensured.ok) {
    return {
      ok: false,
      error: `Could not prepare demo account: ${ensured.error}`,
    };
  }

  const supabase = await getSupabaseAuthServerClient();
  const { error } = await supabase.auth.signInWithPassword({
    email: demoEmail,
    password: expectedPassword,
  });
  if (error) {
    return { ok: false, error: `Sign-in failed: ${error.message}` };
  }

  return { ok: true };
}
