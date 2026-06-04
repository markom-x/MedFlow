"use client";

import { FileText, Loader2 } from "lucide-react";

import { urlLooksLikeAudio, urlLooksLikePdf } from "@/lib/dashboard/media";
import { useSignedPatientMediaUrl } from "@/lib/dashboard/use-signed-patient-media-url";
import { cn } from "@/lib/utils";

type Layout = "chat" | "recap";

type Props = {
  storagePath: string;
  layout?: Layout;
};

/**
 * Allegato paziente: path Storage privato o URL legacy → URL firmato lato server, poi media.
 */
export function SignedPatientMedia({ storagePath, layout = "chat" }: Props) {
  const isAudio = urlLooksLikeAudio(storagePath);
  const isPdf = urlLooksLikePdf(storagePath);
  const { src, loading, error } = useSignedPatientMediaUrl(storagePath);

  if (loading) {
    return (
      <div
        className={cn(
          "flex items-center gap-2 text-slate-500",
          layout === "recap" && "min-h-[4rem]"
        )}
      >
        <Loader2 className="size-5 shrink-0 animate-spin" aria-hidden />
        <span className="text-sm">Loading attachment…</span>
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-sm text-red-600" role="alert">
        {error}
      </p>
    );
  }

  if (!src) return null;

  if (isAudio) {
    return (
      <audio
        controls
        className={cn("mt-2 w-full", layout === "recap" && "mt-1")}
        src={src}
        preload="metadata"
      />
    );
  }

  if (isPdf) {
    if (layout === "recap") {
      return (
        <a
          href={src}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-base font-medium text-blue-700 underline-offset-2 hover:underline"
        >
          <FileText className="size-4 shrink-0 text-blue-600" aria-hidden />
          Open PDF
        </a>
      );
    }
    return (
      <a
        href={src}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-2 inline-flex text-base font-medium text-blue-700 underline underline-offset-2 hover:text-blue-800"
      >
        Download / open PDF
      </a>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      className={cn(
        "mt-2 max-w-xs cursor-pointer rounded-lg object-contain",
        layout === "recap" &&
          "max-h-48 mt-0 w-full max-w-none cursor-default rounded-lg object-contain"
      )}
    />
  );
}
