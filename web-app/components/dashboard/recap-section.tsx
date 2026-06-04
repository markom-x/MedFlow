"use client";

import { Sparkles } from "lucide-react";

import { SignedPatientMedia } from "@/components/dashboard/signed-patient-media";
import { latestClinicalSummary } from "@/lib/dashboard/aggregate";
import { formatCreatedAt } from "@/lib/dashboard/format";
import { urlLooksLikeAudio } from "@/lib/dashboard/media";
import type { RichiestaRow } from "@/lib/dashboard/types";
import { cn } from "@/lib/utils";

type Props = {
  requests: RichiestaRow[];
  className?: string;
  /** Colonna stretta: una sola colonna per allegati */
  variant?: "default" | "sidebar";
  /** Tab fascicolo: più aria e tipografia più grande */
  fascicoloLayout?: boolean;
  /** In galleria mostra solo immagini e PDF (esclude vocali) */
  galleryVisualOnly?: boolean;
  /** Nasconde il blocco super-riassunto (quando la sintesi e' gia' mostrata altrove) */
  hideSummary?: boolean;
};

export function RecapSection({
  requests,
  className,
  variant = "default",
  fascicoloLayout = false,
  galleryVisualOnly = false,
  hideSummary = false,
}: Props) {
  const narrow = variant === "sidebar";
  const sortedDesc = [...requests].sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  const superSummary = latestClinicalSummary(requests);

  const mediaItems = sortedDesc
    .filter((r) => r.url_media)
    .map((r) => ({
      url: r.url_media as string,
      createdAt: r.created_at,
      msg: r.messaggio_originale ?? "",
    }))
    .filter((item) =>
      galleryVisualOnly ? !urlLooksLikeAudio(item.url) : true
    );

  return (
    <div
      className={cn(
        "flex flex-col",
        fascicoloLayout ? "gap-8" : narrow ? "gap-4" : "gap-6",
        className
      )}
    >
      {hideSummary ? null : (
        <div
          className={cn(
            "rounded-2xl border border-slate-200/90 bg-white shadow-sm",
            fascicoloLayout && "border-blue-100/80 bg-gradient-to-b from-blue-50/40 to-white p-8",
            !fascicoloLayout && (narrow ? "p-4" : "p-6"),
            !fascicoloLayout && "rounded-xl"
          )}
        >
          <div className="flex items-center gap-2">
            <Sparkles
              className={cn(
                "shrink-0 text-blue-600",
                narrow ? "size-4" : fascicoloLayout ? "size-6" : "size-5"
              )}
              strokeWidth={1.75}
              aria-hidden
            />
            <h2
              className={cn(
                "font-semibold uppercase tracking-wide text-blue-800",
                fascicoloLayout ? "text-sm" : "text-xs"
              )}
            >
              AI super summary
            </h2>
          </div>
          <p
            className={cn(
              "mt-4 font-semibold leading-relaxed text-slate-900",
              narrow ? "text-sm" : fascicoloLayout ? "text-xl" : "text-lg"
            )}
          >
            {superSummary ?? (
              <span className="font-normal text-slate-600">
                No AI summary available for this patient yet.
              </span>
            )}
          </p>
        </div>
      )}

      <div>
        <h3
          className={cn(
            "mb-4 font-semibold text-slate-900",
            narrow ? "text-sm" : fascicoloLayout ? "text-lg" : "text-base"
          )}
        >
          {galleryVisualOnly ? "Reports gallery" : "Reports & attachments"}
        </h3>
        {mediaItems.length === 0 ? (
          <p
            className={cn(
              "text-slate-600",
              narrow ? "text-sm" : fascicoloLayout ? "text-base" : "text-base"
            )}
          >
            {galleryVisualOnly
              ? "No photos or PDFs on file for this patient."
              : "No reports or attachments with a media URL."}
          </p>
        ) : (
          <ul
            className={cn(
              "grid gap-4",
              narrow ? "grid-cols-1" : fascicoloLayout
                ? "grid-cols-1 sm:grid-cols-2"
                : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
            )}
          >
            {mediaItems.map(({ url, createdAt, msg }, i) => (
              <li
                key={`${url}-${createdAt}-${i}`}
                className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
              >
                <div className="border-b border-slate-200 px-3 py-2">
                  <p className="text-xs font-medium text-slate-600">
                    {formatCreatedAt(createdAt)}
                  </p>
                </div>
                <div className="p-3">
                  <SignedPatientMedia
                    key={`${url}-${i}`}
                    storagePath={url}
                    layout="recap"
                  />
                  {msg.trim() ? (
                    <p className="mt-2 line-clamp-3 text-sm leading-snug text-slate-700">
                      {msg}
                    </p>
                  ) : null}
                  <p
                    className="mt-2 truncate text-xs text-slate-500"
                    title={url}
                  >
                    {url.length > 56 ? `${url.slice(0, 56)}…` : url}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
