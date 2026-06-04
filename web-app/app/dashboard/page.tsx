"use client";

import { ChevronDown, Link2, LogOut, QrCode, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { DashboardApp } from "@/components/dashboard/dashboard-app";
import { PatientInvitationCard } from "@/components/dashboard/patient-invitation-card";
import { getSupabaseAuthBrowserClient } from "@/lib/supabase/auth-browser";

export default function DashboardPage() {
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [isHeaderOpen, setIsHeaderOpen] = useState(false);

  useEffect(() => {
    if (!isInviteModalOpen && !isHeaderOpen) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsInviteModalOpen(false);
        setIsHeaderOpen(false);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isInviteModalOpen, isHeaderOpen]);

  async function handleLogout() {
    setSigningOut(true);
    try {
      const supabase = getSupabaseAuthBrowserClient();
      await supabase.auth.signOut();
      router.push("/");
      router.refresh();
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-slate-50">
      {/* Always-present toggle: small arrow top-right, overlaid (no layout space). */}
      <button
        type="button"
        onClick={() => setIsHeaderOpen((open) => !open)}
        aria-label={isHeaderOpen ? "Hide menu" : "Show menu"}
        aria-expanded={isHeaderOpen}
        className="absolute right-2 top-2 z-50 inline-flex size-7 items-center justify-center rounded-md bg-white/85 text-slate-500 shadow-sm ring-1 ring-slate-200 backdrop-blur transition hover:bg-white hover:text-slate-900"
      >
        <ChevronDown
          className={`size-4 transition-transform duration-200 ${
            isHeaderOpen ? "rotate-180" : ""
          }`}
          aria-hidden
        />
      </button>

      {/* Click-away backdrop while the header is open. */}
      {isHeaderOpen ? (
        <div
          className="absolute inset-0 z-30"
          aria-hidden
          onClick={() => setIsHeaderOpen(false)}
        />
      ) : null}

      <header
        className={`absolute inset-x-0 top-0 z-40 flex items-center justify-between gap-4 border-b border-slate-200 bg-white/95 py-3 pl-4 pr-12 shadow-md backdrop-blur transition-all duration-200 md:pl-6 ${
          isHeaderOpen
            ? "translate-y-0 opacity-100"
            : "pointer-events-none -translate-y-full opacity-0"
        }`}
      >
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold text-slate-900 md:text-lg">
            Doctor CRM · MedFlow
          </h1>
          <p className="truncate text-xs text-slate-500">
            Patients, WhatsApp messages and records
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <Link
            href="/"
            className="text-sm text-slate-600 transition hover:text-slate-900"
          >
            Home
          </Link>
          <button
            type="button"
            onClick={() => {
              setIsHeaderOpen(false);
              setIsInviteModalOpen(true);
            }}
            className="inline-flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-800 shadow-sm transition hover:bg-emerald-100"
          >
            <QrCode className="size-4" aria-hidden />
            <span>Invite patients</span>
            <Link2 className="size-3.5 opacity-80" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => void handleLogout()}
            disabled={signingOut}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:opacity-50"
          >
            <LogOut className="size-4" aria-hidden />
            {signingOut ? "Signing out…" : "Logout"}
          </button>
        </div>
      </header>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <DashboardApp />
      </div>
      {isInviteModalOpen ? (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/60 p-3 backdrop-blur-sm sm:p-6"
          role="dialog"
          aria-modal="true"
          aria-label="Invite patients"
          onClick={() => setIsInviteModalOpen(false)}
        >
          <div
            className="relative max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-2xl border border-slate-200 bg-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur sm:px-5">
              <p className="text-sm font-semibold text-slate-900 sm:text-base">
                Patient onboarding
              </p>
              <button
                type="button"
                onClick={() => setIsInviteModalOpen(false)}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-sm text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
                aria-label="Close patient invite window"
              >
                <X className="size-4" aria-hidden />
                <span>Close</span>
              </button>
            </div>
            <PatientInvitationCard />
          </div>
        </div>
      ) : null}
    </div>
  );
}
