"use client";

import { Loader2, Menu, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { sendDoctorMessage } from "@/lib/actions";
import { EmptyPatientState } from "@/components/dashboard/empty-state";
import { PatientMainArea } from "@/components/dashboard/patient-main-area";
import { PatientSidebar } from "@/components/dashboard/patient-sidebar";
import {
  groupRichiesteByPatient,
  sortPatientIds,
  type PatientBucket,
} from "@/lib/dashboard/aggregate";
import { fetchRichieste } from "@/lib/dashboard/data";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { safeStorageFileName } from "@/lib/upload/safe-storage-name";
import { cn } from "@/lib/utils";

export function DashboardApp() {
  const [buckets, setBuckets] = useState<Map<string, PatientBucket>>(new Map());
  const [orderedIds, setOrderedIds] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const supabase = getSupabaseBrowserClient();
      const rows = await fetchRichieste(supabase);
      const map = groupRichiesteByPatient(rows);
      const ids = sortPatientIds(map);
      setBuckets(map);
      setOrderedIds(ids);
    } catch (e) {
      const msg =
        e instanceof Error ? e.message : "Errore durante il caricamento.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedBucket = useMemo(() => {
    if (selectedId == null) return null;
    return buckets.get(selectedId) ?? null;
  }, [buckets, selectedId]);

  async function handleSendMessage(payload: {
    text: string;
    file: File | null;
  }): Promise<boolean> {
    if (selectedId == null || !selectedBucket) return false;
    const { text, file } = payload;
    const trimmed = text.trim();
    if (!trimmed && !file) {
      toast.error("Scrivi un messaggio o allega un file.");
      return false;
    }

    setSending(true);
    try {
      const supabase = getSupabaseBrowserClient();
      let urlPubblico: string | null = null;

      if (file) {
        const path = safeStorageFileName(file.name);
        const { error: uploadError } = await supabase.storage
          .from("referti")
          .upload(path, file, {
            contentType: file.type || "application/octet-stream",
            upsert: false,
          });
        if (uploadError) {
          toast.error(
            `Upload non riuscito: ${uploadError.message}. Verifica policy sul bucket referti.`
          );
          return false;
        }
        const { data } = supabase.storage.from("referti").getPublicUrl(path);
        urlPubblico = data.publicUrl;
      }

      const result = await sendDoctorMessage({
        pazienteId: selectedId,
        numeroPaziente: selectedBucket.profile.telefono,
        testo: trimmed,
        urlPubblico,
      });

      if (!result.ok) {
        toast.error(result.message);
        return false;
      }

      toast.success("Messaggio inviato");
      await load();
      return true;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Errore imprevisto.");
      return false;
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center bg-slate-50 px-4">
        <Loader2 className="size-9 animate-spin text-blue-600" aria-hidden />
        <span className="sr-only">Caricamento…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 bg-slate-50 px-4 text-center md:gap-4 md:px-6">
        <p className="max-w-md text-base text-red-800">{error}</p>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-base font-medium text-blue-700 shadow-sm transition hover:bg-slate-50"
        >
          Riprova
        </button>
      </div>
    );
  }

  if (orderedIds.length === 0) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center bg-slate-50 px-4 md:px-6">
        <div className="max-w-md rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <p className="text-base leading-relaxed text-slate-700">
            Nessuna richiesta in archivio. Collega Supabase e importa i dati per vedere i
            pazienti.
          </p>
        </div>
      </div>
    );
  }

  function handleSelectPatient(id: string) {
    setSelectedId(id);
    setMobileSidebarOpen(false);
  }

  return (
    <div className="relative flex h-full min-h-0 w-full flex-1 flex-col gap-2 overflow-hidden bg-slate-50 md:flex-row md:gap-6">
      <div className="flex items-center justify-between border-b border-slate-200 bg-white px-3 py-2 md:hidden">
        <button
          type="button"
          onClick={() => setMobileSidebarOpen(true)}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700"
        >
          <Menu className="size-4" />
          Pazienti
        </button>
        {selectedBucket ? (
          <p className="line-clamp-1 text-right text-sm font-medium text-slate-700">
            {selectedBucket.profile.nomeDisplay}
          </p>
        ) : null}
      </div>

      <div
        className={cn(
          "fixed inset-0 z-40 bg-slate-900/40 md:hidden",
          mobileSidebarOpen ? "block" : "hidden"
        )}
        onClick={() => setMobileSidebarOpen(false)}
      />

      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-full max-w-sm -translate-x-full transition-transform duration-200 md:static md:z-auto md:w-auto md:max-w-none md:translate-x-0",
          mobileSidebarOpen && "translate-x-0"
        )}
      >
        <div className="flex h-full min-h-0 flex-col">
          <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 md:hidden">
            <p className="text-sm font-semibold text-slate-800">Seleziona paziente</p>
            <button
              type="button"
              onClick={() => setMobileSidebarOpen(false)}
              className="rounded-md p-1.5 text-slate-600 hover:bg-slate-100"
              aria-label="Chiudi elenco pazienti"
            >
              <X className="size-4" />
            </button>
          </div>
          <PatientSidebar
            orderedIds={orderedIds}
            buckets={buckets}
            selectedId={selectedId}
            onSelect={handleSelectPatient}
          />
        </div>
      </div>

      {selectedBucket ? (
        <PatientMainArea
          profile={selectedBucket.profile}
          requests={selectedBucket.requests}
          sending={sending}
          onSendMessage={handleSendMessage}
          onNotesSaved={() => void load()}
        />
      ) : (
        <div className="flex min-h-0 min-w-0 flex-1 flex-col items-center justify-center overflow-hidden border-t border-slate-200 bg-white md:border-l md:border-t-0">
          <EmptyPatientState />
        </div>
      )}
    </div>
  );
}
