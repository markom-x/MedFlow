"use client";

import { Pencil } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PatientBucket } from "@/lib/dashboard/aggregate";
import { lastMessagePreview } from "@/lib/dashboard/aggregate";
import { needsAttention } from "@/lib/dashboard/format";
import { useState } from "react";

type Props = {
  orderedIds: string[];
  buckets: Map<string, PatientBucket>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  updatePatientName: (patientId: string, newName: string) => Promise<void>;
};

export function PatientSidebar({
  orderedIds,
  buckets,
  selectedId,
  onSelect,
  updatePatientName,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");

  function startEditing(id: string, currentName: string | null) {
    setEditingId(id);
    setDraftName(currentName?.trim() ?? "");
  }

  async function commitEdit(id: string) {
    const nextName = draftName.trim();
    setEditingId(null);
    await updatePatientName(id, nextName);
  }

  return (
    <aside className="flex h-full min-h-0 w-full shrink-0 flex-col overflow-hidden border-r border-slate-200 bg-white shadow-sm md:w-80 md:min-w-[18rem]">
      <div className="border-b border-slate-200 px-4 py-4 md:px-5 md:py-5">
        <h1 className="text-lg font-semibold tracking-tight text-slate-900">
          Pazienti
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">
          In cima: da gestire o urgenza alta. Clicca per aprire il fascicolo.
        </p>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 py-2 md:px-3 md:py-3">
        <ul className="flex flex-col gap-2">
          {orderedIds.map((id) => {
            const bucket = buckets.get(id);
            if (!bucket) return null;
            const { profile, requests } = bucket;
            const alert = needsAttention(requests);
            const active = selectedId === id;
            const preview = lastMessagePreview(requests);

            return (
              <li key={id}>
                <button
                  type="button"
                  onClick={() => onSelect(id)}
                  className={cn(
                    "w-full rounded-xl border px-4 py-3.5 text-left text-base shadow-sm transition-colors",
                    "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50",
                    active && "border-blue-300 bg-blue-50/80 ring-1 ring-blue-200"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={cn(
                        "mt-2 size-2.5 shrink-0 rounded-full",
                        alert ? "bg-red-600" : "bg-emerald-600"
                      )}
                      title={alert ? "Richiede attenzione" : "Nessuna azione urgente"}
                    />
                    <div className="min-w-0 flex-1">
                      {editingId === id ? (
                        <input
                          autoFocus
                          value={draftName}
                          onChange={(event) => setDraftName(event.target.value)}
                          onBlur={() => void commitEdit(id)}
                          onClick={(event) => event.stopPropagation()}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              event.preventDefault();
                              void commitEdit(id);
                            }
                            if (event.key === "Escape") {
                              event.preventDefault();
                              setEditingId(null);
                              setDraftName("");
                            }
                          }}
                          className="w-full rounded border border-blue-300 bg-white px-2 py-0.5 text-sm font-semibold text-slate-900 outline-none ring-1 ring-blue-200"
                          placeholder="Nome paziente"
                          aria-label="Modifica nome paziente"
                        />
                      ) : (
                        <span
                          className="inline-flex max-w-full items-center gap-1.5 truncate font-semibold text-slate-900"
                          title="Clicca per modificare il nome"
                          onClick={(event) => {
                            event.stopPropagation();
                            startEditing(id, profile.nomeRaw);
                          }}
                        >
                          <span className="truncate">{profile.nomeDisplay}</span>
                          <Pencil className="size-3.5 shrink-0 text-slate-500" />
                        </span>
                      )}
                      <p className="mt-1 line-clamp-2 text-sm leading-snug text-slate-600">
                        {preview}
                      </p>
                    </div>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
