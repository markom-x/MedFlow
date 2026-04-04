"use client";

import { Loader2, Paperclip, Send, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { formatCreatedAt, isMedicoMessage } from "@/lib/dashboard/format";
import {
  bubbleMessageText,
  isAllegatoMultimedialePlaceholder,
} from "@/lib/dashboard/message-text";
import { urlLooksLikeAudio, urlLooksLikePdf } from "@/lib/dashboard/media";
import type { RichiestaRow } from "@/lib/dashboard/types";
import { getSupabaseAuthBrowserClient } from "@/lib/supabase/auth-browser";
import { cn } from "@/lib/utils";

type Props = {
  /** UUID `pazienti.id` (stesso tipo del DB) */
  pazienteId: string;
  requests: RichiestaRow[];
  sending: boolean;
  onSend: (payload: { text: string; file: File | null }) => Promise<boolean>;
  className?: string;
  /** Colonna centrale CRM: solo area messaggi scrollabile, composer fisso in basso */
  variant?: "default" | "crmColumn";
};

function sortByCreatedAt(rows: RichiestaRow[]): RichiestaRow[] {
  return [...rows].sort(
    (a, b) =>
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );
}

function rowFromRealtimeNew(raw: Record<string, unknown>): RichiestaRow {
  return {
    id: String(raw.id ?? ""),
    created_at: String(raw.created_at ?? ""),
    stato: raw.stato != null ? String(raw.stato) : null,
    urgenza: raw.urgenza != null ? String(raw.urgenza) : null,
    riassunto_clinico:
      raw.riassunto_clinico != null ? String(raw.riassunto_clinico) : null,
    messaggio_originale:
      raw.messaggio_originale != null ? String(raw.messaggio_originale) : null,
    url_media: raw.url_media != null ? String(raw.url_media) : null,
    pazienti: null,
  };
}

const FILE_INPUT_ACCEPT =
  "image/jpeg,image/png,image/webp,image/gif,application/pdf,.pdf,.png,.jpg,.jpeg,.webp";

const QUICK_REPLIES = [
  "Ricetta pronta in segreteria",
  "Passi in studio per una visita",
  "Tutto nella norma",
] as const;

/** Paziente: sinistra, grigio chiaro */
const bubblePatient =
  "rounded-bl-lg border border-slate-200 bg-slate-100 text-slate-900";

/** Medico: destra, azzurro chiaro con bordo azzurro */
const bubbleMedico =
  "rounded-br-lg border border-blue-200 bg-blue-50 text-slate-900";

export function ChatSection({
  pazienteId,
  requests,
  sending,
  onSend,
  className,
  variant = "default",
}: Props) {
  const isCrm = variant === "crmColumn";
  const [draft, setDraft] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  const [messages, setMessages] = useState<RichiestaRow[]>([]);
  const [realtimeEnterId, setRealtimeEnterId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const enterClearRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const draftInputRef = useRef<HTMLTextAreaElement>(null);

  const requestsSignature = useMemo(
    () => requests.map((r) => r.id).join(","),
    [requests]
  );

  const prevPazienteIdRef = useRef(pazienteId);

  /**
   * Merge props `requests` con lo stato locale: le righe dalle props vincono su stesso `id`;
   * i messaggi solo-Realtime (id non ancora nelle props) restano. Evita che un refetch “indietro” cancelli la coda.
   */
  useEffect(() => {
    const switchedPatient = prevPazienteIdRef.current !== pazienteId;
    prevPazienteIdRef.current = pazienteId;

    if (switchedPatient) {
      setMessages(sortByCreatedAt(requests));
      return;
    }

    setMessages((prev) => {
      const seenIds = new Set<string>();
      const merged: RichiestaRow[] = [];

      for (const r of requests) {
        if (seenIds.has(r.id)) continue;
        seenIds.add(r.id);
        merged.push(r);
      }
      for (const r of prev) {
        if (seenIds.has(r.id)) continue;
        seenIds.add(r.id);
        merged.push(r);
      }

      return sortByCreatedAt(merged);
    });
  }, [pazienteId, requestsSignature]);

  useEffect(() => {
    const supabase = getSupabaseAuthBrowserClient();

    const channel = supabase.channel("custom-insert-channel");

    channel.on(
      "postgres_changes",
      {
        event: "INSERT",
        schema: "public",
        table: "richieste",
      },
      (payload) => {
        console.log("Nuovo messaggio in arrivo:", payload.new);

        const raw = payload.new as Record<string, unknown> | null;
        if (!raw) return;
        if (String(raw.paziente_id) !== String(pazienteId)) return;

        const newMsg = rowFromRealtimeNew(raw);

        setMessages((prev) => {
          if (prev.some((m) => m.id === newMsg.id)) return prev;
          return [newMsg, ...prev];
        });

        if (enterClearRef.current) clearTimeout(enterClearRef.current);
        setRealtimeEnterId(newMsg.id);
        enterClearRef.current = setTimeout(() => {
          setRealtimeEnterId(null);
          enterClearRef.current = null;
        }, 520);
      }
    );

    channel.subscribe((status, err) => {
      if (status === "SUBSCRIBED") return;
      if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
        console.error("[Realtime richieste INSERT]", status, err);
        return;
      }
      if (status === "CLOSED") {
        // In dev può succedere durante remount/cleanup React Strict Mode.
        console.info("[Realtime richieste INSERT]", status);
      }
    });

    return () => {
      if (enterClearRef.current) clearTimeout(enterClearRef.current);
      void supabase.removeChannel(channel);
    };
  }, [pazienteId]);

  const chatRows = useMemo(() => sortByCreatedAt(messages), [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatRows.length, sending]);

  const canSend =
    (draft.trim().length > 0 || attachment !== null) && !sending;

  async function sendMessage() {
    if (!canSend) return;
    const text = draft.trim();
    const file = attachment;
    const ok = await onSend({ text, file });
    if (ok) {
      setDraft("");
      setAttachment(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function applyQuickReply(text: string, sendImmediately: boolean) {
    if (sendImmediately) {
      if (sending) return;
      const ok = await onSend({ text, file: null });
      if (ok) {
        setDraft("");
        setAttachment(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
      return;
    }
    setDraft(text);
    requestAnimationFrame(() => draftInputRef.current?.focus());
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await sendMessage();
  }

  return (
    <div
      className={cn(
        "flex min-h-0 flex-1 flex-col bg-white",
        !isCrm && "rounded-xl border border-slate-200 shadow-sm",
        className
      )}
    >
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-3 sm:px-4 sm:py-4 md:space-y-3 md:px-6">
        {chatRows.map((messaggio) => {
          const raw =
            (messaggio.messaggio_originale ?? "").trim() || "[Messaggio vuoto]";
          const medico = isMedicoMessage(messaggio.messaggio_originale);
          const text = bubbleMessageText(raw, medico);
          const u = messaggio.url_media?.trim() || null;
          const isAudio = Boolean(u && urlLooksLikeAudio(u));
          const isPdf = Boolean(u && urlLooksLikePdf(u));
          /** referti / immagini: url valorizzato e non audio né PDF */
          const isImageOrReferto =
            Boolean(u) && !isAudio && !isPdf;
          const showTextBelowImage =
            isImageOrReferto &&
            text.trim().length > 0 &&
            !isAllegatoMultimedialePlaceholder(text);
          const animateEnter = realtimeEnterId === messaggio.id;

          return (
            <div
              key={messaggio.id}
              className={cn(
                "flex w-full",
                medico ? "justify-end" : "justify-start",
                animateEnter && "chat-bubble-realtime-enter"
              )}
            >
              <div
                className={cn(
                  "max-w-[min(100%,32rem)] rounded-2xl px-4 py-3 text-lg leading-relaxed shadow-sm",
                  medico ? bubbleMedico : bubblePatient
                )}
              >
                <p
                  className={cn(
                    "mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500",
                    medico && "text-blue-800"
                  )}
                >
                  {formatCreatedAt(messaggio.created_at)}
                </p>
                {isAudio && u ? (
                  <>
                    <audio
                      controls
                      className="mt-2 w-full"
                      src={u}
                      preload="metadata"
                    />
                    {text.trim() ? (
                      <p className="mt-2 whitespace-pre-wrap text-slate-900">
                        {text}
                      </p>
                    ) : null}
                  </>
                ) : isPdf && u ? (
                  <>
                    {!isAllegatoMultimedialePlaceholder(text) ? (
                      <p className="whitespace-pre-wrap text-slate-900">{text}</p>
                    ) : null}
                    <a
                      href={u}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 inline-flex text-base font-medium text-blue-700 underline underline-offset-2 hover:text-blue-800"
                    >
                      Scarica / apri PDF
                    </a>
                  </>
                ) : isImageOrReferto && u ? (
                  <>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={u}
                      alt=""
                      className="mt-2 max-w-xs cursor-pointer rounded-lg object-contain"
                    />
                    {showTextBelowImage ? (
                      <p className="mt-2 whitespace-pre-wrap text-slate-900">
                        {text}
                      </p>
                    ) : null}
                  </>
                ) : (
                  <p className="whitespace-pre-wrap text-slate-900">{text}</p>
                )}
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSubmit}
        className={cn(
          "sticky bottom-0 z-10 shrink-0 border-t border-slate-200 bg-white px-3 py-3 pb-[calc(env(safe-area-inset-bottom)+0.75rem)] sm:px-4 md:px-6",
          isCrm ? "mt-auto" : ""
        )}
      >
        {attachment ? (
          <div className="mx-auto mb-3 flex max-w-3xl items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-base text-slate-900">
            <span className="min-w-0 truncate font-medium">{attachment.name}</span>
            <button
              type="button"
              onClick={() => {
                setAttachment(null);
                if (fileInputRef.current) fileInputRef.current.value = "";
              }}
              className="shrink-0 rounded-md p-1.5 text-slate-600 hover:bg-slate-200"
              aria-label="Rimuovi allegato"
            >
              <X className="size-5" />
            </button>
          </div>
        ) : null}

        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept={FILE_INPUT_ACCEPT}
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              setAttachment(f ?? null);
            }}
          />
          <Button
            type="button"
            variant="outline"
            size="icon-lg"
            className="shrink-0 rounded-lg border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            disabled={sending}
            onClick={() => fileInputRef.current?.click()}
            aria-label="Allega file"
          >
            <Paperclip className="size-5" />
          </Button>
          <textarea
            ref={draftInputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Scrivi un messaggio al paziente…"
            rows={1}
            className={cn(
              "max-h-40 min-h-[46px] flex-1 resize-none rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-base text-slate-900 shadow-sm md:px-4 md:py-3 md:text-lg",
              "placeholder:text-slate-500",
              "outline-none transition-colors",
              "focus:border-blue-600 focus:ring-2 focus:ring-blue-600/25"
            )}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void sendMessage();
              }
            }}
            disabled={sending}
          />
          <Button
            type="submit"
            size="icon-lg"
            className="h-12 min-w-12 shrink-0 rounded-lg bg-blue-600 text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
            disabled={!canSend}
            aria-label="Invia messaggio"
          >
            {sending ? (
              <Loader2 className="size-5 animate-spin" />
            ) : (
              <Send className="size-5" />
            )}
          </Button>
        </div>
        <div className="mx-auto mt-3 flex max-w-3xl flex-wrap gap-2">
          {QUICK_REPLIES.map((label) => (
            <button
              key={label}
              type="button"
              disabled={sending}
              title="Clic: inserisci nel messaggio · Maiusc+clic: invia subito"
              onClick={(e) => {
                void applyQuickReply(label, e.shiftKey);
              }}
              className="rounded-md border border-slate-200 bg-slate-100 px-2.5 py-1.5 text-left text-xs font-medium text-slate-700 transition-colors hover:bg-slate-200 disabled:opacity-50"
            >
              {label}
            </button>
          ))}
        </div>
        {!isCrm ? (
          <p className="mx-auto mt-3 max-w-3xl text-center text-sm text-slate-500">
            Aggiornamenti in tempo reale sulla tabella{" "}
            <code className="rounded bg-slate-100 px-1 text-slate-800">richieste</code>
          </p>
        ) : null}
      </form>
    </div>
  );
}
