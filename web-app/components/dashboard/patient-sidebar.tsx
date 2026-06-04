"use client";

import { cn } from "@/lib/utils";
import type { PatientBucket } from "@/lib/dashboard/aggregate";
import { lastMessagePreview } from "@/lib/dashboard/aggregate";

type Props = {
  orderedIds: string[];
  buckets: Map<string, PatientBucket>;
  selectedId: string | null;
  onSelect: (id: string) => void;
};

export function PatientSidebar({
  orderedIds,
  buckets,
  selectedId,
  onSelect,
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
            const { profile, requests } = bucket;
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
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold text-slate-900">
                      {profile.nomeDisplay}
                    </p>
                    <p className="mt-1 line-clamp-2 text-sm leading-snug text-slate-600">
                      {preview}
                    </p>
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
