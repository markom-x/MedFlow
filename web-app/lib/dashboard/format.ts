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
  return "Sconosciuto (clicca per modificare)";
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
 * Normalizza il valore di urgenza ai 3 livelli della dashboard, mappando anche
 * i valori semaforo legacy (ROSSO/GIALLO/VERDE) eventualmente residui in DB.
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

export function urgencyMeta(level: UrgencyLevel | null): {
  label: string;
  short: string;
  badgeClass: string;
  dotClass: string;
} {
  switch (level) {
    case "alta":
      return {
        label: "Urgenza alta",
        short: "Alta",
        badgeClass: "border-red-200 bg-red-50 text-red-700",
        dotClass: "bg-red-600",
      };
    case "media":
      return {
        label: "Urgenza media",
        short: "Media",
        badgeClass: "border-amber-200 bg-amber-50 text-amber-700",
        dotClass: "bg-amber-500",
      };
    case "bassa":
      return {
        label: "Urgenza bassa",
        short: "Bassa",
        badgeClass: "border-emerald-200 bg-emerald-50 text-emerald-700",
        dotClass: "bg-emerald-600",
      };
    default:
      return {
        label: "Urgenza non valutata",
        short: "n/d",
        badgeClass: "border-slate-200 bg-slate-50 text-slate-600",
        dotClass: "bg-slate-400",
      };
  }
}
