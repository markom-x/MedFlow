"use client";

import { Check, Copy, MessageCircle, Printer } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { STUDIO_MEDICO_ID } from "@/lib/dashboard/constants";
import { getSupabaseAuthBrowserClient } from "@/lib/supabase/auth-browser";

/** WhatsApp click-to-chat expects digits only (country code + number, no +). */
function waMePhoneDigits(raw: string): string {
  return raw.replace(/\D/g, "");
}

function buildPatientActivationWhatsAppUrl(
  twilioPhoneRaw: string,
  medicoId: string
): string | null {
  const phone = waMePhoneDigits(twilioPhoneRaw);
  if (!phone || !medicoId) return null;
  // The backend (`Activation <uuid>`) checks the id against `medici.id`, NOT the
  // Auth UID: we therefore use the practice doctor's id.
  const text = `Activation ${medicoId}`;
  return `https://wa.me/${phone}?text=${encodeURIComponent(text)}`;
}

export function PatientInvitationCard() {
  const [doctorUid, setDoctorUid] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const supabase = getSupabaseAuthBrowserClient();
    let cancelled = false;

    async function syncUser() {
      const { data, error } = await supabase.auth.getUser();
      if (cancelled) return;
      if (error || !data.user) {
        setDoctorUid(null);
      } else {
        setDoctorUid(data.user.id);
      }
      setAuthLoading(false);
    }

    void syncUser();

    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      if (cancelled) return;
      setDoctorUid(session?.user?.id ?? null);
      setAuthLoading(false);
    });

    return () => {
      cancelled = true;
      sub.subscription.unsubscribe();
    };
  }, []);

  const twilioPhone = process.env.NEXT_PUBLIC_TWILIO_PHONE_NUMBER ?? "";
  // Id del medico dello studio (coerente con le scritture lato dashboard e col
  // webhook). Overridabile via env senza ricompilare il codice.
  const medicoId =
    process.env.NEXT_PUBLIC_MEDICO_STUDIO_ID?.trim() || STUDIO_MEDICO_ID;

  const magicLink = useMemo(() => {
    // We only show the invite to a logged-in doctor, but the activation code is
    // the doctor's id (medici.id), not the Auth UID.
    if (doctorUid == null) return null;
    return buildPatientActivationWhatsAppUrl(twilioPhone, medicoId);
  }, [twilioPhone, medicoId, doctorUid]);

  const handleCopy = useCallback(async () => {
    if (!magicLink) return;
    try {
      await navigator.clipboard.writeText(magicLink);
      setCopied(true);
      toast.success("Link copied to clipboard");
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Copy failed. Please select the link manually.");
    }
  }, [magicLink]);

  const handlePrintQr = useCallback(() => {
    window.print();
  }, []);

  if (authLoading) {
    return (
      <div className="shrink-0 border-b border-slate-200 bg-white px-4 py-4 md:px-6">
        <div
          className="mx-auto max-w-5xl h-36 animate-pulse rounded-xl bg-slate-100"
          aria-hidden
        />
        <span className="sr-only">Loading patient invite…</span>
      </div>
    );
  }

  if (doctorUid == null) {
    return null;
  }

  if (!twilioPhone.trim()) {
    return (
      <div className="shrink-0 border-b border-amber-200 bg-amber-50 px-4 py-3 md:px-6">
        <p className="mx-auto max-w-5xl text-sm text-amber-950">
          To generate the WhatsApp invite link, set the{" "}
          <code className="rounded bg-amber-100/80 px-1.5 py-0.5 font-mono text-xs">
            NEXT_PUBLIC_TWILIO_PHONE_NUMBER
          </code>{" "}
          variable (your Twilio / sandbox number in E.164 format, e.g.{" "}
          <span className="whitespace-nowrap font-mono text-xs">+14155238886</span>).
        </p>
      </div>
    );
  }

  if (!magicLink) {
    return null;
  }

  return (
    <section className="shrink-0 border-b border-slate-200 bg-gradient-to-b from-slate-50 to-white px-4 py-4 md:px-6 print:border-0 print:bg-white print:py-2">
      <div className="mx-auto max-w-5xl">
        <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm ring-1 ring-slate-900/5">
          <div className="flex flex-col gap-1 border-b border-slate-100 bg-gradient-to-r from-emerald-600/95 to-teal-600/95 px-4 py-3 md:flex-row md:items-center md:justify-between md:px-5">
            <div className="flex items-center gap-2 text-white">
              <span className="flex size-9 items-center justify-center rounded-lg bg-white/15 backdrop-blur-sm">
                <MessageCircle className="size-5" aria-hidden />
              </span>
              <div>
                <h2 className="text-sm font-semibold tracking-tight md:text-base">
                  Invite patients on WhatsApp
                </h2>
                <p className="text-xs text-emerald-50/95 md:text-sm">
                  Link and QR with your doctor code to activate the bot
                </p>
              </div>
            </div>
          </div>

          <div className="grid gap-6 p-4 md:grid-cols-[1fr_auto] md:items-start md:gap-8 md:p-6">
            <div className="min-w-0 space-y-3">
              <label
                htmlFor="patient-invite-magic-link"
                className="text-xs font-medium uppercase tracking-wide text-slate-500"
              >
                Magic link
              </label>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
                <input
                  id="patient-invite-magic-link"
                  readOnly
                  value={magicLink}
                  className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 font-mono text-xs text-slate-800 shadow-inner outline-none ring-emerald-500/30 focus-visible:ring-2 md:text-sm"
                  spellCheck={false}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="default"
                  onClick={() => void handleCopy()}
                  className="shrink-0 border-slate-200 bg-white sm:w-auto"
                >
                  {copied ? (
                    <>
                      <Check className="size-4 text-emerald-600" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy className="size-4" />
                      Copy to clipboard
                    </>
                  )}
                </Button>
              </div>
              <p className="text-xs leading-relaxed text-slate-500">
                Share the link by email or clipboard: when the patient opens
                WhatsApp, it pre-fills the message{" "}
                <span className="font-medium text-slate-700">Activation</span> followed by your
                doctor code.
              </p>
            </div>

            <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-slate-200 bg-slate-50/80 p-4 print:border-slate-300">
              <p className="text-center text-xs font-medium text-slate-600">QR for the waiting room</p>
              <div className="rounded-lg bg-white p-2 shadow-sm print:shadow-none">
                <QRCodeSVG
                  value={magicLink}
                  size={160}
                  level="M"
                  includeMargin={false}
                  className="size-40 md:size-44"
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handlePrintQr}
                className="text-slate-600 print:hidden"
              >
                <Printer className="size-3.5" />
                Print QR
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
