"use client";

import { Stethoscope } from "lucide-react";

import {
  latestClinicalSummary,
  latestFinalizedRequest,
} from "@/lib/dashboard/aggregate";
import { formatCreatedAt } from "@/lib/dashboard/format";
import type { RichiestaRow } from "@/lib/dashboard/types";

type Props = {
  requests: RichiestaRow[];
};

/**
 * AI clinical summary for the patient: the latest synthesis produced from the
 * WhatsApp conversation and attached documents. Shown under the record query
 * panel, which is the primary tool.
 */
export function ClinicalSummary({ requests }: Props) {
  const latest = latestFinalizedRequest(requests);
  const summary = latestClinicalSummary(requests);

  return (
    <section className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-sm md:p-8">
      <div className="flex items-center gap-2">
        <Stethoscope
          className="size-5 shrink-0 text-blue-600"
          strokeWidth={1.75}
          aria-hidden
        />
        <h2 className="text-sm font-semibold uppercase tracking-wide text-blue-800">
          Clinical summary
        </h2>
      </div>

      <p className="mt-4 text-lg font-medium leading-relaxed text-slate-900">
        {summary ?? (
          <span className="text-base font-normal text-slate-600">
            No clinical summary yet. It will appear here once the assistant has
            completed the patient&apos;s intake.
          </span>
        )}
      </p>

      {latest ? (
        <p className="mt-4 text-xs text-slate-500">
          Updated {formatCreatedAt(latest.created_at)}
        </p>
      ) : null}
    </section>
  );
}
