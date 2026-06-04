"use client";

import { Stethoscope } from "lucide-react";

import {
  latestClinicalData,
  latestClinicalSummary,
  latestFinalizedRequest,
} from "@/lib/dashboard/aggregate";
import { formatClinicalEntityCategory } from "@/lib/dashboard/clinical-entity-labels";
import { formatCreatedAt } from "@/lib/dashboard/format";
import type { RichiestaRow } from "@/lib/dashboard/types";

type Props = {
  requests: RichiestaRow[];
};

function hasText(value: string | null | undefined): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function TableRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <tr className="border-b border-slate-100 last:border-0 align-top">
      <th
        scope="row"
        className="w-40 whitespace-nowrap py-2.5 pr-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 md:w-48"
      >
        {label}
      </th>
      <td className="py-2.5 text-sm leading-relaxed text-slate-900">{children}</td>
    </tr>
  );
}

/**
 * AI clinical summary rendered as a readable key/value table from the structured
 * synthesis (`dati_clinici`), with a graceful fallback to the free-text summary.
 * Shown under the record query panel, which is the primary tool.
 */
export function ClinicalSummary({ requests }: Props) {
  const latest = latestFinalizedRequest(requests);
  const data = latestClinicalData(requests);
  const summaryText = latestClinicalSummary(requests);

  const medications = (data?.medications ?? []).filter(hasText);
  const redFlags = (data?.red_flags ?? []).filter(hasText);
  const entities = (data?.clinical_entities ?? []).filter((e) =>
    hasText(e?.description)
  );

  const hasStructured =
    hasText(data?.chief_complaint) ||
    hasText(data?.history_of_present_illness) ||
    medications.length > 0 ||
    redFlags.length > 0 ||
    entities.length > 0;

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

      {hasText(data?.sintesi_medica) || hasText(summaryText) ? (
        <p className="mt-4 text-base font-medium leading-relaxed text-slate-900">
          {data?.sintesi_medica?.trim() || summaryText}
        </p>
      ) : null}

      {hasStructured ? (
        <div className="mt-5 overflow-hidden rounded-xl border border-slate-200">
          <table className="w-full border-collapse">
            <tbody className="[&>tr>th]:px-4 [&>tr>td]:pr-4">
              {hasText(data?.chief_complaint) ? (
                <TableRow label="Chief complaint">
                  {data?.chief_complaint?.trim()}
                </TableRow>
              ) : null}
              {hasText(data?.history_of_present_illness) ? (
                <TableRow label="History">
                  {data?.history_of_present_illness?.trim()}
                </TableRow>
              ) : null}
              {medications.length > 0 ? (
                <TableRow label="Medications">
                  <ul className="flex flex-wrap gap-1.5">
                    {medications.map((m, i) => (
                      <li
                        key={`${m}-${i}`}
                        className="rounded-md bg-slate-100 px-2 py-0.5 text-sm text-slate-800"
                      >
                        {m}
                      </li>
                    ))}
                  </ul>
                </TableRow>
              ) : null}
              {entities.length > 0 ? (
                <TableRow label="Key findings">
                  <ul className="list-disc space-y-1 pl-4">
                    {entities.map((e, i) => (
                      <li key={`${e.description}-${i}`}>
                        {e.description}
                        {hasText(e.category) ? (
                          <span className="ml-1 text-xs text-slate-500">
                            ({formatClinicalEntityCategory(e.category!)})
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </TableRow>
              ) : null}
              {redFlags.length > 0 ? (
                <TableRow label="Red flags">
                  <ul className="list-disc space-y-1 pl-4 text-slate-900">
                    {redFlags.map((r, i) => (
                      <li key={`${r}-${i}`}>{r}</li>
                    ))}
                  </ul>
                </TableRow>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : !hasText(data?.sintesi_medica) && !hasText(summaryText) ? (
        <p className="mt-4 text-base font-normal text-slate-600">
          No clinical summary yet. It will appear here once the patient has shared
          information and documents.
        </p>
      ) : null}

      {latest ? (
        <p className="mt-4 text-xs text-slate-500">
          Updated {formatCreatedAt(latest.created_at)}
        </p>
      ) : null}
    </section>
  );
}
