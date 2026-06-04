"use server";

import { patientMediaBucketForPath } from "@/lib/dashboard/storage-bucket";
import { getSupabaseAuthServerClient } from "@/lib/supabase/auth-server";
import { getSupabaseServiceRoleClient } from "@/lib/supabase/server";

export type PatientMediaSignedUrlResult =
  | { ok: true; signedUrl: string }
  | { ok: false; message: string };

/**
 * Genera un URL firmato per un oggetto in Storage (bucket privato), usando la service role.
 * Richiede sessione dashboard (middleware); non esporre anon.
 */
export async function createPatientMediaSignedUrl(
  storagePath: string,
  expiresIn: number = 3600
): Promise<PatientMediaSignedUrlResult> {
  const raw = storagePath.trim();
  if (!raw) {
    return { ok: false, message: "Missing media path." };
  }

  const auth = await getSupabaseAuthServerClient();
  const {
    data: { user },
    error: userError,
  } = await auth.auth.getUser();

  if (userError || !user) {
    return { ok: false, message: "Invalid session." };
  }

  if (/^https?:\/\//i.test(raw)) {
    return { ok: true, signedUrl: raw };
  }

  const bucket = patientMediaBucketForPath(raw);

  try {
    const supabase = getSupabaseServiceRoleClient();
    const { data, error } = await supabase.storage
      .from(bucket)
      .createSignedUrl(raw, expiresIn);

    if (error) {
      return {
        ok: false,
        message: error.message || "Could not generate a signed URL.",
      };
    }

    if (!data?.signedUrl) {
      return { ok: false, message: "Signed URL not available." };
    }

    return { ok: true, signedUrl: data.signedUrl };
  } catch (e) {
    const msg =
      e instanceof Error ? e.message : "Error while signing the URL.";
    return {
      ok: false,
      message: msg.includes("SUPABASE_SERVICE_ROLE_KEY")
        ? `${msg} Configura SUPABASE_SERVICE_ROLE_KEY sul server.`
        : msg,
    };
  }
}
