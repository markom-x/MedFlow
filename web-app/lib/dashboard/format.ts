import { MEDICO_FILE_SENT, MEDICO_MSG_PREFIX } from "./constants";

export function cleanPhone(phone: string | null | undefined): string {
  let value = (phone ?? "").trim();
  if (value.toLowerCase().startsWith("whatsapp:")) {
    value = value.split(":", 2)[1]?.trim() ?? "";
  }
  return value || "Numero sconosciuto";
}

export function patientDisplayName(
  nome: string | null | undefined,
  _phoneClean: string
): string {
  if (nome?.trim()) return nome.trim();
  return "Unknown (click to edit)";
}

export function formatCreatedAt(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return new Intl.DateTimeFormat("it-IT", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return value;
  }
}

export function isMedicoMessage(raw: string | null | undefined): boolean {
  const t = (raw ?? "").trim();
  return t.startsWith(MEDICO_MSG_PREFIX) || t === MEDICO_FILE_SENT;
}

export function needsAttention(requests: { stato?: string | null; urgenza?: string | null }[]): boolean {
  for (const req of requests) {
    const stato = (req.stato ?? "").trim().toLowerCase();
    const urgenza = normalizeUrgenza(req.urgenza);
    if (stato === "da gestire" || urgenza === "alta") return true;
  }
  return false;
}

export type UrgencyLevel = "alta" | "media" | "bassa";

/**
 * Normalizes the urgency value to the 3 internal levels, mapping legacy
 * traffic-light values (ROSSO/GIALLO/VERDE) that may still exist in the DB.
 * Used only for internal sorting (no urgency is shown in the UI).
 */
export function normalizeUrgenza(
  urgenza: string | null | undefined
): UrgencyLevel | null {
  const v = (urgenza ?? "").trim().toLowerCase();
  const legacy: Record<string, UrgencyLevel> = {
    rosso: "alta",
    giallo: "media",
    verde: "bassa",
  };
  if (v in legacy) return legacy[v];
  if (v === "alta" || v === "media" || v === "bassa") return v;
  return null;
}
