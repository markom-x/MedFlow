"use client";

import { LogOut } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { DashboardApp } from "@/components/dashboard/dashboard-app";
import { getSupabaseAuthBrowserClient } from "@/lib/supabase/auth-browser";

export default function DashboardPage() {
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);

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
    <div className="flex min-h-dvh min-h-0 flex-col bg-slate-50">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 py-3 md:px-6">
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold text-slate-900 md:text-lg">
            CRM Medico · MedFlow
          </h1>
          <p className="truncate text-xs text-slate-500">
            Pazienti, messaggi WhatsApp e triage
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
            onClick={() => void handleLogout()}
            disabled={signingOut}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:opacity-50"
          >
            <LogOut className="size-4" aria-hidden />
            {signingOut ? "Uscita…" : "Logout"}
          </button>
        </div>
      </header>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <DashboardApp />
      </div>
    </div>
  );
}
