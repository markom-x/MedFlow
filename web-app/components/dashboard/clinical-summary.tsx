"use client";

import { Stethoscope } from "lucide-react";

import {
  highestUrgenza,
  latestClinicalSummary,
  latestFinalizedRequest,
} from "@/lib/dashboard/aggregate";
import {
  formatCreatedAt,
  isMedicoMessage,
  normalizeUrgenza,
  urgencyMeta,
} from "@/lib/dashboard/format";
import type { RichiestaRow } from "@/lib/dashboard/types";
import { cn } from "@/lib/utils";

type Props = {
  requests: RichiestaRow[];
};

/**
 * Card di sintesi clinica in evidenza nel tab Fascicolo: mostra l'ultima sintesi
 * prodotta dall'agente con il badge di urgenza colorato. E' la prima cosa che il
 * medico vede aprendo il fascicolo.
 */
export function ClinicalSummary({ requests }: Props) {
  const latest = latestFinalizedRequest(requests);
  const summary = latestClinicalSummary(requests);
  const level = latest
    ? normalizeUrgenza(latest.urgenza)
    : highestUrgenza(requests);
  const meta = urgencyMeta(level);

  const motivo =
    latest && !isMedicoMessage(latest.messaggio_originale)
      ? latest.messaggio_originale?.trim() || ""
      : "";

  return (
    <section className="rounded-2xl border border-blue-100/80 bg-gradient-to-b from-blue-50/40 to-white p-6 shadow-sm md:p-8">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Stethoscope
            className="size-6 shrink-0 text-blue-600"
            strokeWidth={1.75}
            aria-hidden
          />
          <h2 className="text-sm font-semibold uppercase tracking-wide text-blue-800">
            Sintesi clinica
          </h2>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold",
            meta.badgeClass
          )}
          title={meta.label}
        >
          <span className={cn("size-2 rounded-full", meta.dotClass)} aria-hidden />
          {meta.short}
        </span>
      </div>

      {motivo ? (
        <p className="mt-4 text-sm font-medium uppercase tracking-wide text-slate-500">
          Motivo del contatto
        </p>
      ) : null}
      {motivo ? (
        <p className="mt-1 text-base leading-relaxed text-slate-800">{motivo}</p>
      ) : null}

      <p className="mt-4 text-xl font-semibold leading-relaxed text-slate-900">
        {summary ?? (
          <span className="text-base font-normal text-slate-600">
            Nessuna sintesi clinica ancora disponibile. Apparira' qui appena
            l'agente avra' completato l'anamnesi del paziente.
          </span>
        )}
      </p>

      {latest ? (
        <p className="mt-4 text-xs text-slate-500">
          Aggiornata il {formatCreatedAt(latest.created_at)}
        </p>
      ) : null}
    </section>
  );
}
