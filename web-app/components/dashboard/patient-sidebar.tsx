"use client";

import { Pencil } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { lastMessagePreview } from "@/lib/dashboard/aggregate";
import type { PatientBucket } from "@/lib/dashboard/aggregate";
import { cn } from "@/lib/utils";

type Props = {
  orderedIds: string[];
  buckets: Map<string, PatientBucket>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  updatePatientName: (patientId: string, newName: string) => Promise<void>;
};

function PatientListItem({
  bucket,
  active,
  onSelect,
  updatePatientName,
}: {
  bucket: PatientBucket;
  active: boolean;
  onSelect: () => void;
  updatePatientName: (patientId: string, newName: string) => Promise<void>;
}) {
  const { profile, requests } = bucket;
  const preview = lastMessagePreview(requests);
  const [isEditingName, setIsEditingName] = useState(false);
  const [draftName, setDraftName] = useState(profile.nomeRaw ?? "");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const leaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function openDetails() {
    if (leaveTimerRef.current) {
      clearTimeout(leaveTimerRef.current);
      leaveTimerRef.current = null;
    }
    setDetailsOpen(true);
  }

  function scheduleCloseDetails() {
    if (leaveTimerRef.current) clearTimeout(leaveTimerRef.current);
    leaveTimerRef.current = setTimeout(() => setDetailsOpen(false), 450);
  }

  useEffect(() => {
    if (!isEditingName) {
      setDraftName(profile.nomeRaw ?? "");
    }
  }, [isEditingName, profile.nomeRaw]);

  async function commitNameEdit() {
    const nextName = draftName.trim();
    setIsEditingName(false);
    await updatePatientName(profile.id, nextName);
  }

  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "group/patient relative w-full rounded-xl border px-4 py-3.5 text-left text-base shadow-sm transition-colors",
          "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50",
          active && "border-blue-300 bg-blue-50/80 ring-1 ring-blue-200"
        )}
      >
        <div className="relative min-w-0 flex-1">
          {isEditingName ? (
            <input
              autoFocus
              value={draftName}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setDraftName(e.target.value)}
              onBlur={() => void commitNameEdit()}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void commitNameEdit();
                }
                if (e.key === "Escape") {
                  e.preventDefault();
                  setIsEditingName(false);
                  setDraftName(profile.nomeRaw ?? "");
                }
              }}
              className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm font-semibold text-slate-900 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              aria-label="Edit patient name"
            />
          ) : (
            <div
              className="relative inline-block max-w-full"
              onMouseEnter={openDetails}
              onMouseLeave={scheduleCloseDetails}
            >
              <p className="truncate font-semibold text-slate-900 pr-1">
                {profile.nomeDisplay}
              </p>
              {detailsOpen ? (
                <div
                  className="absolute left-0 top-full z-30 pt-2"
                  onMouseEnter={openDetails}
                  onMouseLeave={scheduleCloseDetails}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="min-w-[12rem] rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-lg">
                  <p className="font-mono text-xs text-slate-600">
                    {profile.telefono}
                  </p>
                  <button
                    type="button"
                    className="mt-1.5 inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-blue-700"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDetailsOpen(false);
                      setIsEditingName(true);
                    }}
                    aria-label="Edit patient name"
                  >
                    <Pencil className="size-3.5" />
                    Edit name
                  </button>
                  </div>
                </div>
              ) : null}
            </div>
          )}
          <p className="mt-1 line-clamp-2 text-sm leading-snug text-slate-600">
            {preview}
          </p>
        </div>
      </button>
    </li>
  );
}

export function PatientSidebar({
  orderedIds,
  buckets,
  selectedId,
  onSelect,
  updatePatientName,
}: Props) {
  return (
    <aside className="flex h-full min-h-0 w-full shrink-0 flex-col overflow-hidden border-r border-slate-200 bg-white shadow-sm md:w-80 md:min-w-[18rem]">
      <div className="border-b border-slate-200 px-4 py-4 md:px-5 md:py-5">
        <h1 className="text-lg font-semibold tracking-tight text-slate-900">
          Patients
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">
          Click a contact to open their record.
        </p>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 py-2 md:px-3 md:py-3">
        <ul className="flex flex-col gap-2">
          {orderedIds.map((id) => {
            const bucket = buckets.get(id);
            if (!bucket) return null;
            return (
              <PatientListItem
                key={id}
                bucket={bucket}
                active={selectedId === id}
                onSelect={() => onSelect(id)}
                updatePatientName={updatePatientName}
              />
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
